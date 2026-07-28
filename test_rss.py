import requests
import xml.etree.ElementTree as ET
import urllib.parse

def get_news_rss(query):
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        root = ET.fromstring(response.text)
        channel = root.find('channel')
        
        results = []
        for item in channel.findall('item')[:3]:
            title = item.find('title').text
            pub_date = item.find('pubDate').text
            results.append({"title": title, "date": pub_date})
            
        return results
    except Exception as e:
        return str(e)

print(get_news_rss("latest news about space x"))
