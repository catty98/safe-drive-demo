import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"


ACCIDENT_FILES = {
    "type": RAW_DIR / "지역별 사고 유형.xlsx",
    "road": RAW_DIR / "지역별 사고 당시 도로.xlsx",
    "time": RAW_DIR / "지역별 사고 당시 시간.xlsx",
    "weather": RAW_DIR / "지역별 사고 당시 날씨.xlsx",
}


# 개발 중에는 프로젝트 루트의 secret_config.py에서 읽고,
# 배포 환경에서는 TMAP_APP_KEY 환경변수에서 읽습니다.
try:
    from secret_config import TMAP_APP_KEY as _LOCAL_TMAP_APP_KEY
except ImportError:
    _LOCAL_TMAP_APP_KEY = ""


TMAP_APP_KEY = (
    _LOCAL_TMAP_APP_KEY
    or os.getenv("TMAP_APP_KEY", "")
).strip()

TMAP_API_VERSION = "1"
TMAP_ROUTE_URL = "https://apis.openapi.sk.com/tmap/routes"
TMAP_REVERSE_GEOCODING_URL = (
    "https://apis.openapi.sk.com/tmap/geo/reversegeocoding"
)
TMAP_TRAFFIC_URL = "https://apis.openapi.sk.com/tmap/traffic"
