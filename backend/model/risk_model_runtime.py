from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

FEATURE_COLUMNS = [
    "시도", "시군구", "feature_group", "condition",
    "feature_year", "lag1_count", "lag2_count", "lag3_count",
    "rolling3_mean", "rolling3_std", "trend3", "lag1_total",
    "lag1_share", "lag2_share", "rolling3_share",
]
CATEGORICAL_COLUMNS = ["시도", "시군구", "feature_group", "condition"]

SIDO_ALIASES = {
    "서울특별시": "서울", "부산광역시": "부산", "대구광역시": "대구",
    "인천광역시": "인천", "광주광역시": "광주", "대전광역시": "대전",
    "울산광역시": "울산", "세종특별자치시": "세종", "경기도": "경기",
    "강원특별자치도": "강원", "강원도": "강원", "충청북도": "충북",
    "충청남도": "충남", "전북특별자치도": "전북", "전라북도": "전북",
    "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
    "제주특별자치도": "제주",
}
WEATHER_ALIASES = {
    "맑음": "맑음", "구름많음": "흐림", "흐림": "흐림", "비": "비",
    "비/눈": "눈", "눈": "눈", "안개": "안개", "기타": "기타/불명",
    "정보없음": "기타/불명",
}
ROAD_ALIASES = {
    "일반국도": "일반국도", "국도": "일반국도", "지방도": "지방도",
    "특별광역시도": "특별광역시도", "특별시도": "특별광역시도",
    "광역시도": "특별광역시도", "시도": "시도", "군도": "군도",
    "고속국도": "고속국도", "고속도로": "고속국도", "기타": "기타",
}


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _normalize_sido(value):
    value = _clean(value)
    return SIDO_ALIASES.get(value, value)


class RiskModelRuntime:
    def __init__(self):
        self.artifact_dir = Path(__file__).resolve().parent / "artifacts"
        with open(self.artifact_dir / "metadata.json", "r", encoding="utf-8") as handle:
            self.metadata = json.load(handle)
        self.snapshot = pd.read_csv(self.artifact_dir / "latest_feature_snapshot.csv.gz")
        for column in CATEGORICAL_COLUMNS:
            self.snapshot[column] = self.snapshot[column].fillna("").astype(str)
        self.model_type = self.metadata["model_type"]
        self.model = None
        self.preprocessor = None
        self._load_model()

    def _load_model(self):
        if self.model_type == "CatBoost":
            from catboost import CatBoostRegressor
            self.model = CatBoostRegressor()
            self.model.load_model(str(self.artifact_dir / "model.cbm"))
        elif self.model_type == "XGBoost":
            from xgboost import XGBRegressor
            self.model = XGBRegressor()
            self.model.load_model(str(self.artifact_dir / "model.json"))
            self.preprocessor = joblib.load(self.artifact_dir / "preprocessor.joblib")
        elif self.model_type == "NegativeBinomial":
            self.model = joblib.load(self.artifact_dir / "model.joblib")
            self.preprocessor = joblib.load(self.artifact_dir / "nb_encoder.joblib")
        elif self.model_type == "MLP":
            import tensorflow as tf
            self.model = tf.keras.models.load_model(self.artifact_dir / "model.keras")
            self.preprocessor = joblib.load(self.artifact_dir / "preprocessor.joblib")
        else:
            raise ValueError(f"지원하지 않는 모델 형식: {self.model_type}")

    def _find_region_rows(self, sido, sigungu):
        sido = _normalize_sido(sido)
        sigungu = _clean(sigungu)
        candidates = self.snapshot[self.snapshot["시도"] == sido]
        exact = candidates[candidates["시군구"] == sigungu]
        if not exact.empty:
            return exact
        if sigungu:
            fuzzy_names = [
                name for name in candidates["시군구"].dropna().unique()
                if name.startswith(sigungu) or sigungu.startswith(name)
            ]
            if len(fuzzy_names) == 1:
                return candidates[candidates["시군구"] == fuzzy_names[0]]
        return pd.DataFrame(columns=self.snapshot.columns)

    def _predict_frame(self, frame):
        frame = frame[FEATURE_COLUMNS].copy()
        if self.model_type == "CatBoost":
            return np.asarray(self.model.predict(frame), dtype=float)
        if self.model_type == "NegativeBinomial":
            transformed = pd.DataFrame(index=frame.index)
            transformed["const"] = 1.0
            global_mean = float(self.preprocessor["global_mean"])
            for column in CATEGORICAL_COLUMNS:
                mapping = self.preprocessor["maps"].get(column, {})
                transformed[f"te__{column}"] = (
                    frame[column].fillna("").astype(str).map(mapping).fillna(global_mean).astype(float)
                )
            numeric_columns = [
                "feature_year", "lag1_count", "lag2_count", "lag3_count",
                "rolling3_mean", "rolling3_std", "trend3", "lag1_total",
                "lag1_share", "lag2_share", "rolling3_share",
            ]
            for column in numeric_columns:
                series = pd.to_numeric(frame[column], errors="coerce").fillna(0.0).astype(float)
                mean = float(self.preprocessor["numeric_means"].get(column, 0.0))
                scale = float(self.preprocessor["numeric_scales"].get(column, 1.0))
                if abs(scale) < 1e-8:
                    scale = 1.0
                transformed[f"num__{column}"] = (series - mean) / scale
            transformed = transformed.reindex(
                columns=self.preprocessor["columns"], fill_value=0.0
            ).astype(float)
            return np.asarray(self.model.predict(transformed), dtype=float)
        transformed = self.preprocessor.transform(frame)
        if self.model_type == "MLP":
            if hasattr(transformed, "toarray"):
                transformed = transformed.toarray()
            return np.asarray(self.model.predict(np.asarray(transformed, dtype=np.float32), verbose=0)).reshape(-1)
        return np.asarray(self.model.predict(transformed), dtype=float)

    def _condition_prediction(self, region_rows, group, condition):
        row = region_rows[
            (region_rows["feature_group"] == group)
            & (region_rows["condition"] == condition)
        ]
        if row.empty:
            return None
        return max(float(self._predict_frame(row.iloc[[0]])[0]), 1e-8)

    def _factor(self, region_rows, base_count, group, condition):
        condition_count = self._condition_prediction(region_rows, group, condition)
        national_share = float(self.metadata["national_shares"].get(f"{group}::{condition}", 0.0))
        if condition_count is None or national_share <= 0:
            return 1.0, False
        alpha = float(self.metadata.get("smoothing_alpha", 30.0))
        regional_share = (condition_count + alpha * national_share) / (base_count + alpha)
        return float(np.clip(regional_share / national_share, 0.5, 2.0)), True

    def _risk_score(self, relative_risk):
        quantiles = np.asarray(self.metadata["risk_quantiles"], dtype=float)
        indexes = np.arange(len(quantiles), dtype=float)
        score = float(np.interp(relative_risk, quantiles, indexes))
        return float(np.clip(score, 0.0, 100.0))

    def predict(self, features):
        region_rows = self._find_region_rows(features.get("시도"), features.get("시군구"))
        if region_rows.empty:
            return None

        base_count = self._condition_prediction(region_rows, "base", "전체")
        if base_count is None:
            return None

        weather = WEATHER_ALIASES.get(_clean(features.get("날씨")), _clean(features.get("날씨")))
        time_band = _clean(features.get("시간대"))
        road = ROAD_ALIASES.get(_clean(features.get("도로종류")), _clean(features.get("도로종류")))

        median_base = max(float(self.metadata["median_base_prediction"]), 1e-8)
        region_factor = float(np.clip(base_count / median_base, 0.5, 2.0))
        weather_factor, weather_used = self._factor(region_rows, base_count, "weather", weather)
        time_factor, time_used = self._factor(region_rows, base_count, "time", time_band)
        road_factor, road_used = self._factor(region_rows, base_count, "road", road)

        weights = self.metadata["weights"]
        factors = {
            "region": region_factor,
            "weather": weather_factor,
            "time": time_factor,
            "road": road_factor,
        }
        log_risk = sum(float(weights[key]) * math.log(max(factors[key], 1e-8)) for key in factors)
        relative_risk = math.exp(log_risk / sum(float(value) for value in weights.values()))
        score = self._risk_score(relative_risk)
        if score >= 90:
            level = "매우 높음"
        elif score >= 70:
            level = "높음"
        elif score >= 40:
            level = "보통"
        else:
            level = "낮음"

        return {
            "risk_level": level,
            "risk_score": round(score, 2),
            "relative_risk": round(relative_risk, 4),
            "model_version": self.metadata["model_version"],
            "condition_usage": {
                "weather": weather_used,
                "time": time_used,
                "road": road_used,
            },
        }


@lru_cache(maxsize=1)
def get_runtime():
    return RiskModelRuntime()
