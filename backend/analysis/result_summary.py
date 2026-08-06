import pandas as pd

from analysis.safety_message import (
    create_condition_safety_message,
    create_road_safety_message,
    create_safety_message,
)


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


def _display_accident_type(accident_type):
    return str(accident_type or "").replace("_", " ").strip()


def _find_top_accident_type(route_type_detail, sido):
    """정체 구간의 시도와 같은 TAAS 사고유형 1위를 찾습니다."""

    if not _is_available(route_type_detail) or not sido:
        return None

    required_columns = {"시도", "사고형태", "사고건수"}

    if not required_columns.issubset(route_type_detail.columns):
        return None

    selected = route_type_detail[
        (route_type_detail["시도"] == sido)
        & (route_type_detail["사고건수"] > 0)
    ].copy()

    if selected.empty:
        return None

    # 세분류별 사고건수를 기준으로 해당 시도의 최다 유형을 선택합니다.
    top_row = selected.sort_values(
        by=["사고건수", "사고100건당_사망자수"],
        ascending=[False, False],
        na_position="last",
    ).iloc[0]

    return {
        "사고형태": top_row["사고형태"],
        "사고건수": float(top_row["사고건수"]),
        "지역내_사고비중(%)": top_row.get("지역내_사고비중(%)"),
    }


def _build_congestion_accident_advice(segment, accident_type):
    type_advice = create_safety_message(accident_type)
    level = int(segment.get("congestion_level", 0) or 0)

    if level >= 3 and accident_type != "차대차_추돌":
        return (
            "정체 꼬리의 급정지에 대비해 먼저 차간 거리를 확보하세요. "
            + type_advice
        )

    return type_advice


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
    route_type_detail=None,
    traffic_status=None,
    maximum_messages=2,
):
    """정체 위치·상태·지역별 주요 사고유형·행동요령을 함께 반환합니다."""

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

    if not congestion_segments:
        if query_count > 0 and success_count == 0:
            return [
                "실시간 교통정보 조회에 실패해 정체 구간을 안내하지 못했습니다."
            ]

        if feature_count == 0:
            return [
                "실시간 교통정보에 도로 구간 데이터가 없어 정체 여부를 확인하지 못했습니다."
            ]

        if matched_count == 0:
            return [
                "실시간 교통정보는 조회됐지만 현재 경로와 일치하는 구간을 찾지 못했습니다."
            ]

        return [
            "현재 경로에는 길게 이어지는 지체·정체 구간이 확인되지 않았습니다."
        ]

    meaningful = [
        segment
        for segment in congestion_segments
        if int(segment.get("congestion_level", 0)) >= 3
        or float(segment.get("congestion_distance_km", 0) or 0) >= 1.0
    ]

    if not meaningful:
        return [
            "현재 경로에는 길게 이어지는 지체·정체 구간이 확인되지 않았습니다."
        ]

    # 운전자에게 먼저 닥칠 구간을 우선 안내합니다.
    selected = sorted(
        meaningful,
        key=lambda segment: (
            float(segment.get("eta_minutes", 0) or 0),
            -int(segment.get("congestion_level", 0) or 0),
        ),
    )[:maximum_messages]

    messages = []

    for segment in selected:
        eta = round(float(segment.get("eta_minutes", 0) or 0))
        place = _format_congestion_place(segment)
        congestion_name = segment.get("congestion_name", "혼잡")
        distance_km = float(
            segment.get("congestion_distance_km", 0) or 0
        )
        speed = segment.get("average_speed_kmh")
        traffic_time = segment.get("congestion_time_minutes")

        if eta <= 0:
            prefix = f"현재 {place}"
        else:
            prefix = f"약 {eta}분 후 {place}"

        message = (
            f"{prefix} 약 {distance_km:.1f}km 구간이 "
            f"{congestion_name} 상태입니다"
        )

        details = []

        if speed is not None:
            details.append(f"평균 속도 약 {float(speed):.0f}km/h")

        if traffic_time is not None and float(traffic_time) > 0:
            details.append(f"통과 예상 약 {float(traffic_time):.0f}분")

        if details:
            message += " (" + ", ".join(details) + ")"

        message += "."

        sido = str(segment.get("시도", "")).strip()
        top_type = _find_top_accident_type(
            route_type_detail,
            sido,
        )

        if top_type:
            accident_type = top_type["사고형태"]
            type_label = _display_accident_type(accident_type)
            share = top_type.get("지역내_사고비중(%)")

            message += (
                f" {sido} 전체 사고 통계에서는 "
                f"{type_label} 사고가 가장 많습니다"
            )

            if pd.notna(share):
                message += f"(지역 사고의 {float(share):.1f}%)"

            message += ". " + _build_congestion_accident_advice(
                segment,
                accident_type,
            )
        else:
            advice = _congestion_safety_advice(segment)

            if advice:
                message += " " + advice

        messages.append(message)

    return messages


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


def _format_risk_message(regions, route_type_detail=None):
    available = [
        region
        for region in regions
        if region.get("risk_available")
    ]

    if not available:
        return None

    highest = max(available, key=_risk_sort_value)
    location = _format_location(highest)
    eta = round(float(highest.get("eta_minutes", 0) or 0))

    if eta <= 0:
        prefix = f"현재 {location} 구간의 예측 위험도가 가장 높습니다"
    else:
        prefix = (
            f"약 {eta}분 후 {location} 구간의 예측 위험도가 "
            "이번 경로에서 가장 높습니다"
        )

    details = []

    if highest.get("risk_level"):
        details.append(f"위험 단계 {highest['risk_level']}")

    if highest.get("risk_score") is not None:
        details.append(
            f"위험점수 {float(highest['risk_score']):.1f}점"
        )

    if highest.get("relative_risk") is not None:
        details.append(
            f"기준 대비 {float(highest['relative_risk']):.2f}배"
        )

    message = prefix

    if details:
        message += " (" + ", ".join(details) + ")"

    message += "."

    sido = str(highest.get("시도", "")).strip()
    top_type = _find_top_accident_type(route_type_detail, sido)

    if top_type:
        accident_type = top_type["사고형태"]
        message += (
            f" {sido} 전체 통계에서 가장 많은 "
            f"{_display_accident_type(accident_type)} 사고에 대비해 "
            f"{create_safety_message(accident_type)}"
        )
    else:
        message += " 진입 전에 속도를 낮추고 주변 차량과 보행자를 확인하세요."

    return message


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
        return None

    main_road = recognized[0]
    road_type = main_road["도로종류"]
    message = (
        f"경로에서 {road_type} 이용 비중이 "
        f"약 {main_road['경로비중(%)']}%입니다. "
        f"{create_road_safety_message(road_type)}"
    )

    if not _is_available(route_road_result):
        return message

    matched = route_road_result[
        route_road_result["도로종류"] == road_type
    ].copy()

    if matched.empty:
        return message

    top_row = matched.sort_values(
        by="지역내_도로사고비중(%)",
        ascending=False,
    ).iloc[0]

    return (
        f"{top_row['시도']}에서는 {road_type} 사고가 지역 사고의 "
        f"{float(top_row['지역내_도로사고비중(%)']):.1f}%를 차지합니다. "
        f"{create_road_safety_message(road_type)}"
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
        f"현재 {current_time_band}에는 {top_row['시도']}에서 "
        f"하루 사고의 {top_row[value_column]}%가 발생합니다."
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
        f"{weather}일 때는 {top_row['시도']}에서 "
        f"지역 사고의 {top_row[value_column]}%가 발생합니다."
    )


def _format_condition_message(
    current_time_band,
    weather,
):
    return (
        f"현재 주행 조건은 {current_time_band}, {weather}입니다. "
        f"{create_condition_safety_message(weather, current_time_band)}"
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
    """안전 행동요령을 우선한 최대 6개의 안내 문장을 만듭니다."""

    messages = [
        (
            f"총 거리는 {summary['distance_km']}km이고, "
            f"예상 이동시간은 약 "
            f"{round(summary['duration_minutes'])}분입니다."
        )
    ]

    # 앱에 통과 지역이 별도 카드로 표시되므로,
    # 안전운전 안내에서는 중복 지역 나열보다 행동요령을 우선합니다.
    messages.extend(
        _format_congestion_messages(
            congestion_segments or [],
            route_type_detail=route_type_detail,
            traffic_status=traffic_status,
            maximum_messages=2,
        )
    )

    candidates = [
        _format_risk_message(
            regions,
            route_type_detail=route_type_detail,
        ),
        _format_condition_message(
            current_time_band,
            weather,
        ),
        _format_road_message(
            route_road_summary,
            route_road_result,
        ),
    ]

    for message in candidates:
        if message and message not in messages:
            messages.append(message)

    return messages[:6]
