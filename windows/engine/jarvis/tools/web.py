"""Internet: web/news search, read a web page, weather."""

from __future__ import annotations

import httpx

from ._win import clip
from .base import I, S, tool

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"}


def _ddgs():
    from ddgs import DDGS

    return DDGS()


@tool("web_search", "Search the internet for current information (facts, prices, scores, how-tos).",
      {"query": S("search query"), "max_results": I("default 6")}, ["query"])
def web_search(query: str, max_results: int = 6):
    results = _ddgs().text(query, max_results=max(1, min(int(max_results), 15)))
    return [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in results] or "no results"


@tool("news_search", "Latest news headlines on a topic (or top news if topic is empty).",
      {"topic": S("topic, e.g. 'India cricket', 'AI'"), "max_results": I("default 6")})
def news_search(topic: str = "top news India", max_results: int = 6):
    results = _ddgs().news(topic or "top news", max_results=max(1, min(int(max_results), 15)))
    return [{"title": r.get("title"), "source": r.get("source"), "date": r.get("date"), "url": r.get("url"),
             "summary": r.get("body")} for r in results] or "no news found"


@tool("read_webpage", "Fetch a web page and return its readable text (to summarize or answer from it).",
      {"url": S("page URL"), "max_chars": I("default 12000")}, ["url"])
def read_webpage(url: str, max_chars: int = 12000):
    from bs4 import BeautifulSoup

    if "://" not in url:
        url = "https://" + url
    resp = httpx.get(url, headers=UA, follow_redirects=True, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    main = soup.find("article") or soup.find("main") or soup.body or soup
    lines = [ln.strip() for ln in main.get_text("\n").splitlines()]
    text = "\n".join(ln for ln in lines if len(ln) > 1)
    return f"{title}\n\n{clip(text, int(max_chars))}"


_WMO = {0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "fog",
        51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
        71: "light snow", 73: "snow", 75: "heavy snow", 80: "rain showers", 81: "rain showers",
        82: "violent rain showers", 95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


def _locate(city: str) -> tuple[float, float, str]:
    if city:
        r = httpx.get("https://geocoding-api.open-meteo.com/v1/search",
                      params={"name": city, "count": 1}, timeout=15).json()
        if r.get("results"):
            g = r["results"][0]
            return g["latitude"], g["longitude"], f"{g['name']}, {g.get('country', '')}"
    r = httpx.get("https://ipapi.co/json/", headers=UA, timeout=15).json()
    return r["latitude"], r["longitude"], f"{r.get('city')}, {r.get('country_name')}"


@tool("weather", "Current weather and 3-day forecast for a city (or the user's location if empty).",
      {"city": S("city name, empty = current location")})
def weather(city: str = ""):
    lat, lon, place = _locate(city)
    data = httpx.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 3,
        "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
    }, timeout=15).json()
    cur = data["current"]
    daily = data["daily"]
    return {
        "place": place,
        "now": f"{cur['temperature_2m']}°C (feels {cur['apparent_temperature']}°C), "
               f"{_WMO.get(cur['weather_code'], 'weather code ' + str(cur['weather_code']))}, "
               f"humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']} km/h",
        "forecast": [
            f"{daily['time'][i]}: {daily['temperature_2m_min'][i]}–{daily['temperature_2m_max'][i]}°C, "
            f"{_WMO.get(daily['weather_code'][i], '')}, rain chance {daily['precipitation_probability_max'][i]}%"
            for i in range(len(daily["time"]))
        ],
    }
