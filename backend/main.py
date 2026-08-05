from analysis.region_analysis import find_route_regions
from analysis.result_summary import create_user_messages
from analysis.risk_model_adapter import (
    attach_risk_predictions,
)
from services.geocoding import search_place
from services.route_service import (
    get_route_summary,
    request_route,
    summarize_route_road_types,
)
from services.traffic_service import (
    analyze_route_traffic,
)
from utils.progress import ConsoleProgressBar
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


def question_weather():
    weather_options = {
        "1": "맑음",
        "2": "흐림",
        "3": "비",
        "4": "안개",
        "5": "눈",
    }

    while True:
        print(
            "\n현재 날씨를 선택해 주세요.\n"
            "1번: 맑음\n"
            "2번: 흐림\n"
            "3번: 비\n"
            "4번: 안개\n"
            "5번: 눈"
        )

        answer = input("번호 입력: ").strip()

        if answer in weather_options:
            return weather_options[answer]

        print("1번부터 5번 사이의 숫자를 입력해 주세요.")


def main():
    # 1. 출발지와 도착지 입력
    origin_text = input(
        "출발지를 입력하세요: "
    ).strip()

    destination_text = input(
        "도착지를 입력하세요: "
    ).strip()

    # 2. 장소를 좌표로 변환
    print("\n출발지를 검색하고 있습니다.")
    origin = search_place(origin_text)

    print("도착지를 검색하고 있습니다.")
    destination = search_place(destination_text)

    # 3. TMAP 경로 검색
    print("도로 경로를 검색하고 있습니다.")
    route = request_route(
        origin=origin,
        destination=destination,
    )

    summary = get_route_summary(route)

    # 4. 지역별 경로 구간 생성
    regions = find_route_regions(route)

    # 5. 경로 전체에서 실제 안내선과 가까운 정체 구간 분석
    print()
    traffic_progress = ConsoleProgressBar(
        "실시간 교통정보 분석",
    )

    try:
        traffic_analysis = analyze_route_traffic(
            route=route,
            regions=regions,
            progress_callback=traffic_progress.update,
        )
    except Exception as exc:
        traffic_progress.fail(str(exc))
        raise
    else:
        traffic_progress.finish("완료")
    regions = traffic_analysis["regions"]
    congestion_segments = traffic_analysis[
        "congestion_segments"
    ]

    traffic_status = {
        "traffic_errors": traffic_analysis.get(
            "traffic_errors",
            [],
        ),
        "traffic_query_count": traffic_analysis.get(
            "traffic_query_count",
            0,
        ),
        "successful_traffic_query_count": traffic_analysis.get(
            "successful_traffic_query_count",
            0,
        ),
        "traffic_feature_count": traffic_analysis.get(
            "traffic_feature_count",
            0,
        ),
        "matched_traffic_link_count": traffic_analysis.get(
            "matched_traffic_link_count",
            0,
        ),
    }

    # 정체 문구가 없을 때 원인을 바로 확인할 수 있는 진단 출력입니다.
    print(
        "교통정보 조회 결과: "
        f"요청 {traffic_status['traffic_query_count']}회, "
        f"성공 {traffic_status['successful_traffic_query_count']}회, "
        f"도로 링크 {traffic_status['traffic_feature_count']}개, "
        f"경로 일치 {traffic_status['matched_traffic_link_count']}개, "
        f"혼잡 구간 {len(congestion_segments)}개"
    )

    if traffic_status["traffic_errors"]:
        print(
            "교통정보 오류 예시: "
            f"{traffic_status['traffic_errors'][0]}"
        )

    route_sidos = []

    for region in regions:
        sido = region.get("시도", "").strip()

        if sido and sido not in route_sidos:
            route_sidos.append(sido)

    # 6. 실제 경로에서 확인 가능한 도로 종류 계산
    route_road_summary = summarize_route_road_types(
        route
    )

    recognized_road_types = [
        item["도로종류"]
        for item in route_road_summary
        if item["도로종류"] != "기타"
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
            route_road_result["도로종류"].isin(
                recognized_road_types
            )
        ].copy()
    else:
        route_road_result = route_road_result.iloc[0:0]

    # 7. 경로상 지역의 사고 유형 분석
    type_data = load_preprocessed_type_data()

    route_type_detail = select_type_analysis(
        type_long_df=type_data["detail_long"],
        sidos=route_sidos,
        min_accidents_for_severity=30,
    )

    # 8. 현재 시간대 분석
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

    # 9. 현재 날씨 분석
    weather = question_weather()

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

    # 10. 모델이 연결돼 있으면 지역별 사고 위험 예측
    regions = attach_risk_predictions(
        regions=regions,
        weather=weather,
        current_time_band=current_time_band,
        main_road_type=main_road_type,
    )

    # 11. 사용자용 짧은 문장 생성 및 출력
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
        congestion_segments=congestion_segments,
        traffic_status=traffic_status,
    )

    print("\n[안전운전 안내]")

    for message in messages:
        print(f"- {message}")


if __name__ == "__main__":
    main()
