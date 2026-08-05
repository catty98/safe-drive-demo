from services.route_service import (
    get_route_summary,
    request_route,
    summarize_route_road_types,
)


def main():
    # 서울시청 -> 강남역. 장소 검색 API를 거치지 않고
    # TMAP AppKey와 경로 API 연결만 확인하는 테스트입니다.
    origin = {
        "name": "서울시청",
        "longitude": 126.9783882,
        "latitude": 37.5666103,
    }

    destination = {
        "name": "강남역",
        "longitude": 127.027621,
        "latitude": 37.497952,
    }

    route = request_route(
        origin=origin,
        destination=destination,
    )

    summary = get_route_summary(route)
    road_summary = summarize_route_road_types(route)

    print("[TMAP 연결 성공]")
    print(f"총 거리: {summary['distance_km']}km")
    print(
        f"예상 이동시간: "
        f"{summary['duration_minutes']}분"
    )
    print(f"경로 좌표 수: {len(route['coordinates'])}")
    print(f"도로 구간 수: {len(route['segments'])}")

    print("\n[도로 종류 요약]")

    for item in road_summary:
        print(
            f"- {item['도로종류']}: "
            f"{item['거리_km']}km "
            f"({item['경로비중(%)']}%)"
        )


if __name__ == "__main__":
    main()
