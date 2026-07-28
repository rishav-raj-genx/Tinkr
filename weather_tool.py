import os
import requests
from dotenv import load_dotenv

load_dotenv()

def get_weather(location: str) -> str:
    """
    Fetches the current weather for a given location using OpenWeatherMap.
    """
    api_key = os.getenv("WEATHER_API_KEY")
    if not api_key:
        return "Error: Weather API key not configured."
        
    print(f"\n [TOOL] Fetching weather for: {location}")
    url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units=metric"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            weather_desc = data['weather'][0]['description']
            temp = data['main']['temp']
            feels_like = data['main']['feels_like']
            humidity = data['main']['humidity']
            wind_speed = data['wind']['speed']
            
            return (f"Weather in {location}: {weather_desc}. "
                    f"Temperature: {temp}°C (feels like {feels_like}°C). "
                    f"Humidity: {humidity}%. Wind speed: {wind_speed} m/s.")
        elif response.status_code == 404:
            return f"Location '{location}' not found."
        else:
            return f"Failed to fetch weather. Status code: {response.status_code}"
    except Exception as e:
        print(f" [TOOL ERROR] Weather API failed: {e}")
        return f"Error fetching weather: {str(e)}"
