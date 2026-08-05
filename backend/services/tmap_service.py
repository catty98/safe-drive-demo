from typing import Any

import requests

from config import (
    TMAP_API_VERSION,
    TMAP_APP_KEY,
    TMAP_ROUTE_URL,
)


class TmapRouteError(RuntimeError):
    """TMAP 경로 API 호출 실패를 나타냅니다."""


def _validate_location(location: dict[str, Any], label: str) -> None:
    required_keys = ("longitude", "latitude")
    missing = [key for key in required_keys if key not in location]

    if missing:
        raise ValueError(
            f"{label}에 필요한 좌표가 없습니다: {', '.join(missing)}"
        )


def _extract_error_message(
    data,
    raw_text="",
):
    """
    TMAP 오류 응답을 읽기 쉬운 문자열로 변환합니다.

    공식 오류 형식:
    {
        "error": {
            "id": "403",
            "category": "gw",
            "code": "INVALID_API_KEY",
            "message": "Forbidden"
        }
    }
    """

    if isinstance(data, dict):
        error = data.get("error")

        if isinstance(error, dict):
            return (
                f"id={error.get('id')}, "
                f"category={error.get('category')}, "
                f"code={error.get('code')}, "
                f"message={error.get('message')}"
            )

        # 응답 형식이 다른 경우를 위한 보조 처리
        return (
            f"id={data.get('id')}, "
            f"category={data.get('category')}, "
            f"code={data.get('code')}, "
            f"message={data.get('message')}, "
            f"response={data}"
        )

    raw_text = str(raw_text).strip()

    if raw_text:
        return f"response={raw_text[:500]}"

    return "오류 응답 내용을 확인하지 못했습니다."


def request_tmap_route(
    origin: dict[str, Any],
    destination: dict[str, Any],
    search_option: str = "0",
) -> dict[str, Any]:
    """
    출발지와 목적지 좌표로 TMAP 자동차 경로를 요청합니다.

    search_option="0"은 교통 상황을 반영한 기본 추천 경로입니다.
    반환값은 TMAP의 원본 GeoJSON 응답입니다.
    """

    if not TMAP_APP_KEY:
        raise RuntimeError(
            "TMAP AppKey가 설정되지 않았습니다. "
            "프로젝트 루트에 secret_config.py를 만들고 "
            "TMAP_APP_KEY를 입력하세요."
        )

    _validate_location(origin, "출발지")
    _validate_location(destination, "도착지")

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "appKey": TMAP_APP_KEY,
    }

    params = {
        "version": TMAP_API_VERSION,
        "format": "json",
    }

    body = {
        "startX": str(origin["longitude"]),
        "startY": str(origin["latitude"]),
        "endX": str(destination["longitude"]),
        "endY": str(destination["latitude"]),
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "startName": str(origin.get("name", "출발지")),
        "endName": str(destination.get("name", "도착지")),
        "searchOption": str(search_option),
        "sort": "index",
        "mainRoadInfo": "Y",
    }

    try:
        response = requests.post(
            TMAP_ROUTE_URL,
            headers=headers,
            params=params,
            json=body,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise TmapRouteError(
            f"TMAP 서버에 연결하지 못했습니다: {exc}"
        ) from exc

    if response.status_code == 204:
        raise TmapRouteError(
            "현재 GPS 위치에서 자동차 경로를 찾지 못했습니다. "
            "에뮬레이터 위치를 실제 도로 위 좌표로 변경한 뒤 다시 시도하세요."
        )

    try:
        data = response.json()
    except ValueError as exc:
        content_type = response.headers.get(
            "Content-Type",
            "알 수 없음",
        )

        response_preview = response.text[:1000]

        raise TmapRouteError(
            "TMAP 경로 응답을 JSON 객체로 해석하지 못했습니다. "
            f"HTTP 상태: {response.status_code}, "
            f"Content-Type: {content_type}, "
            f"최종 요청 주소: {response.url}, "
            f"응답 내용: {response_preview}"
        ) from exc

    if not response.ok:
        message = _extract_error_message(
            data=data,
            raw_text=response.text,
    )

        raise TmapRouteError(
            f"TMAP 경로 조회 실패 "
            f"(HTTP {response.status_code}): "
            f"{message}"
            )

    if not isinstance(data, dict):
        raise TmapRouteError(
            "TMAP 경로 응답을 JSON 객체로 해석하지 못했습니다: "
            f"{_extract_error_message(data, response.text)}"
        )

    features = data.get("features", [])

    if not isinstance(features, list) or not features:
        message = _extract_error_message(
            data=data,
            raw_text=response.text,
        )
        raise TmapRouteError(
            f"TMAP 경로 데이터가 없습니다: {message}"
        )

    return data
