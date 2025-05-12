import requests
from bs4 import BeautifulSoup
from langchain_core.tools import StructuredTool
from langchain_core.pydantic_v1 import BaseModel, Field

# Define headers to mimic a browser visit
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive'
}

# --- Argument Schema for browse_website ---
class BrowseWebsiteArgs(BaseModel):
    url: str = Field(description="The valid URL of the website to browse.")

def _scrape_website_text(url: str) -> str:
    """Fetches content from a URL and extracts readable text."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15) # Added timeout
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

        soup = BeautifulSoup(response.text, 'html.parser')

        # Remove script and style elements
        for script_or_style in soup(["script", "style"]):
            script_or_style.decompose()

        # Get text, strip leading/trailing whitespace, and reduce multiple newlines/spaces
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        # Optional: Limit the length of the returned text if it's too long
        max_length = 4000 # Limit to ~4000 characters
        if len(text) > max_length:
           text = text[:max_length] + "... [content truncated]"

        return text if text else "Could not extract text from the webpage."

    except requests.exceptions.RequestException as e:
        return f"Error fetching URL {url}: {e}"
    except Exception as e:
        return f"Error processing URL {url}: {e}"

# --- Langchain Tool Definition ---
browse_tool = StructuredTool.from_function(
    func=_scrape_website_text,
    name="browse_website",
    description="Fetches the textual content from a given URL. Use this tool when you need to answer questions about the content of a specific webpage provided by the user or found in search results. Input must be a single, valid URL string.",
    args_schema=BrowseWebsiteArgs
)

# Example usage (for testing)
# if __name__ == '__main__':
#    test_url = "https://python.langchain.com/docs/get_started/introduction"
#    print(f"Browsing: {test_url}")
#    content = browse_tool.run(test_url)
#    print(content) 