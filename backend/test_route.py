from analysis.region_analysis import find_route_regions
from services.geocoding import search_place
from services.route_service import (
    get_route_summary,
    request_route,
)


def main():

    origin_text = input(
        "출발지를 입력하세요: "
    ).strip()

    destination_text = input(
        "도착지를 입력하세요: "
    ).strip()

    origin = search_place(origin_text)
    destination = search_place(destination_text)

    route = request_route(
        origin=origin,
        destination=destination,
    )

    summary = get_route_summary(route)

    print("\n[경로 정보]")
    print(
        f"총 거리: {summary['distance_km']}km"
    )
    print(
        f"예상 이동시간: "
        f"{summary['duration_minutes']}분"
    )

    regions = find_route_regions(route)

    print("\n[예상 통과 지역]")

    for region in regions:
        print(
            f"- {region['시도']} "
            f"{region['시군구']}"
        )


if __name__ == "__main__":
    main()