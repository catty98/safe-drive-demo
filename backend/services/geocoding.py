from functools import lru_cache

import requests

from config import (
    TMAP_API_VERSION,
    TMAP_APP_KEY,
    TMAP_REVERSE_GEOCODING_URL,
)


NOMINATIM_SEARCH_URL = (
    "https://nominatim.openstreetmap.org/search"
)

HEADERS = {
    "User-Agent": "university-safe-navigation-project/1.0"
}


class ReverseGeocodingError(RuntimeError):
    """TMAP 좌표→지역 변환 실패를 나타냅니다."""


def search_place(query):
    """
    주소나 장소명을 검색하여 위도·경도를 반환합니다.

    기존 기능과의 호환성을 위해 장소 검색은 Nominatim을 유지합니다.
    """

    query = query.strip()

    if not query:
        raise ValueError("장소명이 입력되지 않았습니다.")

    params = {
        "q": query,
        "format": "json",
        "limit": 1,
        "countrycodes": "kr",
    }

    response = requests.get(
        NOMINATIM_SEARCH_URL,
        headers=HEADERS,
        params=params,
        timeout=15,
    )

    response.raise_for_status()
    results = response.json()

    if not results:
        raise ValueError(
            f"'{query}'에 해당하는 장소를 찾지 못했습니다."
        )

    place = results[0]

    return {
        "name": query,
        "display_name": place.get("display_name", ""),
        "longitude": float(place["lon"]),
        "latitude": float(place["lat"]),
    }


def _extract_tmap_error(data):
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


@lru_cache(maxsize=2048)
def _coordinate_to_region_cached(
    rounded_longitude,
    rounded_latitude,
):
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
        "lat": rounded_latitude,
        "lon": rounded_longitude,
        "coordType": "WGS84GEO",
        "addressType": "A00",
        "coordYn": "N",
    }

    try:
        response = requests.get(
            TMAP_REVERSE_GEOCODING_URL,
            headers=headers,
            params=params,
            timeout=15,
        )
    except requests.RequestException as exc:
        raise ReverseGeocodingError(
            f"TMAP 지역 조회 서버에 연결하지 못했습니다: {exc}"
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ReverseGeocodingError(
            "TMAP 지역 조회 응답을 JSON으로 해석하지 못했습니다."
        ) from exc

    if not response.ok:
        raise ReverseGeocodingError(
            "TMAP 지역 조회 실패 "
            f"(HTTP {response.status_code}): "
            f"{_extract_tmap_error(data)}"
        )

    address = data.get("addressInfo") or {}

    sido_original = str(
        address.get("city_do")
        or address.get("cityDo")
        or ""
    ).strip()

    sigungu = str(
        address.get("gu_gun")
        or address.get("guGun")
        or ""
    ).strip()

    full_address = str(
        address.get("fullAddress")
        or ""
    ).strip()

    return {
        "시도_원본": sido_original,
        "시도": normalize_sido_name(sido_original),
        "시군구": sigungu,
        "전체주소": full_address,
    }


def coordinate_to_region(longitude, latitude):
    """
    TMAP Reverse Geocoding으로 좌표를 시도·시군구로 변환합니다.

    좌표를 소수점 5자리로 반올림하여 같은 지점의 중복 요청을
    메모리 캐시에서 재사용합니다.
    """

    rounded_longitude = round(float(longitude), 5)
    rounded_latitude = round(float(latitude), 5)

    return dict(
        _coordinate_to_region_cached(
            rounded_longitude,
            rounded_latitude,
        )
    )


def normalize_sido_name(region_name):
    """TMAP 지역명을 TAAS 시도 명칭으로 통일합니다."""

    region_name = str(region_name).strip()

    name_map = {
        "서울특별시": "서울",
        "부산광역시": "부산",
        "대구광역시": "대구",
        "인천광역시": "인천",
        "광주광역시": "광주",
        "대전광역시": "대전",
        "울산광역시": "울산",
        "세종특별자치시": "세종",
        "경기도": "경기",
        "강원특별자치도": "강원",
        "강원도": "강원",
        "충청북도": "충북",
        "충청남도": "충남",
        "전북특별자치도": "전북",
        "전라북도": "전북",
        "전라남도": "전남",
        "경상북도": "경북",
        "경상남도": "경남",
        "제주특별자치도": "제주",
    }

    return name_map.get(region_name, region_name)
