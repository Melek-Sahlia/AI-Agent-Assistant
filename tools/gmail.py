import os
import base64
from email.mime.text import MIMEText
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from langchain_core.tools import Tool, StructuredTool
from langchain_core.pydantic_v1 import BaseModel, Field
import logging # Added logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
TOKEN_PATH = os.getenv("GMAIL_TOKEN_FILE", "token.json")

# Define the scopes required for reading and sending emails
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.send']

# --- Argument Schema Definition ---
class SendEmailArgs(BaseModel):
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Subject line of the email")
    body: str = Field(description="Body content of the email")

class ReadEmailArgs(BaseModel):
    query: str | None = Field(default='is:unread', description="Optional Gmail query string (e.g., 'is:unread', 'subject:meeting'). Defaults to 'is:unread'.")

def _get_gmail_service():
    """Authenticates and returns the Gmail API service client."""
    creds = None
    logger.info("Attempting to get Gmail service.") # New log
    # The file token.json stores the user's access and refresh tokens.
    if os.path.exists(TOKEN_PATH):
        try:
            logger.info(f"Token file found at {TOKEN_PATH}. Loading credentials.") # New log
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            # --- Add check for validity immediately after loading ---
            if creds and creds.valid:
                logger.info("Loaded credentials appear valid.")
            elif creds:
                logger.warning("Loaded credentials appear invalid or expired.")
            # -----------------------------------------------------
        except Exception as e:
             logger.error(f"Error loading token file {TOKEN_PATH}: {e}")
             creds = None # Ensure creds is None if loading fails
    else:
        logger.info(f"Token file not found at {TOKEN_PATH}.") # New log

    # If there are no (valid) credentials available, let the user log in.
    # This block now also handles cases where loaded creds were invalid
    if not creds or not creds.valid:
        logger.info("No valid credentials found or loaded credentials invalid/expired.") # Modified log
        if creds and creds.expired and creds.refresh_token:
            try:
                logger.info("Credentials expired, attempting to refresh...") # New log
                creds.refresh(Request())
                logger.info("Credentials refreshed successfully.") # New log
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                creds = None # Force re-authentication if refresh fails
        else:
             if not creds:
                 logger.info("No credentials object found, will try to initiate OAuth flow.") # New log
             elif not creds.refresh_token:
                 logger.info("Credentials object found, but no refresh token available. Will try to initiate OAuth flow.") # New log

             # Check if credentials file exists
             if not os.path.exists(CREDENTIALS_PATH):
                 logger.error(f"Credentials file not found at {CREDENTIALS_PATH}")
                 raise FileNotFoundError(f"Credentials file not found at {CREDENTIALS_PATH}. Please download it from Google Cloud Console.")

             try:
                logger.info("No valid token found or refresh failed, initiating OAuth flow...") # Modified log
                # Use port=0 to find an available port automatically
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = flow.run_local_server(port=0)
                logger.info("OAuth flow completed successfully.")
             except Exception as e:
                 logger.error(f"Error during OAuth flow: {e}")
                 raise # Re-raise the exception to indicate failure

        # Save the credentials for the next run
        if creds:
             try:
                with open(TOKEN_PATH, 'w') as token:
                    token.write(creds.to_json())
                logger.info(f"Token saved to {TOKEN_PATH}")
             except Exception as e:
                 logger.error(f"Error saving token to {TOKEN_PATH}: {e}")
    else:
        logger.info("Valid credentials loaded from token file.") # New log

    if not creds:
         # This state should ideally not be reached if error handling above is correct
         logger.error("Failed to obtain Gmail credentials after all checks.") # New log
         raise Exception("Failed to obtain Gmail credentials.") 

    try:
        service = build('gmail', 'v1', credentials=creds)
        logger.info("Gmail service client created successfully.")
        return service
    except HttpError as error:
        logger.error(f'An API error occurred: {error}')
        raise # Re-raise API error
    except Exception as e:
        logger.error(f"Failed to build Gmail service: {e}")
        raise # Re-raise other errors


def _get_email_body(payload: dict) -> str:
    """Extracts and decodes the email body from the payload."""
    body = ""
    mime_type = payload.get('mimeType', '')

    if 'parts' in payload:
        # Multi-part email, look for text/plain or text/html
        for part in payload['parts']:
            part_mime_type = part.get('mimeType', '')
            if part_mime_type == 'text/plain':
                data = part.get('body', {}).get('data')
                if data:
                    body = base64.urlsafe_b64decode(data).decode('utf-8')
                    break # Prefer plain text
            elif part_mime_type == 'text/html':
                data = part.get('body', {}).get('data')
                if data and not body: # Use HTML only if plain text wasn't found
                    # Basic HTML stripping (consider a library for complex HTML)
                    html_body = base64.urlsafe_b64decode(data).decode('utf-8')
                    # Very basic tag removal for brevity - might need improvement
                    import re
                    body = re.sub('<[^<]+?>', '', html_body) 
            elif 'parts' in part: # Handle nested parts
                 nested_body = _get_email_body(part)
                 if nested_body:
                     body = nested_body
                     # If we found text in nested part, stop searching this level
                     if part_mime_type.startswith('text/'): 
                         break

    elif mime_type.startswith('text/'): # Single part email (text/plain or text/html)
        data = payload.get('body', {}).get('data')
        if data:
            decoded_body = base64.urlsafe_b64decode(data).decode('utf-8')
            if mime_type == 'text/html':
                import re
                body = re.sub('<[^<]+?>', '', decoded_body)
            else:
                 body = decoded_body
                 
    # Limit body length to avoid overwhelming the context window
    max_length = 1500 # Adjust as needed
    if len(body) > max_length:
        body = body[:max_length] + "... (truncated)"

    return body if body else "N/A"


def _read_emails(query: str | None = 'is:unread') -> str:
    """Reads emails matching the query from the user's Gmail account."""
    # Use the provided query or the default
    final_query = query if query else 'is:unread' # Ensure default if None or empty string
    logger.info(f"Reading emails with query: '{final_query}'") # Log the query being used

    try:
        service = _get_gmail_service()
        # Call the Gmail API to list messages
        results = service.users().messages().list(userId='me', q=final_query, maxResults=3).execute() # Reduced maxResults slightly
        messages = results.get('messages', [])

        if not messages:
            return "No emails found matching the query."

        email_details = []
        for msg_info in messages[:3]: # Process only top 3 to keep response size manageable
            msg_id = msg_info['id']
            # Get the full message details
            message = service.users().messages().get(userId='me', id=msg_id, format='full').execute() # Changed to format='full'
            payload = message.get('payload', {})
            headers = payload.get('headers', [])
            snippet = message.get('snippet', 'N/A')

            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'N/A')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'N/A')
            
            # Extract and decode the body
            body = _get_email_body(payload) # Use helper function

            email_details.append(f"From: {sender}\\nSubject: {subject}\\nSnippet: {snippet}\\nBody: {body}\\n---")


        if len(messages) > 3:
             email_details.append(f"({len(messages) - 3} more emails match the query but were not shown for brevity.)")

        return "\\n".join(email_details)

    except FileNotFoundError as e: # Catch specific error from _get_gmail_service
        return f"Error: {e}"
    except HttpError as error:
        logger.error(f"An API error occurred while reading emails: {error}")
        return f"API Error reading emails: {error}"
    except Exception as e:
        logger.error(f"An unexpected error occurred while reading emails: {e}")
        return f"Error reading emails: {e}"


def _send_email(to: str, subject: str, body: str) -> str:
    """Sends an email using the user's Gmail account."""
    # Ensure arguments are strings (passed directly by StructuredTool now)
    try:
        # --- Explicit Type Conversion for Robustness ---
        to = str(to) 
        subject = str(subject)
        body = str(body)
        # ----------------------------------------------
    except Exception as e: 
        # Catch any unexpected errors during conversion
        logger.error(f"Unexpected error during argument conversion: {e}")
        return f"Error processing arguments: {e}"

    # Proceed with sending the email
    try:
        service = _get_gmail_service()
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        # Encode the message in base64url format
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': raw_message}

        # Call the Gmail API to send the email
        sent_message = service.users().messages().send(userId='me', body=create_message).execute()
        logger.info(f"Email sent successfully. Message ID: {sent_message.get('id')}")
        return f"Email sent successfully to {to} with subject \"{subject}\"."

    except FileNotFoundError as e: # Catch specific error from _get_gmail_service
        return f"Error: {e}"
    except HttpError as error:
        logger.error(f"An API error occurred while sending email: {error}")
        # Provide more specific feedback if possible (e.g., invalid address)
        error_content = getattr(error, 'content', b'').decode('utf-8')
        return f"API Error sending email: {error}. Details: {error_content}"
    except Exception as e:
        logger.error(f"An unexpected error occurred while sending email: {e}")
        return f"Error sending email: {e}"

# --- Langchain Tool Definitions ---

read_email_tool = StructuredTool.from_function(
    func=_read_emails,
    name="read_email",
    description="Use this tool to read emails from the user's Gmail account when they ask to check their inbox, read specific emails, or search for emails. Fetches the From, Subject, Snippet, and the main Body content (decoded plain text or stripped HTML, possibly truncated) for the most recent matching emails.", # Updated description
    args_schema=ReadEmailArgs
)

send_email_tool = StructuredTool.from_function(
    func=_send_email,
    name="send_email",
    description="Sends an email from the user's Gmail account. Use this when the user asks to send an email.", 
    args_schema=SendEmailArgs
)

# --- Testing ---
# if __name__ == '__main__':
#     print("Testing Gmail Integration...")
#     # Test reading emails (will trigger OAuth flow if no token)
#     print("\n--- Testing Read Email ---")
#     # recent_unread = read_email_tool.run({}) # Test with default query
#     # print(recent_unread)
#     # test_read_query = 'from:google'
#     # print(f"\n--- Testing Read Email with query: {test_read_query} ---")
#     # query_result = read_email_tool.run(test_read_query)
#     # print(query_result)
#
#     # Test sending email (USE A TEST RECIPIENT)
#     # print("\n--- Testing Send Email ---")
#     # send_input = {
#     #     'to': 'your_test_email@example.com', # CHANGE THIS
#     #     'subject': 'Agent Test Email',
#     #     'body': 'This is a test email sent by the Langchain agent.'
#     # }
#     # send_result = send_email_tool.run(send_input)
#     # print(send_result) 