import requests
import os
from dotenv import load_dotenv
import json

load_dotenv()
api_key = os.getenv("WEATHER_API_KEY")
location = "Ghaziabad"

# Current weather
url_current = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
resp_curr = requests.get(url_current).json()

# Forecast
url_forecast = f"http://api.openweathermap.org/data/2.5/forecast?q={location}&appid={api_key}&units=metric"
resp_fore = requests.get(url_forecast).json()

# Simplify forecast
forecast_list = []
if 'list' in resp_fore:
    for item in resp_fore['list'][:4]: # Next 12 hours
        forecast_list.append({
            "time": item.get('dt_txt'),
            "temp": item['main']['temp'],
            "description": item['weather'][0]['description']
        })

output = {
    "current": resp_curr,
    "forecast": forecast_list
}
print(json.dumps(output, indent=2))
