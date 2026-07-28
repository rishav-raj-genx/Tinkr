from duckduckgo_search import DDGS

def search_web(query: str) -> str:
    """
    Searches the web using DuckDuckGo and returns a summary of the results.
    """
    print(f"\n [TOOL] Searching web for: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            if not results:
                return "No results found."
            
            output = ""
            for i, result in enumerate(results):
                output += f"[{i+1}] Title: {result.get('title')}\nSnippet: {result.get('body')}\n\n"
            return output
    except Exception as e:
        print(f" [TOOL ERROR] Web search failed: {e}")
        return f"Error searching the web: {e}"

def get_news(query: str) -> str:
    """
    Fetches the latest news using DuckDuckGo.
    """
    print(f"\n [TOOL] Fetching news for: {query}")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.news(query, max_results=3))
            if not results:
                return "No news results found."
            
            output = ""
            for i, result in enumerate(results):
                output += f"[{i+1}] Source: {result.get('source')}\nTitle: {result.get('title')}\nSnippet: {result.get('body')}\n\n"
            return output
    except Exception as e:
        print(f" [TOOL ERROR] News search failed: {e}")
        return f"Error fetching news: {e}"

if __name__ == '__main__':
    print(get_news("latest news about space x"))
