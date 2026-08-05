"""인터넷 호출 없이 패치 핵심 로직을 확인하는 간단한 테스트."""

from analysis import region_analysis
from analysis.risk_model_adapter import (
    attach_risk_predictions,
)
from services.traffic_service import (
    summarize_traffic_near_point,
)


def test_region_segments():
    timeline = [
        {
            "longitude": 127.0 + index * 0.01,
            "latitude": 37.5,
            "elapsed_seconds": index * 600,
            "distance_m": index * 5000,
        }
        for index in range(7)
    ]

    original_timeline = region_analysis.extract_route_timeline
    original_lookup = region_analysis.coordinate_to_region

    region_analysis.extract_route_timeline = lambda route: timeline

    def fake_lookup(longitude, latitude):
        if longitude < 127.035:
            return {
                "시도_원본": "서울특별시",
                "시도": "서울",
                "시군구": "강남구",
                "전체주소": "서울특별시 강남구",
            }

        return {
            "시도_원본": "경기도",
            "시도": "경기",
            "시군구": "성남시",
            "전체주소": "경기도 성남시",
        }

    region_analysis.coordinate_to_region = fake_lookup

    try:
        regions = region_analysis.find_route_regions({})
    finally:
        region_analysis.extract_route_timeline = original_timeline
        region_analysis.coordinate_to_region = original_lookup

    assert len(regions) == 2
    assert regions[0]["시도"] == "서울"
    assert regions[1]["시도"] == "경기"
    assert "duration_minutes" in regions[0]
    assert "distance_km" in regions[0]


def test_traffic_summary():
    data = {
        "features": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [127.0, 37.5],
                        [127.01, 37.5],
                    ],
                },
                "properties": {
                    "congestion": 3,
                    "speed": 22,
                    "description": "지체",
                    "name": "테스트 도로",
                },
            }
        ]
    }

    result = summarize_traffic_near_point(
        data,
        longitude=127.005,
        latitude=37.5,
    )

    assert result["traffic_available"] is True
    assert result["congestion_name"] == "지체"
    assert result["average_speed_kmh"] == 22.0


def test_model_adapter():
    regions = [
        {
            "시도": "경기",
            "시군구": "성남시",
            "eta_minutes": 15,
            "duration_minutes": 20,
            "distance_km": 12,
            "congestion_level": 3,
            "congestion_name": "지체",
            "average_speed_kmh": 21,
        }
    ]

    def fake_predictor(features):
        assert features["시군구"] == "성남시"
        return {
            "probability": 0.04,
            "risk_level": "높음",
        }

    result = attach_risk_predictions(
        regions=regions,
        weather="맑음",
        current_time_band="10시~12시",
        main_road_type="일반국도",
        predictor=fake_predictor,
    )

    assert result[0]["risk_available"] is True
    assert result[0]["accident_probability"] == 0.04
    assert result[0]["risk_level"] == "높음"


if __name__ == "__main__":
    test_region_segments()
    test_traffic_summary()
    test_model_adapter()
    print("모든 오프라인 테스트를 통과했습니다.")
