from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
import math
from typing import Any, Callable

import requests

from config import (
    TMAP_API_VERSION,
    TMAP_APP_KEY,
    TMAP_TRAFFIC_URL,
)
from services.route_service import extract_route_timeline


CONGESTION_NAMES = {
    0: "정보없음",
    1: "원활",
    2: "서행",
    3: "지체",
    4: "정체",
}


class TmapTrafficError(RuntimeError):
    """TMAP 교통 정보 조회 실패를 나타냅니다."""


ProgressCallback = Callable[[float, str], None]


def _notify_progress(
    progress_callback: ProgressCallback | None,
    percent: float,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(percent, message)


def _extract_error_message(data: Any) -> str:
    if not isinstance(data, dict):
        return "응답 형식을 확인할 수 없습니다."

    error = data.get("error")

    if isinstance(error, dict):
        return str(
            error.get("message")
            or error.get("detail")
            or error
        )

    return str(
        data.get("message")
        or data.get("errorMessage")
        or "원인을 확인할 수 없습니다."
    )


def request_traffic_near_point(
    longitude: float,
    latitude: float,
    radius_km: float = 2.0,
) -> dict[str, Any]:
    """대표 좌표 주변의 TMAP 실시간 교통 정보를 조회합니다."""

    if not TMAP_APP_KEY:
        raise RuntimeError(
            "TMAP AppKey가 설정되지 않았습니다."
        )

    headers = {
        "Accept": "application/json",
        "appKey": TMAP_APP_KEY,
    }

    params = {
        "version": TMAP_API_VERSION,
        "centerLat": float(latitude),
        "centerLon": float(longitude),
        "trafficType": "AUTO",
        "radius": float(radius_km),
        "zoomLevel": 15,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
    }

    try:
        response = requests.get(
            TMAP_TRAFFIC_URL,
            headers=headers,
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        raise TmapTrafficError(
            f"TMAP 교통 서버에 연결하지 못했습니다: {exc}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise TmapTrafficError(
            "TMAP 교통 응답을 JSON으로 해석하지 못했습니다."
        ) from exc

    if not response.ok:
        raise TmapTrafficError(
            "TMAP 교통 조회 실패 "
            f"(HTTP {response.status_code}): "
            f"{_extract_error_message(data)}"
        )

    return data


def _property(
    properties: dict[str, Any],
    name: str,
    default: Any = None,
) -> Any:
    """JSON 응답과 XML 변환 응답의 키 차이를 함께 처리합니다."""

    if name in properties:
        return properties[name]

    tmap_name = f"tmap:{name}"
    if tmap_name in properties:
        return properties[tmap_name]

    return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _distance_m(
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
) -> float:
    """짧은 거리에서 사용할 위경도 평면 근사 거리입니다."""

    mean_latitude = math.radians((lat1 + lat2) / 2)
    meters_per_lon = 111_320 * math.cos(mean_latitude)
    meters_per_lat = 110_540

    dx = (lon2 - lon1) * meters_per_lon
    dy = (lat2 - lat1) * meters_per_lat
    return math.hypot(dx, dy)


def _point_to_segment_distance_m(
    point_lon: float,
    point_lat: float,
    start: list[float],
    end: list[float],
) -> float:
    latitude_radians = math.radians(point_lat)
    meters_per_lon = 111_320 * math.cos(latitude_radians)
    meters_per_lat = 110_540

    ax = (float(start[0]) - point_lon) * meters_per_lon
    ay = (float(start[1]) - point_lat) * meters_per_lat
    bx = (float(end[0]) - point_lon) * meters_per_lon
    by = (float(end[1]) - point_lat) * meters_per_lat

    dx = bx - ax
    dy = by - ay
    length_squared = dx * dx + dy * dy

    if length_squared <= 0:
        return math.hypot(ax, ay)

    t = -(ax * dx + ay * dy) / length_squared
    t = max(0.0, min(1.0, t))

    nearest_x = ax + t * dx
    nearest_y = ay + t * dy

    return math.hypot(nearest_x, nearest_y)


def _point_to_linestring_distance_m(
    point_lon: float,
    point_lat: float,
    coordinates: list[list[float]],
) -> float:
    if len(coordinates) < 2:
        return float("inf")

    return min(
        _point_to_segment_distance_m(
            point_lon,
            point_lat,
            coordinates[index],
            coordinates[index + 1],
        )
        for index in range(len(coordinates) - 1)
    )


def _build_route_match_timeline(
    route: dict[str, Any],
) -> list[dict[str, float]]:
    """
    좌표 간 실제 지리 거리 비율로 TMAP 구간의 거리·시간을 분배합니다.

    기존 route_service의 타임라인은 좌표 개수로 균등 분배하므로,
    교통 링크의 경로상 위치를 찾을 때는 이 보정 타임라인을 사용합니다.
    """

    segments = route.get("segments", [])

    if not segments:
        return extract_route_timeline(route)

    timeline: list[dict[str, float]] = []
    elapsed_seconds = 0.0
    accumulated_distance = 0.0

    for segment in segments:
        coordinates = segment.get("coordinates", [])

        if not isinstance(coordinates, list) or len(coordinates) < 2:
            continue

        geometric_lengths = []

        for index in range(len(coordinates) - 1):
            start = coordinates[index]
            end = coordinates[index + 1]

            geometric_lengths.append(
                _distance_m(
                    float(start[0]),
                    float(start[1]),
                    float(end[0]),
                    float(end[1]),
                )
            )

        geometric_total = sum(geometric_lengths)
        segment_distance = max(
            0.0,
            _as_float(segment.get("distance_m"), 0.0),
        )
        segment_duration = max(
            0.0,
            _as_float(segment.get("duration_s"), 0.0),
        )

        if not timeline:
            timeline.append(
                {
                    "longitude": float(coordinates[0][0]),
                    "latitude": float(coordinates[0][1]),
                    "elapsed_seconds": elapsed_seconds,
                    "distance_m": accumulated_distance,
                }
            )

        for index, point in enumerate(coordinates[1:]):
            if geometric_total > 0:
                ratio = geometric_lengths[index] / geometric_total
            else:
                ratio = 1 / max(1, len(coordinates) - 1)

            elapsed_seconds += segment_duration * ratio
            accumulated_distance += segment_distance * ratio

            timeline.append(
                {
                    "longitude": float(point[0]),
                    "latitude": float(point[1]),
                    "elapsed_seconds": elapsed_seconds,
                    "distance_m": accumulated_distance,
                }
            )

    if not timeline:
        return extract_route_timeline(route)

    total_distance = _as_float(route.get("distance"), 0.0)
    total_duration = _as_float(route.get("duration"), 0.0)
    raw_distance = timeline[-1]["distance_m"]
    raw_duration = timeline[-1]["elapsed_seconds"]

    distance_scale = (
        total_distance / raw_distance
        if total_distance > 0 and raw_distance > 0
        else 1.0
    )
    duration_scale = (
        total_duration / raw_duration
        if total_duration > 0 and raw_duration > 0
        else 1.0
    )

    for point in timeline:
        point["distance_m"] *= distance_scale
        point["elapsed_seconds"] *= duration_scale

    return timeline


def _sample_route_points(
    timeline: list[dict[str, float]],
    spacing_km: float = 3.0,
    maximum_points: int = 18,
) -> list[dict[str, float]]:
    """경로 전체를 빠뜨리지 않도록 거리 기준으로 조회 좌표를 고릅니다."""

    if not timeline:
        return []

    start_distance_m = float(
        timeline[0].get("distance_m", 0)
    )
    end_distance_m = float(
        timeline[-1].get("distance_m", 0)
    )
    remaining_distance_m = max(
        0.0,
        end_distance_m - start_distance_m,
    )

    if remaining_distance_m <= 0:
        return [timeline[0]]

    spacing_m = max(500.0, float(spacing_km) * 1000)
    estimated_count = int(
        math.ceil(remaining_distance_m / spacing_m)
    ) + 1
    point_count = max(2, min(maximum_points, estimated_count))

    target_distances = [
        start_distance_m
        + remaining_distance_m * index / (point_count - 1)
        for index in range(point_count)
    ]

    sampled = []
    timeline_index = 0

    for target_distance in target_distances:
        while (
            timeline_index < len(timeline) - 1
            and float(
                timeline[timeline_index].get(
                    "distance_m",
                    0,
                )
            ) < target_distance
        ):
            timeline_index += 1

        sampled.append(timeline[timeline_index])

    # 좌표가 같은 항목은 한 번만 호출합니다.
    unique = []
    seen = set()

    for point in sampled:
        key = (
            round(float(point["longitude"]), 5),
            round(float(point["latitude"]), 5),
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(point)

    return unique


def _request_traffic_parallel(
    points: list[dict[str, float]],
    radius_km: float,
    max_workers: int,
    progress_callback: ProgressCallback | None = None,
    progress_start: float = 10.0,
    progress_end: float = 45.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not points:
        return [], []

    payloads: list[dict[str, Any]] = []
    errors: list[str] = []
    worker_count = min(max_workers, len(points))

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        future_map = {
            executor.submit(
                request_traffic_near_point,
                point["longitude"],
                point["latitude"],
                radius_km,
            ): index
            for index, point in enumerate(points)
        }

        completed_count = 0

        for future in as_completed(future_map):
            completed_count += 1
            request_percent = (
                progress_start
                + (progress_end - progress_start)
                * completed_count
                / len(points)
            )
            _notify_progress(
                progress_callback,
                request_percent,
                (
                    "TMAP 교통정보 요청 중 "
                    f"({completed_count}/{len(points)})"
                ),
            )

            try:
                payloads.append(future.result())
            except Exception as exc:
                errors.append(str(exc))

    return payloads, errors


def _clean_road_name(value: Any) -> str:
    road_name = str(value or "").strip()

    # TMAP 교통 응답의 name은 "도로명/링크ID/..." 형태일 수 있습니다.
    if "/" in road_name:
        road_name = road_name.split("/", 1)[0].strip()

    return road_name


def _normalize_traffic_features(
    payloads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """여러 조회 결과를 하나로 합치고 같은 링크는 제거합니다."""

    links: dict[tuple[Any, ...], dict[str, Any]] = {}

    for data in payloads:
        for feature in data.get("features", []):
            geometry = feature.get("geometry") or {}
            properties = feature.get("properties") or {}

            if geometry.get("type") != "LineString":
                continue

            coordinates = geometry.get("coordinates", [])

            if not isinstance(coordinates, list) or len(coordinates) < 2:
                continue

            valid_coordinates = []

            for point in coordinates:
                if not isinstance(point, (list, tuple)) or len(point) < 2:
                    continue

                valid_coordinates.append(
                    [float(point[0]), float(point[1])]
                )

            if len(valid_coordinates) < 2:
                continue

            link_id = str(
                _property(properties, "id", "") or ""
            ).strip()
            direction = str(
                _property(properties, "direction", "") or ""
            ).strip()
            start_node = str(
                _property(properties, "startNodeName", "")
                or ""
            ).strip()
            end_node = str(
                _property(properties, "endNodeName", "")
                or ""
            ).strip()
            road_name = _clean_road_name(
                _property(properties, "name", "")
            )

            if link_id:
                key = (link_id, direction)
            else:
                key = (
                    road_name,
                    start_node,
                    end_node,
                    direction,
                )

            links[key] = {
                "link_id": link_id,
                "direction": direction,
                "road_name": road_name,
                "description": str(
                    _property(properties, "description", "")
                    or ""
                ).strip(),
                "start_node": start_node,
                "end_node": end_node,
                "congestion_level": _as_int(
                    _property(properties, "congestion", 0),
                    0,
                ),
                "speed_kmh": _as_float(
                    _property(properties, "speed", 0),
                    0.0,
                ),
                "distance_m": _as_float(
                    _property(properties, "distance", 0),
                    0.0,
                ),
                "time_s": _as_float(
                    _property(properties, "time", 0),
                    0.0,
                ),
                "update_time": str(
                    _property(properties, "updateTime", "")
                    or ""
                ).strip(),
                "coordinates": valid_coordinates,
            }

    return list(links.values())


def _reduce_timeline(
    timeline: list[dict[str, float]],
    maximum_points: int = 900,
) -> list[dict[str, float]]:
    if len(timeline) <= maximum_points:
        return timeline

    step = max(1, math.ceil(len(timeline) / maximum_points))
    reduced = timeline[::step]

    if reduced[-1] is not timeline[-1]:
        reduced.append(timeline[-1])

    return reduced


def _match_link_to_route(
    link: dict[str, Any],
    timeline: list[dict[str, float]],
    max_match_distance_m: float,
) -> dict[str, Any] | None:
    """교통 링크가 실제 안내 경로와 가까운지 확인하고 위치를 붙입니다."""

    coordinates = link.get("coordinates", [])

    if len(coordinates) < 2:
        return None

    nearest_point = None
    nearest_distance = float("inf")

    for route_point in timeline:
        match_distance = _point_to_linestring_distance_m(
            float(route_point["longitude"]),
            float(route_point["latitude"]),
            coordinates,
        )

        if match_distance < nearest_distance:
            nearest_distance = match_distance
            nearest_point = route_point

    if (
        nearest_point is None
        or nearest_distance > max_match_distance_m
    ):
        return None

    result = dict(link)
    result["match_distance_m"] = round(nearest_distance, 1)
    result["route_distance_m"] = float(
        nearest_point.get("distance_m", 0)
    )
    result["eta_minutes"] = round(
        float(nearest_point.get("elapsed_seconds", 0)) / 60,
        1,
    )

    half_distance = max(0.0, result["distance_m"] / 2)
    result["start_route_m"] = max(
        0.0,
        result["route_distance_m"] - half_distance,
    )
    result["end_route_m"] = (
        result["route_distance_m"] + half_distance
    )

    return result


def _find_region_for_route_distance(
    regions: list[dict[str, Any]],
    route_distance_m: float,
) -> dict[str, Any] | None:
    for region in regions:
        start_m = _as_float(
            region.get("entry_distance_km"),
            0.0,
        ) * 1000
        end_m = _as_float(
            region.get("exit_distance_km"),
            0.0,
        ) * 1000

        if start_m <= route_distance_m <= end_m:
            return region

    if not regions:
        return None

    return min(
        regions,
        key=lambda region: abs(
            _as_float(
                region.get("entry_distance_km"),
                0.0,
            )
            * 1000
            - route_distance_m
        ),
    )


def _attach_region_to_links(
    links: list[dict[str, Any]],
    regions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []

    for link in links:
        item = dict(link)
        region = _find_region_for_route_distance(
            regions,
            float(item.get("route_distance_m", 0)),
        )

        if region:
            item["시도"] = region.get("시도", "")
            item["시군구"] = region.get("시군구", "")
        else:
            item["시도"] = ""
            item["시군구"] = ""

        enriched.append(item)

    return enriched


def _same_corridor(
    previous: dict[str, Any],
    current: dict[str, Any],
) -> bool:
    previous_road = previous.get("road_name", "")
    current_road = current.get("road_name", "")

    if previous_road and previous_road == current_road:
        return True

    previous_end = previous.get("end_node", "")
    current_start = current.get("start_node", "")

    if previous_end and previous_end == current_start:
        return True

    same_region = (
        previous.get("시도", ""),
        previous.get("시군구", ""),
    ) == (
        current.get("시도", ""),
        current.get("시군구", ""),
    )

    # 도로명이 바뀌더라도 같은 지역에서 매우 가까운 정체 링크는
    # 하나의 연속 혼잡 구간으로 묶습니다.
    return same_region


def _new_congestion_group(
    link: dict[str, Any],
) -> dict[str, Any]:
    distance_m = max(0.0, _as_float(link.get("distance_m")))
    speed = max(0.0, _as_float(link.get("speed_kmh")))

    return {
        "links": [link],
        "road_names": [link.get("road_name", "")]
        if link.get("road_name")
        else [],
        "start_node": link.get("start_node", ""),
        "end_node": link.get("end_node", ""),
        "시도": link.get("시도", ""),
        "시군구": link.get("시군구", ""),
        "start_route_m": float(link.get("start_route_m", 0)),
        "end_route_m": float(link.get("end_route_m", 0)),
        "eta_minutes": float(link.get("eta_minutes", 0)),
        "congestion_level": int(
            link.get("congestion_level", 0)
        ),
        "distance_m": distance_m,
        "time_s": max(0.0, _as_float(link.get("time_s"))),
        "weighted_speed_sum": speed * distance_m,
        "speed_weight_m": distance_m if speed > 0 else 0.0,
        "update_time": link.get("update_time", ""),
    }


def _append_to_group(
    group: dict[str, Any],
    link: dict[str, Any],
) -> None:
    group["links"].append(link)

    road_name = link.get("road_name", "")
    if road_name and road_name not in group["road_names"]:
        group["road_names"].append(road_name)

    if not group.get("start_node"):
        group["start_node"] = link.get("start_node", "")

    if link.get("end_node"):
        group["end_node"] = link.get("end_node", "")

    group["start_route_m"] = min(
        group["start_route_m"],
        float(link.get("start_route_m", 0)),
    )
    group["end_route_m"] = max(
        group["end_route_m"],
        float(link.get("end_route_m", 0)),
    )
    group["eta_minutes"] = min(
        group["eta_minutes"],
        float(link.get("eta_minutes", 0)),
    )
    group["congestion_level"] = max(
        group["congestion_level"],
        int(link.get("congestion_level", 0)),
    )

    distance_m = max(0.0, _as_float(link.get("distance_m")))
    speed = max(0.0, _as_float(link.get("speed_kmh")))

    group["distance_m"] += distance_m
    group["time_s"] += max(
        0.0,
        _as_float(link.get("time_s")),
    )

    if speed > 0:
        group["weighted_speed_sum"] += speed * distance_m
        group["speed_weight_m"] += distance_m

    if link.get("update_time"):
        group["update_time"] = link["update_time"]


def _finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    speed = None

    if group["speed_weight_m"] > 0:
        speed = round(
            group["weighted_speed_sum"]
            / group["speed_weight_m"],
            1,
        )

    road_names = [
        name
        for name in group["road_names"]
        if name
    ]

    return {
        "traffic_available": True,
        "congestion_level": group["congestion_level"],
        "congestion_name": CONGESTION_NAMES.get(
            group["congestion_level"],
            "정보없음",
        ),
        "congestion_distance_km": round(
            group["distance_m"] / 1000,
            2,
        ),
        "congestion_time_minutes": round(
            group["time_s"] / 60,
            1,
        ),
        "average_speed_kmh": speed,
        "road_names": road_names,
        "road_name": " · ".join(road_names[:2]),
        "start_node": group.get("start_node", ""),
        "end_node": group.get("end_node", ""),
        "시도": group.get("시도", ""),
        "시군구": group.get("시군구", ""),
        "eta_minutes": round(group["eta_minutes"], 1),
        "start_route_km": round(
            group["start_route_m"] / 1000,
            2,
        ),
        "end_route_km": round(
            group["end_route_m"] / 1000,
            2,
        ),
        "link_count": len(group["links"]),
        "update_time": group.get("update_time", ""),
    }


def _merge_congested_links(
    links: list[dict[str, Any]],
    minimum_level: int = 2,
    maximum_gap_m: float = 600,
) -> list[dict[str, Any]]:
    congested = [
        link
        for link in links
        if int(link.get("congestion_level", 0))
        >= minimum_level
    ]

    congested.sort(
        key=lambda link: float(
            link.get("route_distance_m", 0)
        )
    )

    groups: list[dict[str, Any]] = []

    for link in congested:
        if not groups:
            groups.append(_new_congestion_group(link))
            continue

        previous_link = groups[-1]["links"][-1]
        gap_m = float(link.get("start_route_m", 0)) - float(
            groups[-1].get("end_route_m", 0)
        )

        if (
            gap_m <= maximum_gap_m
            and _same_corridor(previous_link, link)
        ):
            _append_to_group(groups[-1], link)
        else:
            groups.append(_new_congestion_group(link))

    return [_finalize_group(group) for group in groups]


def _attach_traffic_to_regions(
    regions: list[dict[str, Any]],
    matched_links: list[dict[str, Any]],
    congestion_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []

    for region in regions:
        item = dict(region)
        start_m = _as_float(
            item.get("entry_distance_km"),
            0.0,
        ) * 1000
        end_m = _as_float(
            item.get("exit_distance_km"),
            0.0,
        ) * 1000

        region_links = [
            link
            for link in matched_links
            if start_m
            <= _as_float(link.get("route_distance_m"), 0.0)
            <= end_m
        ]

        region_congestion = [
            segment
            for segment in congestion_segments
            if (
                start_m / 1000
                <= _as_float(segment.get("start_route_km"), 0.0)
                <= end_m / 1000
            )
            or (
                start_m / 1000
                <= _as_float(segment.get("end_route_km"), 0.0)
                <= end_m / 1000
            )
            or (
                _as_float(segment.get("start_route_km"), 0.0)
                <= start_m / 1000
                and _as_float(segment.get("end_route_km"), 0.0)
                >= end_m / 1000
            )
        ]

        if not region_links:
            item.update(
                {
                    "traffic_available": False,
                    "congestion_level": 0,
                    "congestion_name": "정보없음",
                    "average_speed_kmh": None,
                    "congestion_distance_km": 0.0,
                    "congestion_segments": region_congestion,
                }
            )
            enriched.append(item)
            continue

        worst_link = max(
            region_links,
            key=lambda link: int(
                link.get("congestion_level", 0)
            ),
        )

        speed_weight_sum = 0.0
        speed_weight_m = 0.0

        for link in region_links:
            speed = _as_float(link.get("speed_kmh"), 0.0)
            distance_m = max(
                1.0,
                _as_float(link.get("distance_m"), 0.0),
            )

            if speed > 0:
                speed_weight_sum += speed * distance_m
                speed_weight_m += distance_m

        average_speed = (
            round(speed_weight_sum / speed_weight_m, 1)
            if speed_weight_m > 0
            else None
        )

        total_congestion_km = round(
            sum(
                _as_float(
                    segment.get("congestion_distance_km"),
                    0.0,
                )
                for segment in region_congestion
            ),
            2,
        )

        worst_level = int(
            worst_link.get("congestion_level", 0)
        )

        item.update(
            {
                "traffic_available": True,
                "congestion_level": worst_level,
                "congestion_name": CONGESTION_NAMES.get(
                    worst_level,
                    "정보없음",
                ),
                "average_speed_kmh": average_speed,
                "congestion_distance_km": total_congestion_km,
                "congestion_segments": region_congestion,
            }
        )
        enriched.append(item)

    return enriched


def analyze_route_traffic(
    route: dict[str, Any],
    regions: list[dict[str, Any]],
    spacing_km: float = 3.0,
    radius_km: float = 2.0,
    maximum_queries: int = 18,
    max_workers: int = 5,
    max_match_distance_m: float = 250,
    start_route_distance_m: float = 0.0,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    """
    경로에서 실제 안내선과 가까운 교통 링크를 찾고,
    인접한 서행·지체·정체 링크를 연속 혼잡 구간으로 합칩니다.

    start_route_distance_m이 0보다 크면 이미 지나온 구간을 제외하고
    현재 위치 이후의 남은 경로만 분석합니다.

    반환값:
    {
        "regions": 교통 정보가 붙은 지역 목록,
        "congestion_segments": 어디서 어디까지 혼잡한지 나타내는 목록,
        "traffic_errors": 일부 조회 실패 메시지,
    }
    """

    _notify_progress(
        progress_callback,
        2,
        "경로 좌표와 시간을 정리하는 중",
    )
    timeline = _build_route_match_timeline(route)

    start_route_distance_m = max(
        0.0,
        _as_float(start_route_distance_m, 0.0),
    )
    full_timeline = timeline

    if start_route_distance_m > 0:
        remaining_timeline = [
            point
            for point in full_timeline
            if _as_float(point.get("distance_m"), 0.0)
            >= start_route_distance_m
        ]

        if remaining_timeline:
            timeline = remaining_timeline
        elif full_timeline:
            timeline = [full_timeline[-1]]

    elapsed_offset_minutes = (
        _as_float(
            timeline[0].get("elapsed_seconds"),
            0.0,
        )
        / 60.0
        if timeline
        else 0.0
    )

    _notify_progress(
        progress_callback,
        7,
        "교통정보 조회 지점을 선택하는 중",
    )
    query_points = _sample_route_points(
        timeline=timeline,
        spacing_km=spacing_km,
        maximum_points=maximum_queries,
    )

    _notify_progress(
        progress_callback,
        10,
        f"교통정보 {len(query_points)}개 지점 조회 준비",
    )
    payloads, errors = _request_traffic_parallel(
        points=query_points,
        radius_km=radius_km,
        max_workers=max_workers,
        progress_callback=progress_callback,
        progress_start=10,
        progress_end=45,
    )

    _notify_progress(
        progress_callback,
        48,
        "받은 도로 링크를 정리하는 중",
    )
    traffic_links = _normalize_traffic_features(payloads)

    print("=== 실시간 교통 디버그 ===")
    print("조회 지점 수:", len(query_points))
    print("응답 payload 수:", len(payloads))
    print("조회 오류 수:", len(errors))
    print("조회 오류:", errors)
    print("정규화된 traffic_links 수:", len(traffic_links))

    if payloads:
        first_payload = payloads[0]
        print("첫 payload 타입:", type(first_payload))

        if isinstance(first_payload, dict):
            print("첫 payload 키:", list(first_payload.keys()))
            print("첫 payload 일부:", str(first_payload)[:2000])
        else:
            print("첫 payload 일부:", str(first_payload)[:2000])

    print("==========================")

    reduced_timeline = _reduce_timeline(timeline)
    reduced_timeline = _reduce_timeline(timeline)
    matched_links = []

    total_links = len(traffic_links)
    report_interval = max(1, total_links // 100)

    if total_links == 0:
        _notify_progress(
            progress_callback,
            85,
            "대조할 교통 링크가 없습니다",
        )

    for index, link in enumerate(
        traffic_links,
        start=1,
    ):
        matched = _match_link_to_route(
            link=link,
            timeline=reduced_timeline,
            max_match_distance_m=max_match_distance_m,
        )

        if (
            matched is not None
            and _as_float(
                matched.get("route_distance_m"),
                0.0,
            ) >= start_route_distance_m
        ):
            matched_links.append(matched)

        if (
            index == 1
            or index == total_links
            or index % report_interval == 0
        ):
            match_percent = 50 + 35 * index / total_links
            _notify_progress(
                progress_callback,
                match_percent,
                (
                    "실제 경로와 교통 링크 대조 중 "
                    f"({index}/{total_links}, "
                    f"일치 {len(matched_links)}개)"
                ),
            )

    if start_route_distance_m > 0:
        for link in matched_links:
            original_eta = _as_float(
                link.get("eta_minutes"),
                0.0,
            )
            link["eta_minutes"] = round(
                max(
                    0.0,
                    original_eta - elapsed_offset_minutes,
                ),
                1,
            )

    _notify_progress(
        progress_callback,
        89,
        "교통 링크에 행정구역을 연결하는 중",
    )
    matched_links = _attach_region_to_links(
        matched_links,
        regions,
    )

    _notify_progress(
        progress_callback,
        94,
        "연속된 정체 구간을 합치는 중",
    )
    congestion_segments = _merge_congested_links(
        matched_links,
        minimum_level=2,
        maximum_gap_m=600,
    )

    _notify_progress(
        progress_callback,
        98,
        "지역별 교통상태를 계산하는 중",
    )
    enriched_regions = _attach_traffic_to_regions(
        regions,
        matched_links,
        congestion_segments,
    )

    _notify_progress(
        progress_callback,
        100,
        (
            "교통정보 분석 완료: "
            f"경로 일치 {len(matched_links)}개, "
            f"혼잡 구간 {len(congestion_segments)}개"
        ),
    )

    return {
        "regions": enriched_regions,
        "congestion_segments": congestion_segments,
        "traffic_errors": errors,
        "traffic_query_count": len(query_points),
        "successful_traffic_query_count": len(payloads),
        "traffic_feature_count": len(traffic_links),
        "matched_traffic_link_count": len(matched_links),
    }


# 이전 패치와의 호환용 함수입니다.
def attach_traffic_information(
    regions: list[dict[str, Any]],
    max_workers: int = 4,
) -> list[dict[str, Any]]:
    """
    이전 코드 호환용입니다.

    경로 전체의 정체 구간을 안내하려면 main.py에서
    analyze_route_traffic(route, regions)를 사용해야 합니다.
    """

    return [dict(region) for region in regions]