from concurrent.futures import (
    ThreadPoolExecutor,
    as_completed,
)
import math

from services.geocoding import coordinate_to_region
from services.route_service import extract_route_timeline


def _choose_sample_count(timeline):
    """
    약 12분 간격으로 경로를 확인하되 6~12개로 제한합니다.

    Reverse Geocoding은 병렬 실행하므로 기존의 1.1초 강제 대기는
    사용하지 않습니다.
    """

    if not timeline:
        return 0

    total_minutes = (
        float(timeline[-1].get("elapsed_seconds", 0))
        / 60
    )

    estimated = math.ceil(total_minutes / 12) + 1
    return max(6, min(12, estimated))


def sample_route_timeline(
    timeline,
    maximum_points=None,
):
    """누적시간을 기준으로 경로 지점을 고르게 선택합니다."""

    if not timeline:
        return []

    if maximum_points is None:
        maximum_points = _choose_sample_count(timeline)

    maximum_points = max(2, int(maximum_points))

    if len(timeline) <= maximum_points:
        return timeline

    total_seconds = float(
        timeline[-1].get("elapsed_seconds", 0)
    )

    if total_seconds <= 0:
        return timeline[:maximum_points]

    target_times = [
        total_seconds * index / (maximum_points - 1)
        for index in range(maximum_points)
    ]

    sampled = []
    timeline_index = 0

    for target_time in target_times:
        while (
            timeline_index < len(timeline) - 1
            and float(
                timeline[timeline_index].get(
                    "elapsed_seconds",
                    0,
                )
            ) < target_time
        ):
            timeline_index += 1

        sampled.append(timeline[timeline_index])

    return sampled


def _lookup_regions_parallel(points, max_workers=4):
    if not points:
        return []

    results = [None] * len(points)
    worker_count = min(max_workers, len(points))

    with ThreadPoolExecutor(
        max_workers=worker_count
    ) as executor:
        future_map = {
            executor.submit(
                coordinate_to_region,
                point["longitude"],
                point["latitude"],
            ): index
            for index, point in enumerate(points)
        }

        completed_count = 0

        for future in as_completed(future_map):
            index = future_map[future]
            completed_count += 1

            print(
                "지역 확인 중... "
                f"({completed_count}/{len(points)})"
            )

            try:
                results[index] = future.result()
            except Exception as exc:
                # 일부 지점 조회 실패가 전체 분석을 중단시키지 않게 합니다.
                results[index] = {
                    "시도_원본": "",
                    "시도": "",
                    "시군구": "",
                    "전체주소": "",
                    "조회오류": str(exc),
                }

    return results


def _build_region_segments(
    sampled_points,
    region_results,
    timeline,
):
    annotated = []

    for point, region in zip(
        sampled_points,
        region_results,
    ):
        annotated.append(
            {
                **point,
                **(region or {}),
            }
        )

    # 조회 실패 지점은 바로 앞의 정상 지역으로 보완합니다.
    previous_region = None

    for item in annotated:
        region_key = (
            item.get("시도", ""),
            item.get("시군구", ""),
        )

        if any(region_key):
            previous_region = {
                key: item.get(key, "")
                for key in [
                    "시도_원본",
                    "시도",
                    "시군구",
                    "전체주소",
                ]
            }
        elif previous_region:
            item.update(previous_region)

    if not annotated:
        return []

    runs = []
    run_start = 0

    for index in range(1, len(annotated)):
        previous_key = (
            annotated[index - 1].get("시도", ""),
            annotated[index - 1].get("시군구", ""),
        )
        current_key = (
            annotated[index].get("시도", ""),
            annotated[index].get("시군구", ""),
        )

        if current_key != previous_key:
            runs.append((run_start, index - 1))
            run_start = index

    runs.append((run_start, len(annotated) - 1))

    total_seconds = float(
        timeline[-1].get("elapsed_seconds", 0)
    )
    total_distance_m = float(
        timeline[-1].get("distance_m", 0)
    )

    segments = []

    for run_number, (start_index, end_index) in enumerate(runs):
        start_point = annotated[start_index]
        representative = annotated[
            (start_index + end_index) // 2
        ]

        if run_number + 1 < len(runs):
            next_start_index = runs[run_number + 1][0]
            exit_point = annotated[next_start_index]
            exit_seconds = float(
                exit_point.get("elapsed_seconds", 0)
            )
            exit_distance_m = float(
                exit_point.get("distance_m", 0)
            )
        else:
            exit_seconds = total_seconds
            exit_distance_m = total_distance_m

        entry_seconds = float(
            start_point.get("elapsed_seconds", 0)
        )
        entry_distance_m = float(
            start_point.get("distance_m", 0)
        )

        segments.append(
            {
                "시도_원본": representative.get(
                    "시도_원본",
                    "",
                ),
                "시도": representative.get("시도", ""),
                "시군구": representative.get("시군구", ""),
                "전체주소": representative.get(
                    "전체주소",
                    "",
                ),
                # 기존 result_summary.py와 호환되는 필드
                "eta_minutes": round(entry_seconds / 60),
                # 모델·교통정보 연결용 필드
                "entry_minutes": round(
                    entry_seconds / 60,
                    1,
                ),
                "exit_minutes": round(
                    exit_seconds / 60,
                    1,
                ),
                "duration_minutes": round(
                    max(0.0, exit_seconds - entry_seconds)
                    / 60,
                    1,
                ),
                "entry_distance_km": round(
                    entry_distance_m / 1000,
                    2,
                ),
                "exit_distance_km": round(
                    exit_distance_m / 1000,
                    2,
                ),
                "distance_km": round(
                    max(
                        0.0,
                        exit_distance_m - entry_distance_m,
                    )
                    / 1000,
                    2,
                ),
                "longitude": float(
                    representative["longitude"]
                ),
                "latitude": float(
                    representative["latitude"]
                ),
            }
        )

    return segments


def find_route_regions(route):
    """
    경로를 지역별 구간으로 나눠 반환합니다.

    기존 필드인 eta_minutes를 유지하면서 지역별 주행시간·거리와
    대표 좌표를 추가합니다.
    """

    timeline = extract_route_timeline(route)
    sampled_timeline = sample_route_timeline(timeline)

    region_results = _lookup_regions_parallel(
        sampled_timeline,
        max_workers=4,
    )

    return _build_region_segments(
        sampled_points=sampled_timeline,
        region_results=region_results,
        timeline=timeline,
    )
