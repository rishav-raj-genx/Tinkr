from duckduckgo_search import DDGS

def search_web(query: str) -> str:
    """
    Searches the web using DuckDuckGo and returns a summary of the results.
    """
    print(f"\n🌐 [TOOL] Searching web for: {query}")
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
        print(f"❌ [TOOL ERROR] Web search failed: {e}")
        return f"Error searching the web: {e}"

if __name__ == '__main__':
    print(search_web("latest news about space x"))
