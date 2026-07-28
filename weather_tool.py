import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def get_weather(location: str) -> str:
    """
    Fetches the current weather and forecast for a given location.
    Returns a JSON string so the AI can parse and provide brief or detailed answers.
    """
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return json.dumps({"error": "Weather API key not configured."})
        
    print(f"\n [TOOL] Fetching weather for: {location}")
    url_current = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    url_forecast = f"http://api.openweathermap.org/data/2.5/forecast?q={location}&appid={api_key}&units=metric"
    
    try:
        resp_curr = requests.get(url_current)
        if resp_curr.status_code == 404:
            return json.dumps({"error": f"Location '{location}' not found."})
        elif resp_curr.status_code != 200:
            return json.dumps({"error": f"Failed to fetch weather. Status code: {resp_curr.status_code}"})
            
        data_curr = resp_curr.json()
        
        # Try to get forecast
        resp_fore = requests.get(url_forecast)
        forecast_list = []
        if resp_fore.status_code == 200:
            data_fore = resp_fore.json()
            if 'list' in data_fore:
                for item in data_fore['list'][:4]: # next 12 hours
                    forecast_list.append({
                        "time": item.get('dt_txt'),
                        "temp": item['main']['temp'],
                        "description": item['weather'][0]['description']
                    })
        
        current_temp = data_curr.get('main', {}).get('temp', 'Unknown')
        current_desc = data_curr.get('weather', [{}])[0].get('description', 'Unknown')
        
        result_str = f"Current weather in {data_curr.get('name', location)}: {current_temp}°C and {current_desc}."
        if forecast_list:
            result_str += " Forecast for the next few hours: "
            for f in forecast_list[:2]:
                time_only = f['time'].split()[1][:5]
                result_str += f"At {time_only}, {f['temp']}°C ({f['description']}). "
                
        return result_str
        
    except Exception as e:
        print(f" [TOOL ERROR] Weather API failed: {e}")
        return json.dumps({"error": f"Error fetching weather: {str(e)}"})
