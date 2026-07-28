import requests
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("WEATHER_API_KEY")

url = f"http://api.openweathermap.org/data/2.5/weather?q=Ghaziabad&appid={api_key}&units=metric"
response = requests.get(url)
print(response.status_code)
print(response.json())
