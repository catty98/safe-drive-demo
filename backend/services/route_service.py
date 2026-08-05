import math
import re
from typing import Any

from services.tmap_service import request_tmap_route


def _append_coordinates(
    target: list[list[float]],
    coordinates: list[Any],
) -> None:
    """중복되는 구간 경계 좌표를 제거하며 좌표를 합칩니다."""

    valid_coordinates: list[list[float]] = []

    for point in coordinates:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue

        valid_coordinates.append(
            [float(point[0]), float(point[1])]
        )

    if not valid_coordinates:
        return

    if target and target[-1] == valid_coordinates[0]:
        target.extend(valid_coordinates[1:])
    else:
        target.extend(valid_coordinates)


def normalize_tmap_route(tmap_data: dict[str, Any]) -> dict[str, Any]:
    """
    TMAP GeoJSON 응답을 프로젝트 내부의 공통 경로 형식으로 바꿉니다.

    내부 형식:
    - distance: 총 거리(m)
    - duration: 총 소요시간(초)
    - coordinates: 전체 경로 좌표
    - segments: 도로 구간별 좌표·거리·시간·도로 유형
    """

    total_distance = 0.0
    total_duration = 0.0
    route_coordinates: list[list[float]] = []
    segments: list[dict[str, Any]] = []

    features = tmap_data.get("features", [])

    for feature in features:
        geometry = feature.get("geometry") or {}
        properties = feature.get("properties") or {}
        geometry_type = geometry.get("type")

        if geometry_type == "Point":
            # 출발지 Point 피처에 전체 거리와 시간이 포함됩니다.
            if properties.get("pointType") == "S":
                total_distance = float(
                    properties.get("totalDistance", 0) or 0
                )
                total_duration = float(
                    properties.get("totalTime", 0) or 0
                )

        elif geometry_type == "LineString":
            line_coordinates = geometry.get("coordinates", [])

            if len(line_coordinates) < 2:
                continue

            _append_coordinates(
                route_coordinates,
                line_coordinates,
            )

            segments.append(
                {
                    "name": str(
                        properties.get("name", "")
                    ).strip(),
                    "description": str(
                        properties.get("description", "")
                    ).strip(),
                    "road_type_code": properties.get("roadType"),
                    "facility_type_code": properties.get(
                        "facilityType"
                    ),
                    "distance_m": float(
                        properties.get("distance", 0) or 0
                    ),
                    "duration_s": float(
                        properties.get("time", 0) or 0
                    ),
                    "coordinates": [
                        [float(point[0]), float(point[1])]
                        for point in line_coordinates
                        if isinstance(point, (list, tuple))
                        and len(point) >= 2
                    ],
                }
            )

    if len(route_coordinates) < 2:
        raise ValueError(
            "TMAP 응답에서 경로 좌표를 추출하지 못했습니다."
        )

    # 일부 응답에서 전체값이 없을 경우 구간 합계로 보완합니다.
    if total_distance <= 0:
        total_distance = sum(
            segment["distance_m"]
            for segment in segments
        )

    if total_duration <= 0:
        total_duration = sum(
            segment["duration_s"]
            for segment in segments
        )

    return {
        "provider": "tmap",
        "distance": total_distance,
        "duration": total_duration,
        "coordinates": route_coordinates,
        "segments": segments,
    }


def request_route(origin, destination):
    """
    기존 main.py의 호출 방식을 유지하면서 TMAP 경로를 반환합니다.
    """

    raw_route = request_tmap_route(
        origin=origin,
        destination=destination,
    )

    return normalize_tmap_route(raw_route)


def extract_route_coordinates(route):
    """
    정규화된 경로에서 (경도, 위도) 좌표를 추출합니다.
    """

    coordinates = route.get("coordinates", [])

    if len(coordinates) < 2:
        raise ValueError(
            "경로 좌표를 추출하지 못했습니다."
        )

    return [
        (float(point[0]), float(point[1]))
        for point in coordinates
    ]


def get_route_summary(route):
    """총 거리와 예상 이동시간을 반환합니다."""

    return {
        "distance_km": round(
            float(route.get("distance", 0)) / 1000,
            2,
        ),
        "duration_minutes": round(
            float(route.get("duration", 0)) / 60,
            1,
        ),
    }


def _build_fallback_timeline(route):
    coordinates = extract_route_coordinates(route)
    segment_count = len(coordinates) - 1

    total_duration = float(route.get("duration", 0))
    total_distance = float(route.get("distance", 0))

    duration_per_segment = (
        total_duration / segment_count
        if segment_count > 0
        else 0.0
    )
    distance_per_segment = (
        total_distance / segment_count
        if segment_count > 0
        else 0.0
    )

    timeline = [
        {
            "longitude": coordinates[0][0],
            "latitude": coordinates[0][1],
            "elapsed_seconds": 0.0,
            "distance_m": 0.0,
        }
    ]

    elapsed_seconds = 0.0
    accumulated_distance = 0.0

    for longitude, latitude in coordinates[1:]:
        elapsed_seconds += duration_per_segment
        accumulated_distance += distance_per_segment

        timeline.append(
            {
                "longitude": longitude,
                "latitude": latitude,
                "elapsed_seconds": elapsed_seconds,
                "distance_m": accumulated_distance,
            }
        )

    return timeline


def extract_route_timeline(route):
    """
    TMAP의 구간별 시간과 거리를 이용하여 경로 타임라인을 만듭니다.

    각 LineString 안에서는 좌표 간 시간을 균등 분배합니다.
    따라서 지역 진입시간은 기존과 마찬가지로 대략적인 추정값입니다.
    """

    segments = route.get("segments", [])

    if not segments:
        return _build_fallback_timeline(route)

    timeline: list[dict[str, float]] = []
    elapsed_seconds = 0.0
    accumulated_distance = 0.0

    for segment in segments:
        coordinates = segment.get("coordinates", [])

        if len(coordinates) < 2:
            continue

        interval_count = len(coordinates) - 1
        duration_per_interval = (
            float(segment.get("duration_s", 0))
            / interval_count
        )
        distance_per_interval = (
            float(segment.get("distance_m", 0))
            / interval_count
        )

        first_longitude = float(coordinates[0][0])
        first_latitude = float(coordinates[0][1])

        if not timeline:
            timeline.append(
                {
                    "longitude": first_longitude,
                    "latitude": first_latitude,
                    "elapsed_seconds": 0.0,
                    "distance_m": 0.0,
                }
            )

        for point in coordinates[1:]:
            elapsed_seconds += duration_per_interval
            accumulated_distance += distance_per_interval

            timeline.append(
                {
                    "longitude": float(point[0]),
                    "latitude": float(point[1]),
                    "elapsed_seconds": elapsed_seconds,
                    "distance_m": accumulated_distance,
                }
            )

    if not timeline:
        return _build_fallback_timeline(route)

    # 구간 합계와 TMAP 전체 합계 사이의 미세한 차이를 보정합니다.
    total_duration = float(route.get("duration", 0))
    total_distance = float(route.get("distance", 0))
    raw_duration = timeline[-1]["elapsed_seconds"]
    raw_distance = timeline[-1]["distance_m"]

    duration_scale = (
        total_duration / raw_duration
        if raw_duration > 0 and total_duration > 0
        else 1.0
    )
    distance_scale = (
        total_distance / raw_distance
        if raw_distance > 0 and total_distance > 0
        else 1.0
    )

    for point in timeline:
        point["elapsed_seconds"] *= duration_scale
        point["distance_m"] *= distance_scale

    return timeline
def _distance_between_coordinates_m(
    longitude1,
    latitude1,
    longitude2,
    latitude2,
):
    """두 위경도 좌표 사이의 짧은 거리를 미터로 계산합니다."""

    mean_latitude = math.radians(
        (float(latitude1) + float(latitude2)) / 2
    )

    meters_per_longitude = (
        111_320 * math.cos(mean_latitude)
    )
    meters_per_latitude = 110_540

    dx = (
        float(longitude2) - float(longitude1)
    ) * meters_per_longitude

    dy = (
        float(latitude2) - float(latitude1)
    ) * meters_per_latitude

    return math.hypot(dx, dy)


def find_route_progress(
    route,
    longitude,
    latitude,
):
    """
    현재 GPS 좌표와 가장 가까운 경로 지점의
    진행 상태를 반환합니다.
    """

    timeline = extract_route_timeline(route)

    if not timeline:
        raise ValueError(
            "경로 타임라인이 비어 있습니다."
        )

    nearest_point = min(
        timeline,
        key=lambda point:
            _distance_between_coordinates_m(
                longitude,
                latitude,
                point["longitude"],
                point["latitude"],
            ),
    )

    distance_from_route_m = (
        _distance_between_coordinates_m(
            longitude,
            latitude,
            nearest_point["longitude"],
            nearest_point["latitude"],
        )
    )

    total_distance_m = float(
        route.get("distance", 0) or 0
    )

    total_duration_s = float(
        route.get("duration", 0) or 0
    )

    progress_m = float(
        nearest_point.get("distance_m", 0) or 0
    )

    elapsed_seconds = float(
        nearest_point.get(
            "elapsed_seconds",
            0,
        ) or 0
    )

    return {
        "route_progress_m": progress_m,

        "route_progress_km": round(
            progress_m / 1000,
            2,
        ),

        "distance_from_route_m": round(
            distance_from_route_m,
            1,
        ),

        "elapsed_seconds": elapsed_seconds,

        "remaining_distance_km": round(
            max(
                0.0,
                total_distance_m - progress_m,
            ) / 1000,
            2,
        ),

        "remaining_minutes": round(
            max(
                0.0,
                total_duration_s - elapsed_seconds,
            ) / 60,
            1,
        ),
    }


def find_region_by_progress(
    regions,
    route_progress_m,
):
    """
    현재 경로 진행거리에 해당하는
    지역 정보를 반환합니다.
    """

    progress_km = (
        float(route_progress_m) / 1000
    )

    for region in regions:
        entry_km = float(
            region.get(
                "entry_distance_km",
                0,
            ) or 0
        )

        exit_km = float(
            region.get(
                "exit_distance_km",
                0,
            ) or 0
        )

        if entry_km <= progress_km <= exit_km:
            return dict(region)

    return None

def extract_route_steps(route):
    """정규화된 TMAP 도로 구간을 반환합니다."""

    steps = []

    for segment in route.get("segments", []):
        distance_m = float(
            segment.get("distance_m", 0)
        )

        if distance_m <= 0:
            continue

        steps.append(
            {
                "name": str(
                    segment.get("name", "")
                ).strip(),
                "description": str(
                    segment.get("description", "")
                ).strip(),
                "road_type_code": segment.get(
                    "road_type_code"
                ),
                "distance_m": distance_m,
                "duration_s": float(
                    segment.get("duration_s", 0)
                ),
            }
        )

    return steps


def classify_road_type(step):
    """
    TMAP roadType과 명시적인 도로명 표현을 TAAS 도로 종류로 변환합니다.

    TMAP roadType에서 TAAS와 직접 대응되는 값만 사용합니다.
    대응이 불확실한 일반도로는 임의 분류하지 않고 '기타'로 둡니다.
    """

    road_type_code = step.get("road_type_code")

    try:
        road_type_code = int(road_type_code)
    except (TypeError, ValueError):
        road_type_code = None

    tmap_to_taas = {
        0: "고속국도",
        2: "일반국도",
        3: "지방도",  # 국가지원 지방도를 TAAS 지방도로 통합
        4: "지방도",
    }

    if road_type_code in tmap_to_taas:
        return tmap_to_taas[road_type_code]

    name = str(step.get("name", "")).strip()
    description = str(
        step.get("description", "")
    ).strip()
    text = f"{name} {description}"

    if re.search(r"고속도로|고속국도", text):
        return "고속국도"

    if re.search(r"일반국도|국도\s*(제)?\s*\d+", text):
        return "일반국도"

    if re.search(r"국가지원지방도|지방도", text):
        return "지방도"

    if re.search(r"특별시도|광역시도", text):
        return "특별광역시도"

    if re.search(r"군도\s*(제)?\s*\d+", text):
        return "군도"

    if re.search(r"시도\s*(제)?\s*\d+", text):
        return "시도"

    return "기타"


def summarize_route_road_types(route):
    """
    실제 경로의 안내 구간을 TAAS 도로 종류별 거리와 비중으로 요약합니다.
    """

    steps = extract_route_steps(route)

    if not steps:
        return []

    distance_by_type = {}

    for step in steps:
        road_type = classify_road_type(step)

        distance_by_type[road_type] = (
            distance_by_type.get(road_type, 0.0)
            + step["distance_m"]
        )

    total_distance = sum(distance_by_type.values())

    if total_distance <= 0:
        return []

    result = []

    for road_type, distance_m in distance_by_type.items():
        result.append(
            {
                "도로종류": road_type,
                "거리_km": round(distance_m / 1000, 2),
                "경로비중(%)": round(
                    distance_m / total_distance * 100,
                    1,
                ),
            }
        )

    return sorted(
        result,
        key=lambda item: item["거리_km"],
        reverse=True,
    )
