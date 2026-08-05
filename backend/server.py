from threading import RLock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator

from analysis.live_drive_controller import LiveDriveController
from analysis.region_analysis import find_route_regions
from analysis.result_summary import create_user_messages
from analysis.risk_model_adapter import attach_risk_predictions
from services.geocoding import search_place
from services.route_service import (
    extract_route_coordinates,
    get_route_summary,
    request_route,
    summarize_route_road_types,
)
from services.traffic_service import analyze_route_traffic
from services.weather_service import load_current_weather
from services.taas_service import (
    get_current_time_band,
    load_preprocessed_road_data,
    load_preprocessed_time_data,
    load_preprocessed_type_data,
    load_preprocessed_weather_data,
    select_road_analysis,
    select_time_analysis,
    select_type_analysis,
    select_weather_analysis,
)


app = FastAPI(
    title="SAFE DRIVE API",
    version="1.2.0",
    description=(
        "TMAP 경로, 실시간 교통정보, 교통사고 통계와 "
        "주행 위치를 이용한 안전운전 분석 API"
    ),
)


# Flutter 앱에서 API를 호출할 수 있도록 허용합니다.
# 개발 단계에서는 전체 허용으로 두고,
# 실제 배포할 때는 허용 주소를 제한하는 것이 좋습니다.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RouteAnalysisRequest(BaseModel):
    origin: str = Field(
        min_length=1,
        description="출발지 또는 '현재 위치'",
        examples=["서울역"],
    )
    destination: str = Field(
        min_length=1,
        description="도착지",
        examples=["용인시 기흥구"],
    )
    weather: Literal[
        "맑음",
        "흐림",
        "비",
        "안개",
        "눈",
    ] = "맑음"

    origin_latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="현재 위치 위도",
        examples=[37.5547],
    )
    origin_longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="현재 위치 경도",
        examples=[126.9706],
    )

    @model_validator(mode="after")
    def validate_origin_coordinates(self):
        latitude_exists = self.origin_latitude is not None
        longitude_exists = self.origin_longitude is not None

        if latitude_exists != longitude_exists:
            raise ValueError(
                "현재 위치를 사용할 때는 "
                "origin_latitude와 origin_longitude를 모두 보내야 합니다."
            )

        return self


class RouteSummaryResponse(BaseModel):
    distance_km: float
    duration_minutes: float


class RouteAnalysisResponse(BaseModel):
    origin: dict
    destination: dict
    summary: RouteSummaryResponse
    weather: str
    current_time_band: str
    regions: list[dict]
    road_types: list[dict]
    messages: list[str]
    accident_statistics: dict[str, list[dict]]
    route_points: list[dict]


class StartDrivingRequest(BaseModel):
    refresh_seconds: float = Field(default=300, ge=30, le=3600)
    rest_confirm_seconds: float = Field(default=600, ge=60, le=3600)
    rest_alert_seconds: float = Field(default=3600, ge=300, le=14400)


class LocationUpdateRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    speed_kmh: float | None = Field(default=None, ge=0, le=400)
    force_refresh: bool = False


# 현재 개발 단계에서는 스마트폰 한 대만 연결한다고 가정합니다.
# 여러 사용자를 동시에 지원하려면 session_id별 저장 구조로 변경해야 합니다.
_state_lock = RLock()
_latest_route_context: dict | None = None
_live_controller: LiveDriveController | None = None
_last_live_refresh: dict | None = None


def dataframe_to_records(dataframe) -> list[dict]:
    """Pandas DataFrame을 JSON으로 반환 가능한 리스트로 변환합니다."""

    if dataframe is None or dataframe.empty:
        return []

    clean_dataframe = dataframe.copy()
    clean_dataframe = clean_dataframe.where(
        clean_dataframe.notna(),
        None,
    )

    return clean_dataframe.to_dict(orient="records")


def create_current_location_place(
    latitude: float,
    longitude: float,
) -> dict:
    return {
        "name": "현재 위치",
        "display_name": "현재 위치",
        "longitude": float(longitude),
        "latitude": float(latitude),
    }


def _build_live_messages(
    location_status: dict,
    refresh_result: dict | None,
) -> list[str]:
    """실시간 위치 상태와 교통 갱신 결과를 짧은 안내문으로 변환합니다."""

    messages: list[str] = []
    progress = location_status.get("progress") or {}
    region = location_status.get("region") or {}

    sido = str(region.get("시도", "")).strip()
    sigungu = str(region.get("시군구", "")).strip()
    region_name = " ".join(value for value in (sido, sigungu) if value)

    if region_name:
        messages.append(f"현재 {region_name} 구간을 주행 중입니다.")

    remaining_distance = progress.get("remaining_distance_km")
    remaining_minutes = progress.get("remaining_minutes")

    if remaining_distance is not None and remaining_minutes is not None:
        messages.append(
            f"남은 거리는 약 {remaining_distance}km, "
            f"예상 시간은 약 {remaining_minutes}분입니다."
        )

    distance_from_route = progress.get("distance_from_route_m")
    if distance_from_route is not None and float(distance_from_route) >= 100:
        messages.append(
            "안내 경로에서 벗어난 것으로 보입니다. "
            "현재 위치와 경로를 확인하세요."
        )

    if location_status.get("rest_alert"):
        messages.append(
            "연속 운전시간이 길어졌습니다. "
            "안전한 장소에서 휴식하세요."
        )

    if refresh_result:
        traffic = refresh_result.get("traffic") or {}
        congestion_segments = traffic.get("congestion_segments") or []

        if congestion_segments:
            first_segment = congestion_segments[0]
            road_name = str(first_segment.get("road_name", "")).strip()
            eta_minutes = first_segment.get("eta_minutes")
            congestion_name = str(
                first_segment.get("congestion_name", "혼잡")
            ).strip()

            if road_name and eta_minutes is not None:
                messages.append(
                    f"약 {eta_minutes}분 후 {road_name}에서 "
                    f"{congestion_name} 구간이 예상됩니다."
                )
            elif road_name:
                messages.append(
                    f"남은 경로의 {road_name}에서 "
                    f"{congestion_name} 구간이 확인됐습니다."
                )

    return messages


def analyze_route(
    origin_text: str,
    destination_text: str,
    weather: str,
    origin_latitude: float | None = None,
    origin_longitude: float | None = None,
) -> dict:
    """출발지 문자열 또는 GPS 좌표를 사용하여 경로를 분석합니다."""

    global _latest_route_context

    # 1. 출발지와 도착지 결정
    if origin_latitude is not None and origin_longitude is not None:
        origin = create_current_location_place(
            latitude=origin_latitude,
            longitude=origin_longitude,
        )
    else:
        origin = search_place(origin_text)

    destination = search_place(destination_text)

    # 2. TMAP 경로 검색
    route = request_route(
        origin=origin,
        destination=destination,
    )

    route_coordinates = extract_route_coordinates(route)
    route_points = [
        {
            "latitude": latitude,
            "longitude": longitude,
        }
        for longitude, latitude in route_coordinates
    ]

    summary = get_route_summary(route)

    # 3. 경로 통과지역 분석
    regions = find_route_regions(route)

    # 4. 실제 경로 기준 실시간 교통정보 분석
    traffic_analysis = analyze_route_traffic(
        route=route,
        regions=regions,
    )

    print("=== traffic_analysis 시작 ===")
    print(traffic_analysis)
    print("=== traffic_analysis 끝 ===")

    regions = traffic_analysis["regions"]

    route_sidos: list[str] = []

    for region in regions:
        sido = str(region.get("시도", "")).strip()
        if sido and sido not in route_sidos:
            route_sidos.append(sido)

    # 5. 경로 도로 종류 분석
    route_road_summary = summarize_route_road_types(route)

    recognized_road_types = [
        item["도로종류"]
        for item in route_road_summary
        if item.get("도로종류") != "기타"
    ]

    main_road_type = (
        recognized_road_types[0]
        if recognized_road_types
        else "기타"
    )

    road_data = load_preprocessed_road_data()
    route_road_result = select_road_analysis(
        road_long_df=road_data["long"],
        sidos=route_sidos,
    )

    if recognized_road_types:
        route_road_result = route_road_result[
            route_road_result["도로종류"].isin(recognized_road_types)
        ].copy()
    else:
        route_road_result = route_road_result.iloc[0:0]

    # 6. 사고유형 분석
    type_data = load_preprocessed_type_data()
    route_type_detail = select_type_analysis(
        type_long_df=type_data["detail_long"],
        sidos=route_sidos,
        min_accidents_for_severity=30,
    )

    # 7. 시간대 분석
    time_data = load_preprocessed_time_data()
    current_time_band = get_current_time_band()
    time_result = select_time_analysis(
        time_long_df=time_data["long"],
        time_band=current_time_band,
    )

    if time_result.empty:
        route_time_result = time_result.copy()
    else:
        route_time_result = time_result[
            time_result["시도"].isin(route_sidos)
        ].copy()

    # 8. 날씨별 사고 분석
    weather_data = load_preprocessed_weather_data()
    weather_result = select_weather_analysis(
        weather_long_df=weather_data["long"],
        weather=weather,
    )

    if weather_result.empty:
        route_weather_result = weather_result.copy()
    else:
        route_weather_result = weather_result[
            weather_result["시도"].isin(route_sidos)
        ].copy()

    # 9. 예측 모델 연결
    regions = attach_risk_predictions(
        regions=regions,
        weather=weather,
        current_time_band=current_time_band,
        main_road_type=main_road_type,
    )

    # 10. 사용자용 안전안내 문장 생성
    messages = create_user_messages(
        summary=summary,
        regions=regions,
        route_road_summary=route_road_summary,
        route_road_result=route_road_result,
        route_type_detail=route_type_detail,
        route_time_result=route_time_result,
        current_time_band=current_time_band,
        route_weather_result=route_weather_result,
        weather=weather,
        congestion_segments=traffic_analysis.get(
            "congestion_segments",
            [],
        ),
        traffic_status=traffic_analysis,
    )

    with _state_lock:
        _latest_route_context = {
            "route": route,
            "regions": [dict(region) for region in regions],
            "weather": weather,
            "origin": dict(origin),
            "destination": dict(destination),
            "summary": dict(summary),
            "traffic_analysis": traffic_analysis,
        }

    return {
        "origin": origin,
        "destination": destination,
        "summary": summary,
        "weather": weather,
        "current_time_band": current_time_band,
        "regions": regions,
        "road_types": route_road_summary,
        "messages": messages,
        "route_points": route_points,
        "accident_statistics": {
            "road": dataframe_to_records(route_road_result),
            "type": dataframe_to_records(route_type_detail),
            "time": dataframe_to_records(route_time_result),
            "weather": dataframe_to_records(route_weather_result),
        },
    }


@app.get("/")
def root():
    return {
        "service": "SAFE DRIVE API",
        "status": "running",
        "version": "1.2.0",
    }


@app.get("/health")
def health():
    with _state_lock:
        route_ready = _latest_route_context is not None
        driving_active = _live_controller is not None

    return {
        "status": "ok",
        "route_ready": route_ready,
        "driving_active": driving_active,
    }


@app.post(
    "/analyze-route",
    response_model=RouteAnalysisResponse,
)
def analyze_route_endpoint(request: RouteAnalysisRequest):
    try:
        return analyze_route(
            origin_text=request.origin.strip(),
            destination_text=request.destination.strip(),
            weather=request.weather,
            origin_latitude=request.origin_latitude,
            origin_longitude=request.origin_longitude,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"데이터 파일 오류: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"경로 분석 중 오류가 발생했습니다: {exc}",
        ) from exc


@app.post("/start-driving")
def start_driving(request: StartDrivingRequest):
    """가장 최근에 분석한 경로로 실시간 주행 세션을 시작합니다."""

    global _live_controller, _last_live_refresh

    with _state_lock:
        if _latest_route_context is None:
            raise HTTPException(
                status_code=409,
                detail="먼저 /analyze-route로 경로를 분석해야 합니다.",
            )

        if _live_controller is not None:
            _live_controller.stop_auto_refresh()

        _live_controller = LiveDriveController(
            route=_latest_route_context["route"],
            regions=_latest_route_context["regions"],
            initial_weather=_latest_route_context["weather"],
            weather_loader=load_current_weather,
            refresh_seconds=request.refresh_seconds,
            rest_confirm_seconds=request.rest_confirm_seconds,
            rest_alert_seconds=request.rest_alert_seconds,
        )
        _last_live_refresh = None

    return {
        "status": "started",
        "refresh_seconds": request.refresh_seconds,
        "rest_confirm_seconds": request.rest_confirm_seconds,
        "rest_alert_seconds": request.rest_alert_seconds,
    }


@app.post("/update-location")
def update_location(request: LocationUpdateRequest):
    """Flutter가 전달한 현재 GPS 위치로 주행 상태를 갱신합니다."""

    global _last_live_refresh

    with _state_lock:
        controller = _live_controller

    if controller is None:
        raise HTTPException(
            status_code=409,
            detail="먼저 /start-driving을 호출해야 합니다.",
        )

    try:
        location_status = controller.update_location(
            longitude=request.longitude,
            latitude=request.latitude,
            speed_kmh=request.speed_kmh,
        )

        refresh_result = None
        if request.force_refresh or controller.environment_refresh_due():
            refresh_result = controller.refresh_environment(
                force=request.force_refresh,
            )
            if refresh_result is not None:
                with _state_lock:
                    _last_live_refresh = refresh_result

        messages = _build_live_messages(
            location_status=location_status,
            refresh_result=refresh_result,
        )

        return {
            **location_status,
            "weather": controller.current_weather,
            "environment_refreshed": refresh_result is not None,
            "environment": refresh_result,
            "messages": messages,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"실시간 위치 처리 중 오류가 발생했습니다: {exc}",
        ) from exc


@app.get("/driving-status")
def driving_status():
    """현재 실시간 주행 세션의 마지막 상태를 확인합니다."""

    with _state_lock:
        controller = _live_controller
        last_refresh = _last_live_refresh

    if controller is None:
        return {
            "active": False,
            "message": "실시간 주행이 시작되지 않았습니다.",
        }

    return {
        "active": True,
        "weather": controller.current_weather,
        "location": controller.last_location,
        "progress": controller.current_progress,
        "region": controller.current_region,
        "is_resting": controller.is_resting,
        "environment_refresh_due": controller.environment_refresh_due(),
        "last_environment_refresh": last_refresh,
    }


@app.post("/stop-driving")
def stop_driving():
    """실시간 주행 세션과 자동 갱신을 종료합니다."""

    global _live_controller, _last_live_refresh

    with _state_lock:
        controller = _live_controller
        _live_controller = None
        _last_live_refresh = None

    if controller is not None:
        controller.stop_auto_refresh()

    return {"status": "stopped"}
