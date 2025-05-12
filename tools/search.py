import os
from dotenv import load_dotenv
from googleapiclient.discovery import build
from langchain_core.tools import Tool
from langchain_core.pydantic_v1 import BaseModel, Field

# Load environment variables from .env file
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

# Define the input schema for the search tool
class GoogleSearchInput(BaseModel):
    query: str = Field(description="The search query to look up.")

def _run_google_search(query: str, num_results: int = 5) -> str:
    """Performs a Google Custom Search and returns formatted results."""
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        return "Error: Google API Key or CSE ID not configured. Please set GOOGLE_API_KEY and GOOGLE_CSE_ID environment variables."

    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
        result = service.cse().list(
            q=query,
            cx=GOOGLE_CSE_ID,
            num=num_results
        ).execute()

        # Process results
        if 'items' in result:
            formatted_results = []
            for item in result['items']:
                title = item.get('title')
                link = item.get('link')
                snippet = item.get('snippet')
                formatted_results.append(f"Title: {title}\nLink: {link}\nSnippet: {snippet}\n---")
            return "\n".join(formatted_results)
        else:
            return "No results found."

    except Exception as e:
        return f"Error during Google Search API call: {e}"

# --- Langchain Tool Definition ---

# You can test the function directly:
# if __name__ == '__main__':
#    test_query = "latest news on AI"
#    print(f"Testing search for: {test_query}")
#    search_results = _run_google_search(test_query)
#    print(search_results)

search_tool = Tool(
    name="google_search",
    func=_run_google_search,
    description="Useful for searching the internet for information. Input should be a search query.",
    args_schema=GoogleSearchInput
)

# Example usage of the tool (for testing)
# if __name__ == '__main__':
#     test_query = "Langchain framework"
#     print(search_tool.run(test_query)) 