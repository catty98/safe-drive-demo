from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
SCORES_FILE = BASE_DIR.parent / "model_artifacts" / "regional_risk_scores.json"


@lru_cache(maxsize=1)
def _load_region_scores() -> dict[str, dict[str, Any]]:
    if not SCORES_FILE.exists():
        return {}

    payload = json.loads(SCORES_FILE.read_text(encoding="utf-8"))
    regions = payload.get("regions") or []

    return {
        str(item.get("시도", "")).strip(): item
        for item in regions
        if str(item.get("시도", "")).strip()
    }


def predict_region_risk(features):
    """
    시도별 상대 위험 결과를 앱의 기존 모델 어댑터 형식으로 반환합니다.

    이 결과는 실시간 사고 확률이 아닙니다.
    과거 시도별 사고 통계와 주요도로 대표교통량을 기반으로 계산된
    지역 간 상대 위험 점수입니다.
    """
    sido = str(features.get("시도", "")).strip()
    if not sido:
        return None

    item = _load_region_scores().get(sido)
    if item is None:
        return None

    return {
        "risk_level": item.get("risk_level", "정보없음"),
        # 기존 어댑터는 risk_score를 그대로 전달합니다.
        # 앱에서 0~1 범위를 기대할 가능성을 고려해 100점 값을 0~1로 변환합니다.
        "risk_score": round(float(item.get("risk_score", 0.0)) / 100.0, 4),
        "relative_risk": float(item.get("relative_risk", 1.0)),
        "model_version": str(item.get("model_version", "unknown")),
    }
