from duckduckgo_search import DDGS

try:
    with DDGS() as ddgs:
        results = list(ddgs.news("latest news about space x", max_results=3))
        print("News:", results)
except Exception as e:
    print(e)
