import pandas as pd

from analysis.safety_message import create_safety_message


def _is_available(dataframe):
    return (
        isinstance(dataframe, pd.DataFrame)
        and not dataframe.empty
    )


def _format_location(region):
    return " ".join(
        value
        for value in [
            region.get("시도", ""),
            region.get("시군구", ""),
        ]
        if value
    )


def _format_region_timeline(regions, maximum_regions=2):
    future_regions = [
        region
        for region in regions
        if region.get("eta_minutes", 0) > 0
    ]

    if not future_regions:
        return None

    selected = future_regions[:maximum_regions]
    parts = []

    for region in selected:
        location = _format_location(region)
        parts.append(
            f"약 {region['eta_minutes']}분 후 {location}"
        )

    return ", ".join(parts) + "에 진입할 예정입니다."


def _format_location_from_segment(segment):
    return " ".join(
        value
        for value in [
            segment.get("시도", ""),
            segment.get("시군구", ""),
        ]
        if value
    )


def _congestion_safety_advice(segment):
    level = int(segment.get("congestion_level", 0))
    speed = segment.get("average_speed_kmh")

    if level >= 4:
        return (
            "급정지에 대비해 차간 거리를 충분히 확보하고 "
            "잦은 차선 변경을 피하세요."
        )

    if level == 3:
        return (
            "앞차의 반복 제동에 대비해 차간 거리를 유지하고 "
            "급가속과 급제동을 피하세요."
        )

    if level == 2:
        if speed is not None and float(speed) <= 30:
            return (
                "속도 변화가 잦을 수 있으니 전방 흐름을 확인하고 "
                "안전거리를 유지하세요."
            )

        return (
            "주행 흐름이 느려질 수 있으니 전방을 주시하고 "
            "무리한 추월을 피하세요."
        )

    return ""


def _format_congestion_place(segment):
    start_node = str(segment.get("start_node", "")).strip()
    end_node = str(segment.get("end_node", "")).strip()
    road_name = str(segment.get("road_name", "")).strip()
    location = _format_location_from_segment(segment)

    if start_node and end_node:
        place = f"{start_node}에서 {end_node} 방면"
    elif road_name:
        place = road_name
    elif location:
        place = f"{location} 도로"
    else:
        place = "경로상 도로"

    if road_name and road_name not in place:
        place = f"{place} {road_name}"

    if location and location not in place:
        place = f"{location}의 {place}"

    return place


def _format_congestion_messages(
    congestion_segments,
    traffic_status=None,
    maximum_messages=2,
):
    """정체 안내 또는 교통정보 조회 상태를 반드시 한 문장으로 반환합니다."""

    traffic_status = traffic_status or {}

    query_count = int(
        traffic_status.get("traffic_query_count", 0) or 0
    )
    success_count = int(
        traffic_status.get(
            "successful_traffic_query_count",
            0,
        )
        or 0
    )
    feature_count = int(
        traffic_status.get("traffic_feature_count", 0) or 0
    )
    matched_count = int(
        traffic_status.get(
            "matched_traffic_link_count",
            0,
        )
        or 0
    )
    errors = traffic_status.get("traffic_errors") or []

    if not congestion_segments:
        if query_count > 0 and success_count == 0:
            return [
                "실시간 교통정보 조회에 실패해 정체 구간을 안내하지 못했습니다."
            ]

        if feature_count == 0:
            return [
                "실시간 교통정보 응답에 도로 구간 데이터가 없어 정체 여부를 확인하지 못했습니다."
            ]

        if matched_count == 0:
            return [
                "실시간 교통정보는 조회됐지만 현재 안내 경로와 일치하는 교통 구간을 찾지 못했습니다."
            ]

        return [
            "현재 경로에는 길게 이어지는 서행·지체·정체 구간이 확인되지 않았습니다."
        ]

    meaningful = [
        segment
        for segment in congestion_segments
        if int(segment.get("congestion_level", 0)) >= 3
        or float(
            segment.get("congestion_distance_km", 0)
            or 0
        ) >= 1.0
    ]

    if not meaningful:
        return [
            "현재 경로에는 길게 이어지는 지체·정체 구간이 확인되지 않았습니다."
        ]

    selected = sorted(
        meaningful,
        key=lambda segment: (
            int(segment.get("congestion_level", 0)),
            float(
                segment.get("congestion_distance_km", 0)
                or 0
            ),
        ),
        reverse=True,
    )[:maximum_messages]

    messages = []

    for segment in selected:
        eta = round(float(segment.get("eta_minutes", 0) or 0))
        place = _format_congestion_place(segment)
        congestion_name = segment.get(
            "congestion_name",
            "혼잡",
        )
        distance_km = float(
            segment.get("congestion_distance_km", 0)
            or 0
        )
        speed = segment.get("average_speed_kmh")
        traffic_time = segment.get("congestion_time_minutes")

        parts = [
            f"약 {eta}분 후 {place} 약 {distance_km:.1f}km 구간이 "
            f"{congestion_name} 상태입니다"
        ]

        details = []

        if speed is not None:
            details.append(f"평균 속도 약 {float(speed):.0f}km/h")

        if traffic_time is not None and float(traffic_time) > 0:
            details.append(
                f"통과 예상 약 {float(traffic_time):.0f}분"
            )

        if details:
            parts.append("(" + ", ".join(details) + ")")

        message = " ".join(parts) + "."
        advice = _congestion_safety_advice(segment)

        if advice:
            message += " " + advice

        messages.append(message)

    return messages



def _classify_relative_risk(relative_risk):
    """상대 위험도와 화면 표시 등급을 같은 기준으로 맞춥니다."""
    value = float(relative_risk)

    if value < 0.80:
        return "낮음"
    if value < 1.20:
        return "보통"
    if value < 1.60:
        return "높음"
    return "매우 높음"


def _risk_sort_value(region):
    if region.get("accident_probability") is not None:
        return float(region["accident_probability"])

    if region.get("risk_score") is not None:
        return float(region["risk_score"])

    if region.get("relative_risk") is not None:
        return float(region["relative_risk"])

    level_order = {
        "매우 높음": 4,
        "높음": 3,
        "보통": 2,
        "낮음": 1,
    }

    return float(
        level_order.get(region.get("risk_level"), 0)
    )


def _format_risk_message(regions):
    available = [
        region
        for region in regions
        if region.get("risk_available")
    ]

    if not available:
        return None

    highest = max(available, key=_risk_sort_value)
    location = _format_location(highest)
    eta = round(float(highest.get("eta_minutes", 0)))
    prefix = (
        f"약 {eta}분 후 {location} 구간이 "
        "이번 경로에서 가장 높은 상대 위험도로 분석되었습니다"
    )

    details = []

    relative_risk = highest.get("relative_risk")
    risk_level = highest.get("risk_level")

    if relative_risk is not None:
        relative_risk = float(relative_risk)
        risk_level = _classify_relative_risk(relative_risk)

    if risk_level:
        details.append(
            f"위험 단계 {risk_level}"
        )

    if relative_risk is not None:
        details.append(
            "기준 대비 "
            f"{relative_risk:.2f}배"
        )
    elif highest.get("accident_probability") is not None:
        details.append(
            "모델 점수 "
            f"{float(highest['accident_probability']) * 100:.2f}%"
        )

    if details:
        return prefix + "(" + ", ".join(details) + ")."

    return prefix + "."


def _format_road_message(
    route_road_summary,
    route_road_result,
):
    recognized = [
        item
        for item in route_road_summary
        if item.get("도로종류") != "기타"
    ]

    if not recognized:
        return (
            "경로의 도로 등급을 정확히 확인하지 못해 "
            "도로 종류별 사고 정보는 안내에서 제외합니다."
        )

    main_road = recognized[0]

    if not _is_available(route_road_result):
        return (
            f"도로명 기준으로 {main_road['도로종류']} 이용 비중이 "
            f"약 {main_road['경로비중(%)']}%로 추정됩니다."
        )

    matched = route_road_result[
        route_road_result["도로종류"]
        == main_road["도로종류"]
    ].copy()

    if matched.empty:
        return (
            f"도로명 기준으로 {main_road['도로종류']} 이용 비중이 "
            f"약 {main_road['경로비중(%)']}%로 추정됩니다."
        )

    top_row = matched.sort_values(
        by="지역내_도로사고비중(%)",
        ascending=False,
    ).iloc[0]

    return (
        f"도로명 기준으로 {main_road['도로종류']} 이용 비중이 "
        f"약 {main_road['경로비중(%)']}%로 추정되며, "
        f"{top_row['시도']}에서는 이 도로의 사고 비중이 "
        f"{top_row['지역내_도로사고비중(%)']}%입니다."
    )


def _format_type_message(route_type_detail):
    if not _is_available(route_type_detail):
        return None

    positive = route_type_detail[
        route_type_detail["사고건수"] > 0
    ].copy()

    if positive.empty:
        return None

    grouped = (
        positive.groupby("사고형태", as_index=False)[
            "사고건수"
        ]
        .sum()
        .sort_values("사고건수", ascending=False)
    )

    accident_type = grouped.iloc[0]["사고형태"]
    safety_message = create_safety_message(accident_type)

    return (
        f"경로 지역에서는 '{accident_type}' 사고가 가장 많습니다. "
        f"{safety_message}"
    )


def _format_time_message(
    route_time_result,
    current_time_band,
):
    if not _is_available(route_time_result):
        return None

    value_column = "지역내_사고비중(%)"

    if value_column not in route_time_result.columns:
        return None

    top_row = route_time_result.sort_values(
        by=value_column,
        ascending=False,
    ).iloc[0]

    return (
        f"{top_row['시도']} 지역의 과거 사고 중 "
        f"{current_time_band} 사고 구성비는 "
        f"{top_row[value_column]}%입니다."
    )


def _format_weather_message(
    route_weather_result,
    weather,
):
    if not _is_available(route_weather_result):
        return None

    value_column = "지역내_사고비중(%)"

    if value_column not in route_weather_result.columns:
        return None

    top_row = route_weather_result.sort_values(
        by=value_column,
        ascending=False,
    ).iloc[0]

    return (
        f"{top_row['시도']} 지역의 과거 날씨별 사고 중 "
        f"{weather} 날씨 사고 구성비는 "
        f"{top_row[value_column]}%입니다."
    )


def create_user_messages(
    summary,
    regions,
    route_road_summary,
    route_road_result,
    route_type_detail,
    route_time_result,
    current_time_band,
    route_weather_result,
    weather,
    congestion_segments=None,
    traffic_status=None,
):
    """사용자에게 읽어 줄 최대 7개의 안내 문장을 만듭니다."""

    messages = [
        (
            f"총 거리는 {summary['distance_km']}km이고, "
            f"예상 이동시간은 약 "
            f"{round(summary['duration_minutes'])}분입니다."
        )
    ]

    region_message = _format_region_timeline(regions)

    if region_message:
        messages.append(region_message)

    messages.extend(
        _format_congestion_messages(
            congestion_segments or [],
            traffic_status=traffic_status,
            maximum_messages=2,
        )
    )

    candidates = [
        _format_risk_message(regions),
        _format_time_message(
            route_time_result,
            current_time_band,
        ),
        _format_weather_message(
            route_weather_result,
            weather,
        ),
        _format_type_message(route_type_detail),
        _format_road_message(
            route_road_summary,
            route_road_result,
        ),
    ]

    for message in candidates:
        if message:
            messages.append(message)

    return messages[:7]

