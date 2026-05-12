import ast
import json
import math
import os
import re
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

load_dotenv()


_WEATHER_CODE_LABELS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "react-agent/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _geocode_location(location: str) -> dict | None:
    params = urllib.parse.urlencode(
        {
            "name": location,
            "count": 1,
            "language": "en",
            "format": "json",
        }
    )
    url = f"https://geocoding-api.open-meteo.com/v1/search?{params}"
    data = _http_get_json(url)
    results = data.get("results") or []
    return results[0] if results else None


def _fetch_current_weather(latitude: float, longitude: float) -> dict:
    params = urllib.parse.urlencode(
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,wind_speed_10m,weather_code",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        }
    )
    url = f"https://api.open-meteo.com/v1/forecast?{params}"
    return _http_get_json(url)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"p", "br", "div", "li", "section", "article", "header", "footer"}:
            self._chunks.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if text:
            self._chunks.append(text + " ")

    def text(self) -> str:
        raw = "".join(self._chunks)
        cleaned = re.sub(r"[ \t]+", " ", raw)
        cleaned = re.sub(r"\n{2,}", "\n", cleaned)
        return cleaned.strip()


def _safe_eval(expression: str) -> float:
    allowed_names = {
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "pi": math.pi,
        "e": math.e,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "sqrt": math.sqrt,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
    }
    node = ast.parse(expression, mode="eval")

    def _eval(n):
        if isinstance(n, ast.Expression):
            return _eval(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp):
            left = _eval(n.left)
            right = _eval(n.right)
            if isinstance(n.op, ast.Add):
                return left + right
            if isinstance(n.op, ast.Sub):
                return left - right
            if isinstance(n.op, ast.Mult):
                return left * right
            if isinstance(n.op, ast.Div):
                return left / right
            if isinstance(n.op, ast.FloorDiv):
                return left // right
            if isinstance(n.op, ast.Mod):
                return left % right
            if isinstance(n.op, ast.Pow):
                return left ** right
            raise ValueError("Operator not allowed")
        if isinstance(n, ast.UnaryOp):
            operand = _eval(n.operand)
            if isinstance(n.op, ast.UAdd):
                return +operand
            if isinstance(n.op, ast.USub):
                return -operand
            raise ValueError("Operator not allowed")
        if isinstance(n, ast.Call):
            if not isinstance(n.func, ast.Name) or n.func.id not in allowed_names:
                raise ValueError("Function not allowed")
            args = [_eval(arg) for arg in n.args]
            return allowed_names[n.func.id](*args)
        if isinstance(n, ast.Name) and n.id in allowed_names:
            return allowed_names[n.id]
        raise ValueError("Expression not allowed")

    return float(_eval(node))


_UNIT_FACTORS = {
    "m": 1.0,
    "km": 1000.0,
    "cm": 0.01,
    "mm": 0.001,
    "in": 0.0254,
    "ft": 0.3048,
    "yd": 0.9144,
    "mi": 1609.344,
    "g": 1.0,
    "kg": 1000.0,
    "lb": 453.59237,
    "oz": 28.349523125,
}


def _normalize_unit(unit: str) -> str:
    unit = unit.strip().lower()
    aliases = {
        "meter": "m",
        "meters": "m",
        "metre": "m",
        "metres": "m",
        "kilometer": "km",
        "kilometers": "km",
        "kilometre": "km",
        "kilometres": "km",
        "centimeter": "cm",
        "centimeters": "cm",
        "millimeter": "mm",
        "millimeters": "mm",
        "inch": "in",
        "inches": "in",
        "foot": "ft",
        "feet": "ft",
        "yard": "yd",
        "yards": "yd",
        "mile": "mi",
        "miles": "mi",
        "gram": "g",
        "grams": "g",
        "kilogram": "kg",
        "kilograms": "kg",
        "pound": "lb",
        "pounds": "lb",
        "ounce": "oz",
        "ounces": "oz",
        "celsius": "c",
        "fahrenheit": "f",
        "kelvin": "k",
    }
    return aliases.get(unit, unit)


def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    if from_unit == to_unit:
        return value
    if from_unit == "c":
        c = value
    elif from_unit == "f":
        c = (value - 32) * 5 / 9
    elif from_unit == "k":
        c = value - 273.15
    else:
        raise ValueError("Unsupported temperature unit")

    if to_unit == "c":
        return c
    if to_unit == "f":
        return c * 9 / 5 + 32
    if to_unit == "k":
        return c + 273.15
    raise ValueError("Unsupported temperature unit")


def _tinyfish_config_error() -> str | None:
    if os.getenv("TINYFISH_API_KEY"):
        return None
    return "TinyFish is not configured. Set TINYFISH_API_KEY in the environment."


def _tinyfish_client():
    try:
        from tinyfish import TinyFish
    except ImportError as exc:
        raise RuntimeError(
            "TinyFish SDK is not installed. Run `uv sync` to install dependencies."
        ) from exc
    return TinyFish()


def _to_jsonable(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list | tuple):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if hasattr(value, "__dict__"):
        return _to_jsonable(
            {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        )
    return str(value)


def _truncate_text(text: str | None, max_chars: int) -> str | None:
    if text is None or len(text) <= max_chars:
        return text
    return text[:max_chars] + "..."


@tool
def get_weather(location: str) -> str:
    """Get the current weather for a location via Open-Meteo."""
    location = location.strip()
    if not location:
        return "Please provide a location."

    try:
        place = _geocode_location(location)
        if not place:
            return f"Could not find a location match for '{location}'."

        data = _fetch_current_weather(place["latitude"], place["longitude"])
        current = data.get("current") or {}
        temp = current.get("temperature_2m")
        wind = current.get("wind_speed_10m")
        code = current.get("weather_code")
        label = _WEATHER_CODE_LABELS.get(code, "Unknown conditions")

        name_parts = [place.get("name")]
        if place.get("admin1"):
            name_parts.append(place["admin1"])
        if place.get("country"):
            name_parts.append(place["country"])
        name = ", ".join(part for part in name_parts if part)

        if temp is None:
            return f"Weather data is unavailable for {name}."

        detail_bits = [f"{temp}°F", label]
        if wind is not None:
            detail_bits.append(f"wind {wind} mph")
        detail = ", ".join(detail_bits)
        return f"Current weather in {name}: {detail}."
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"Weather lookup failed: {exc}"


@tool
def get_time(timezone_name: str | None = None) -> str:
    """Get the current time in a specific timezone (IANA name or UTC offset)."""
    if not timezone_name:
        now = datetime.now().astimezone()
        return now.strftime("Local time: %Y-%m-%d %H:%M:%S %Z%z")

    tz_input = timezone_name.strip()
    try:
        tz = ZoneInfo(tz_input)
        now = datetime.now(tz)
        return now.strftime(f"Time in {tz_input}: %Y-%m-%d %H:%M:%S %Z%z")
    except Exception:
        match = re.match(r"^([+-])(\d{2}):?(\d{2})$", tz_input)
        if not match:
            return (
                "Unsupported timezone. Use an IANA name like 'America/Los_Angeles' "
                "or a UTC offset like '+02:00'."
            )
        sign, hours, minutes = match.groups()
        offset = int(hours) * 60 + int(minutes)
        if sign == "-":
            offset = -offset
        tz = timezone(timedelta(minutes=offset))
        now = datetime.now(tz)
        return now.strftime(f"Time in UTC{tz_input}: %Y-%m-%d %H:%M:%S %Z%z")


@tool
def calculator(expression: str) -> str:
    """Safely evaluate a math expression."""
    try:
        value = _safe_eval(expression)
        return f"{value}"
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"Could not evaluate expression: {exc}"


@tool
def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Convert between common length, weight, and temperature units."""
    from_unit = _normalize_unit(from_unit)
    to_unit = _normalize_unit(to_unit)

    temp_units = {"c", "f", "k"}
    if from_unit in temp_units or to_unit in temp_units:
        if from_unit not in temp_units or to_unit not in temp_units:
            return "Temperature conversions must use C, F, or K."
        converted = _convert_temperature(float(value), from_unit, to_unit)
        return f"{value} {from_unit} = {converted:.4g} {to_unit}"

    if from_unit not in _UNIT_FACTORS or to_unit not in _UNIT_FACTORS:
        return (
            "Unsupported units. Supported: m, km, cm, mm, in, ft, yd, mi, "
            "g, kg, lb, oz, C, F, K."
        )
    base_value = float(value) * _UNIT_FACTORS[from_unit]
    converted = base_value / _UNIT_FACTORS[to_unit]
    return f"{value} {from_unit} = {converted:.4g} {to_unit}"


@tool
def page_reader(url: str, max_chars: int = 4000) -> str:
    """Fetch a web page and return cleaned text."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "react-agent/0.1"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read()
        text = ""
        if "text/plain" in content_type:
            text = raw.decode("utf-8", errors="replace")
        else:
            html = raw.decode("utf-8", errors="replace")
            parser = _HTMLTextExtractor()
            parser.feed(html)
            text = parser.text()
        text = text.strip()
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text or "No text content found."
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"Page fetch failed: {exc}"


@tool
def tinyfish_search(
    query: str, location: str = "US", language: str = "en"
) -> dict | str:
    """Search the web with TinyFish and return ranked results."""
    config_error = _tinyfish_config_error()
    if config_error:
        return config_error

    try:
        result = _tinyfish_client().search.query(
            query=query,
            location=location,
            language=language,
        )
        return _to_jsonable(result)
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"TinyFish search failed: {exc}"


@tool
def tinyfish_fetch(
    urls: list[str], format: str = "markdown", max_chars: int = 6000
) -> dict | str:
    """Render URLs with TinyFish and return clean extracted page content."""
    config_error = _tinyfish_config_error()
    if config_error:
        return config_error

    try:
        result = _tinyfish_client().fetch.get_contents(urls=urls, format=format)
        pages = []
        for page in getattr(result, "results", []) or []:
            pages.append(
                {
                    "url": getattr(page, "url", None),
                    "final_url": getattr(page, "final_url", None),
                    "title": getattr(page, "title", None),
                    "description": getattr(page, "description", None),
                    "language": getattr(page, "language", None),
                    "text": _truncate_text(getattr(page, "text", None), max_chars),
                }
            )
        errors = [_to_jsonable(error) for error in getattr(result, "errors", []) or []]
        return {"results": pages, "errors": errors}
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"TinyFish fetch failed: {exc}"


@tool
def tinyfish_agent(url: str, goal: str) -> dict | str:
    """Use TinyFish to execute a goal-driven workflow on a real website."""
    config_error = _tinyfish_config_error()
    if config_error:
        return config_error

    try:
        result = _tinyfish_client().agent.run(url=url, goal=goal)
        data = _to_jsonable(result)
        if isinstance(data, dict):
            return {
                "run_id": data.get("run_id") or data.get("id"),
                "status": data.get("status"),
                "result": data.get("result_json") or data.get("result"),
                "error": data.get("error"),
            }
        return {"result": data}
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"TinyFish agent failed: {exc}"


@tool
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email via SMTP. Requires SMTP_* env configuration."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM") or smtp_user
    smtp_tls = os.getenv("SMTP_TLS", "true").lower() in {"1", "true", "yes"}

    if not smtp_host or not smtp_user or not smtp_pass or not smtp_from:
        return (
            "SMTP is not configured. Set SMTP_HOST, SMTP_PORT, SMTP_USER, "
            "SMTP_PASS, and SMTP_FROM in the environment."
        )

    message = EmailMessage()
    message["From"] = smtp_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            if smtp_tls:
                server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(message)
        return f"Email sent to {to}."
    except Exception as exc:  # noqa: BLE001 - best-effort tool
        return f"Email failed: {exc}"


tavily_search = TavilySearch(max_results=5)

TOOLS = [
    get_weather,
    get_time,
    calculator,
    unit_converter,
    page_reader,
    tinyfish_search,
    tinyfish_fetch,
    tinyfish_agent,
    send_email,
    tavily_search,
]
