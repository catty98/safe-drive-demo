import math
import threading
import time

from services.route_service import (
    find_region_by_progress,
    find_route_progress,
)
from services.traffic_service import analyze_route_traffic


SUPPORTED_WEATHER_VALUES = {"맑음", "흐림", "비", "안개", "눈"}


class LiveDriveController:
    """기존 UI에 실시간 위치·교통·휴식 상태만 연결하는 관리자입니다."""

    def __init__(
        self,
        route,
        regions,
        initial_weather,
        weather_loader=None,
        guidance_loader=None,
        refresh_seconds=300,
        rest_confirm_seconds=600,
        rest_alert_seconds=3600,
    ):
        self.route = route
        self.regions = [dict(region) for region in regions]
        self.current_weather = initial_weather
        self.weather_loader = weather_loader
        self.guidance_loader = guidance_loader

        self.refresh_seconds = float(refresh_seconds)
        self.rest_confirm_seconds = float(
            rest_confirm_seconds
        )
        self.rest_alert_seconds = float(
            rest_alert_seconds
        )

        now = time.monotonic()
        self.driving_started_at = now
        self.last_moving_at = now
        self.last_refresh_at = now
        self.last_weather_refresh_at = None

        self.last_location = None
        self.current_progress = None
        self.current_region = None
        self.is_resting = False
        self.rest_alert_sent = False

        self._stop_event = threading.Event()
        self._refresh_thread = None

    @staticmethod
    def _normalize_weather_result(loaded_weather):
        """날씨 API 반환값을 TAAS 날씨 분류 문자열로 변환합니다."""

        if isinstance(loaded_weather, dict):
            weather = (
                loaded_weather.get("weather")
                or loaded_weather.get("condition")
                or loaded_weather.get("category")
            )
        else:
            weather = loaded_weather

        weather = str(weather or "").strip()

        if weather not in SUPPORTED_WEATHER_VALUES:
            raise ValueError(
                "날씨 API 결과는 맑음, 흐림, 비, 안개, 눈 중 "
                f"하나여야 합니다: {weather or '빈 값'}"
            )

        return weather

    @staticmethod
    def _distance_m(previous, current):
        mean_latitude = math.radians(
            (
                float(previous["latitude"])
                + float(current["latitude"])
            )
            / 2
        )
        meters_per_longitude = (
            111_320 * math.cos(mean_latitude)
        )
        meters_per_latitude = 110_540

        dx = (
            float(current["longitude"])
            - float(previous["longitude"])
        ) * meters_per_longitude
        dy = (
            float(current["latitude"])
            - float(previous["latitude"])
        ) * meters_per_latitude

        return math.hypot(dx, dy)

    def update_location(
        self,
        longitude,
        latitude,
        speed_kmh=None,
    ):
        """UI가 새 GPS 좌표를 받을 때마다 호출합니다."""

        now = time.monotonic()
        current_location = {
            "longitude": float(longitude),
            "latitude": float(latitude),
            "speed_kmh": (
                None
                if speed_kmh is None
                else float(speed_kmh)
            ),
        }

        moved_m = 0.0

        if self.last_location is not None:
            moved_m = self._distance_m(
                self.last_location,
                current_location,
            )

        speed_is_moving = (
            current_location["speed_kmh"] is not None
            and current_location["speed_kmh"] >= 5
        )
        distance_is_moving = moved_m >= 20
        is_moving = speed_is_moving or distance_is_moving

        if is_moving:
            if self.is_resting:
                self.driving_started_at = now
                self.rest_alert_sent = False

            self.is_resting = False
            self.last_moving_at = now
        elif (
            not self.is_resting
            and now - self.last_moving_at
            >= self.rest_confirm_seconds
        ):
            self.is_resting = True
            self.driving_started_at = now
            self.rest_alert_sent = False

        self.last_location = current_location
        self.current_progress = find_route_progress(
            route=self.route,
            longitude=longitude,
            latitude=latitude,
        )
        self.current_region = find_region_by_progress(
            regions=self.regions,
            route_progress_m=self.current_progress[
                "route_progress_m"
            ],
        )

        continuous_seconds = (
            0.0
            if self.is_resting
            else now - self.driving_started_at
        )
        rest_alert = (
            continuous_seconds >= self.rest_alert_seconds
            and not self.rest_alert_sent
        )

        if rest_alert:
            self.rest_alert_sent = True

        return {
            "location": dict(current_location),
            "progress": dict(self.current_progress),
            "region": (
                dict(self.current_region)
                if self.current_region
                else None
            ),
            "is_resting": self.is_resting,
            "continuous_driving_minutes": round(
                continuous_seconds / 60,
                1,
            ),
            "rest_alert": rest_alert,
        }

    def weather_refresh_due(self):
        return (
            self.last_location is not None
            and (
                self.last_weather_refresh_at is None
                or time.monotonic() - self.last_weather_refresh_at
                >= self.refresh_seconds
            )
        )

    def refresh_weather(self, force=False):
        """현재 GPS 위치의 날씨만 갱신합니다. 교통 분석은 실행하지 않습니다."""

        if self.last_location is None:
            raise RuntimeError(
                "현재 위치가 없어 실시간 날씨를 갱신할 수 없습니다."
            )

        if not force and not self.weather_refresh_due():
            return None

        previous_weather = self.current_weather
        weather_error = None
        weather_source = "previous"

        if callable(self.weather_loader):
            try:
                loaded_weather = self.weather_loader(
                    self.last_location["longitude"],
                    self.last_location["latitude"],
                )

                if loaded_weather is not None:
                    self.current_weather = self._normalize_weather_result(
                        loaded_weather
                    )
                    weather_source = "api"
            except Exception as exc:
                weather_error = str(exc)
                self.current_weather = previous_weather

        self.last_weather_refresh_at = time.monotonic()

        return {
            "previous_weather": previous_weather,
            "weather": self.current_weather,
            "weather_changed": previous_weather != self.current_weather,
            "weather_source": weather_source,
            "weather_error": weather_error,
        }

    def environment_refresh_due(self):
        return (
            self.last_location is not None
            and time.monotonic() - self.last_refresh_at
            >= self.refresh_seconds
        )

    def refresh_environment(
        self,
        force=False,
        progress_callback=None,
    ):
        """5분마다 날씨와 남은 경로의 교통정보를 갱신합니다."""

        if self.last_location is None:
            raise RuntimeError(
                "현재 위치가 없어 실시간 정보를 갱신할 수 없습니다."
            )

        if not force and not self.environment_refresh_due():
            return None

        weather_result = self.refresh_weather(force=True) or {}
        previous_weather = weather_result.get(
            "previous_weather",
            self.current_weather,
        )
        weather_source = weather_result.get(
            "weather_source",
            "previous",
        )
        weather_error = weather_result.get("weather_error")

        start_route_distance_m = 0.0

        if self.current_progress:
            start_route_distance_m = float(
                self.current_progress.get(
                    "route_progress_m",
                    0,
                )
            )

        traffic_analysis = analyze_route_traffic(
            route=self.route,
            regions=self.regions,
            start_route_distance_m=start_route_distance_m,
            progress_callback=progress_callback,
        )

        self.regions = traffic_analysis["regions"]

        guidance_messages = []
        guidance_error = None

        if callable(self.guidance_loader):
            try:
                loaded_messages = self.guidance_loader(
                    regions=[
                        dict(region)
                        for region in self.regions
                    ],
                    weather=self.current_weather,
                    traffic_analysis=traffic_analysis,
                    current_progress=(
                        dict(self.current_progress)
                        if self.current_progress
                        else None
                    ),
                )
                guidance_messages = list(
                    loaded_messages or []
                )
            except Exception as exc:
                guidance_error = str(exc)

        self.last_refresh_at = time.monotonic()

        return {
            "previous_weather": previous_weather,
            "weather": self.current_weather,
            "weather_changed": (
                previous_weather != self.current_weather
            ),
            "weather_source": weather_source,
            "weather_error": weather_error,
            "traffic": traffic_analysis,
            "messages": guidance_messages,
            "guidance_error": guidance_error,
        }

    def start_auto_refresh(
        self,
        on_refresh=None,
        on_error=None,
        check_interval_seconds=1.0,
        force_first_refresh=False,
    ):
        """별도 스레드에서 갱신 시각을 확인하고 자동 갱신합니다."""

        if (
            self._refresh_thread is not None
            and self._refresh_thread.is_alive()
        ):
            return

        self._stop_event.clear()

        def worker():
            if force_first_refresh and self.last_location is not None:
                try:
                    result = self.refresh_environment(force=True)
                    if result is not None and callable(on_refresh):
                        on_refresh(result)
                except Exception as exc:
                    if callable(on_error):
                        on_error(exc)

            while not self._stop_event.wait(
                max(0.2, float(check_interval_seconds))
            ):
                if not self.environment_refresh_due():
                    continue

                try:
                    result = self.refresh_environment()
                    if result is not None and callable(on_refresh):
                        on_refresh(result)
                except Exception as exc:
                    if callable(on_error):
                        on_error(exc)

        self._refresh_thread = threading.Thread(
            target=worker,
            name="live-drive-refresh",
            daemon=True,
        )
        self._refresh_thread.start()

    def stop_auto_refresh(self):
        """자동 갱신 스레드를 안전하게 종료합니다."""

        self._stop_event.set()

        if (
            self._refresh_thread is not None
            and self._refresh_thread.is_alive()
            and threading.current_thread()
            is not self._refresh_thread
        ):
            self._refresh_thread.join(timeout=3)

        self._refresh_thread = None

