import json
from urllib.parse import quote

import requests

from config import config
from logger import get_logger

logger = get_logger("weather_tool")


_WMO_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def _get_weather_open_meteo(location: str) -> str:
    """Keyless fallback using Open-Meteo geocoding + forecast API."""
    encoded = quote(location.strip())
    geo_resp = requests.get(
        f"https://geocoding-api.open-meteo.com/v1/search?name={encoded}&count=1",
        timeout=10.0,
    )
    if geo_resp.status_code != 200:
        return json.dumps({"error": f"Geocoding failed with status {geo_resp.status_code}"})
    results = geo_resp.json().get("results") or []
    if not results:
        return json.dumps({"error": f"Location '{location}' not found."})

    place = results[0]
    lat, lon = place["latitude"], place["longitude"]
    resolved_name = place.get("name", location)

    wx_resp = requests.get(
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,weather_code&hourly=temperature_2m,weather_code&forecast_days=1",
        timeout=10.0,
    )
    if wx_resp.status_code != 200:
        return json.dumps({"error": f"Failed to fetch weather. Status code: {wx_resp.status_code}"})

    wx = wx_resp.json()
    current = wx.get("current", {})
    curr_temp = current.get("temperature_2m", "Unknown")
    curr_desc = _WMO_CODES.get(current.get("weather_code"), "clear")

    result_str = f"Current weather in {resolved_name}: {curr_temp}°C and {curr_desc}."
    hourly = wx.get("hourly", {})
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    codes = hourly.get("weather_code") or []
    if len(times) >= 4 and len(temps) >= 4 and len(codes) >= 4:
        # Pick 2 upcoming 3-hour slots from the middle of the forecast array
        result_str += " Forecast for the next few hours: "
        for idx in (3, 6):
            if idx < len(times):
                time_only = times[idx].split("T")[1][:5]
                desc = _WMO_CODES.get(codes[idx], "clear")
                result_str += f"At {time_only}, {temps[idx]}°C ({desc}). "
    return result_str


def get_weather(location: str) -> str:
    """Fetches the current weather and forecast for a given location.

    Tries OpenWeatherMap when WEATHER_API_KEY is configured and falls back
    to Open-Meteo (keyless) if the key is missing or rejected (e.g. 401).
    """
    api_key = config.WEATHER_API_KEY
    logger.info("Fetching weather for: %s", location)
    encoded_location = quote(location.strip())

    if api_key:
        url_current = f"https://api.openweathermap.org/data/2.5/weather?q={encoded_location}&appid={api_key}&units=metric"
        url_forecast = f"https://api.openweathermap.org/data/2.5/forecast?q={encoded_location}&appid={api_key}&units=metric"
        try:
            resp_curr = requests.get(url_current, timeout=10.0)
            if resp_curr.status_code == 404:
                return json.dumps({"error": f"Location '{location}' not found."})
            if resp_curr.status_code == 200:
                data_curr = resp_curr.json()
                resp_fore = requests.get(url_forecast, timeout=10.0)
                forecast_list = []
                if resp_fore.status_code == 200:
                    data_fore = resp_fore.json()
                    for item in data_fore.get("list", [])[:4]:
                        forecast_list.append({
                            "time": item.get("dt_txt"),
                            "temp": item["main"]["temp"],
                            "description": item["weather"][0]["description"],
                        })
                current_temp = data_curr.get("main", {}).get("temp", "Unknown")
                current_desc = data_curr.get("weather", [{}])[0].get("description", "Unknown")
                result_str = f"Current weather in {data_curr.get('name', location)}: {current_temp}°C and {current_desc}."
                if forecast_list:
                    result_str += " Forecast for the next few hours: "
                    for f in forecast_list[:2]:
                        time_only = f["time"].split()[1][:5]
                        result_str += f"At {time_only}, {f['temp']}°C ({f['description']}). "
                return result_str
            logger.warning("OpenWeatherMap returned %s; falling back to Open-Meteo", resp_curr.status_code)
        except Exception as e:
            logger.warning("OpenWeatherMap failed (%s); falling back to Open-Meteo", e)

    try:
        return _get_weather_open_meteo(location)
    except Exception as e:
        logger.error("Weather API request failed: %s", e)
        return json.dumps({"error": f"Error fetching weather: {e!s}"})
