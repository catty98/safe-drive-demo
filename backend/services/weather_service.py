import requests


OPEN_METEO_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
)


class WeatherServiceError(RuntimeError):
    """현재 날씨 API 조회 실패를 나타냅니다."""


def _weather_code_to_category(
    weather_code,
    rain=0.0,
    showers=0.0,
    snowfall=0.0,
):
    """WMO 날씨 코드를 TAAS의 5개 날씨 분류로 변환합니다."""

    try:
        code = int(weather_code)
    except (TypeError, ValueError) as exc:
        raise WeatherServiceError(
            f"날씨 코드를 해석할 수 없습니다: {weather_code}"
        ) from exc

    rain_amount = float(rain or 0) + float(showers or 0)
    snowfall_amount = float(snowfall or 0)

    snow_codes = {71, 73, 75, 77, 85, 86}
    fog_codes = {45, 48}
    rain_codes = {
        51, 53, 55, 56, 57,
        61, 63, 65, 66, 67,
        80, 81, 82, 95, 96, 99,
    }

    if snowfall_amount > 0 or code in snow_codes:
        return "눈"

    if code in fog_codes:
        return "안개"

    if rain_amount > 0 or code in rain_codes:
        return "비"

    if code == 0:
        return "맑음"

    if code in {1, 2, 3}:
        return "흐림"

    raise WeatherServiceError(
        f"지원하지 않는 WMO 날씨 코드입니다: {code}"
    )


def load_current_weather(longitude, latitude):
    """현재 GPS 좌표의 날씨를 조회하여 TAAS 분류값으로 반환합니다."""

    params = {
        "latitude": float(latitude),
        "longitude": float(longitude),
        "current": (
            "weather_code,rain,showers,snowfall,"
            "temperature_2m"
        ),
        "timezone": "Asia/Seoul",
    }

    try:
        response = requests.get(
            OPEN_METEO_FORECAST_URL,
            params=params,
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise WeatherServiceError(
            f"날씨 API 서버에 연결하지 못했습니다: {exc}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise WeatherServiceError(
            "날씨 API 응답을 JSON으로 해석하지 못했습니다."
        ) from exc

    current = data.get("current") or {}
    weather_code = current.get("weather_code")

    if weather_code is None:
        raise WeatherServiceError(
            "날씨 API 응답에 current.weather_code가 없습니다."
        )

    weather = _weather_code_to_category(
        weather_code=weather_code,
        rain=current.get("rain", 0),
        showers=current.get("showers", 0),
        snowfall=current.get("snowfall", 0),
    )

    return {
        "weather": weather,
        "weather_code": int(weather_code),
        "temperature_c": current.get("temperature_2m"),
        "observed_at": current.get("time"),
        "provider": "open-meteo",
    }
