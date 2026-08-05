from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import LeaveOneOut, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import services.taas_service as st


BASE_DIR = Path(__file__).resolve().parent
RAW_DIR = BASE_DIR / "raw"
ARTIFACT_DIR = BASE_DIR / "model_artifacts"

TRAFFIC_FILE = RAW_DIR / "2025_전국_지역별_대표교통량_개선본.xlsx"
TRAFFIC_SHEET = "시도별_개선대표값"

MODEL_FILE = ARTIFACT_DIR / "regional_risk_pipeline.joblib"
METADATA_FILE = ARTIFACT_DIR / "regional_risk_metadata.json"
SCORES_FILE = ARTIFACT_DIR / "regional_risk_scores.json"
EVALUATION_FILE = ARTIFACT_DIR / "regional_risk_evaluation.csv"

MODEL_VERSION = "regional-relative-risk-v1.0"


def _to_numeric(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        result[column] = pd.to_numeric(result[column], errors="coerce").fillna(0.0)
    return result


def extract_accident_features(
    dataframe: pd.DataFrame,
    prefix: str,
) -> pd.DataFrame:
    """
    시도별 사고 건수 행만 추출합니다.

    동일 시도가 여러 행으로 존재해도 시도별 합계로 묶습니다.
    """
    filtered = dataframe[dataframe["구분"] == "사고[건]"].copy()

    excluded = {"시도", "구분", "사고유형"}
    feature_columns = [
        column
        for column in filtered.columns
        if column not in excluded
    ]

    filtered = _to_numeric(filtered, feature_columns)
    grouped = filtered.groupby("시도", as_index=False)[feature_columns].sum()

    rename_map = {
        column: f"{prefix}_{column}"
        for column in feature_columns
    }
    return grouped.rename(columns=rename_map)


def _find_columns(
    dataframe: pd.DataFrame,
    prefix: str,
    keywords: list[str],
) -> list[str]:
    matched: list[str] = []

    for column in dataframe.columns:
        if not column.startswith(f"{prefix}_"):
            continue
        if "합계" in column:
            continue
        if any(keyword in column for keyword in keywords):
            matched.append(column)

    return matched


def _group_total_column(
    dataframe: pd.DataFrame,
    prefix: str,
) -> str:
    exact = f"{prefix}_합계"
    if exact in dataframe.columns:
        return exact

    candidates = [
        column
        for column in dataframe.columns
        if column.startswith(f"{prefix}_") and "합계" in column
    ]
    if not candidates:
        raise KeyError(f"{prefix} 데이터에서 합계 열을 찾지 못했습니다.")

    return candidates[0]


def _ratio_feature(
    dataframe: pd.DataFrame,
    *,
    prefix: str,
    keywords: list[str],
    output_name: str,
) -> pd.Series:
    """
    절대 사고 건수 대신 해당 그룹 내 사고 구성비를 만듭니다.
    """
    matched_columns = _find_columns(dataframe, prefix, keywords)
    total_column = _group_total_column(dataframe, prefix)

    if not matched_columns:
        print(
            f"[경고] {output_name}: 일치하는 열이 없어 0으로 처리합니다. "
            f"키워드={keywords}"
        )
        return pd.Series(0.0, index=dataframe.index, name=output_name)

    numerator = dataframe[matched_columns].sum(axis=1)
    denominator = pd.to_numeric(
        dataframe[total_column],
        errors="coerce",
    ).replace(0, np.nan)

    return (
        numerator.div(denominator)
        .fillna(0.0)
        .clip(lower=0.0, upper=1.0)
        .rename(output_name)
    )


def build_training_data() -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    입력 특성 6개와 지역 상대 위험도를 만듭니다.

    목표값:
        지역 사고율 / 전국 평균 사고율

    주의:
        이는 실시간 사고 확률이 아니라
        시도별 과거 집계 자료에 기반한 상대 위험 지표입니다.
    """
    traffic_data = pd.read_excel(
        TRAFFIC_FILE,
        sheet_name=TRAFFIC_SHEET,
    )

    required_traffic_columns = {"시도", "추천대표교통량"}
    missing = required_traffic_columns - set(traffic_data.columns)
    if missing:
        raise KeyError(
            f"교통량 파일에 필요한 열이 없습니다: {sorted(missing)}"
        )

    weather_data = st.load_preprocessed_weather_data()
    time_data = st.load_preprocessed_time_data()
    road_data = st.load_preprocessed_road_data()
    type_data = st.load_preprocessed_type_data()

    feature_frames = [
        extract_accident_features(weather_data["region"], "weather"),
        extract_accident_features(time_data["region"], "time"),
        extract_accident_features(road_data["region"], "road"),
        extract_accident_features(type_data["region"], "type"),
    ]

    merged = feature_frames[0]
    for frame in feature_frames[1:]:
        merged = pd.merge(merged, frame, on="시도", how="inner")

    merged = pd.merge(
        merged,
        traffic_data[["시도", "추천대표교통량"]],
        on="시도",
        how="inner",
    )

    merged["추천대표교통량"] = pd.to_numeric(
        merged["추천대표교통량"],
        errors="coerce",
    )

    weather_total_column = _group_total_column(merged, "weather")
    merged[weather_total_column] = pd.to_numeric(
        merged[weather_total_column],
        errors="coerce",
    )

    merged = merged.dropna(
        subset=[weather_total_column, "추천대표교통량"]
    ).copy()
    merged = merged[
        (merged[weather_total_column] > 0)
        & (merged["추천대표교통량"] > 0)
    ].copy()

    # 절대 건수 대신 설명 가능한 5개 구성비 특성을 사용합니다.
    features = pd.DataFrame(
        {
            "악천후_사고구성비": _ratio_feature(
                merged,
                prefix="weather",
                keywords=["비", "눈", "안개"],
                output_name="악천후_사고구성비",
            ),
            "야간_사고구성비": _ratio_feature(
                merged,
                prefix="time",
                keywords=["00시", "02시", "04시", "22시", "24시"],
                output_name="야간_사고구성비",
            ),
            "고속도로_사고구성비": _ratio_feature(
                merged,
                prefix="road",
                keywords=["고속국도", "고속도로"],
                output_name="고속도로_사고구성비",
            ),
            "보행자_사고구성비": _ratio_feature(
                merged,
                prefix="type",
                keywords=["차대사람", "보행자", "횡단"],
                output_name="보행자_사고구성비",
            ),
            "추돌_사고구성비": _ratio_feature(
                merged,
                prefix="type",
                keywords=["추돌"],
                output_name="추돌_사고구성비",
            ),
            "log_추천대표교통량": np.log1p(
                merged["추천대표교통량"].astype(float)
            ),
        }
    )

    # 주요도로 대표교통량으로 보정한 지역 사고율입니다.
    accident_rate = (
        merged[weather_total_column].astype(float)
        / merged["추천대표교통량"].astype(float)
    ) * 10000.0

    national_average_rate = float(accident_rate.mean())
    if national_average_rate <= 0:
        raise ValueError("전국 평균 사고율이 0 이하라 상대 위험도를 만들 수 없습니다.")

    relative_risk = accident_rate / national_average_rate

    region_info = pd.DataFrame(
        {
            "시도": merged["시도"].astype(str).str.strip(),
            "사고율": accident_rate,
            "실측_상대위험도": relative_risk,
            "추천대표교통량": merged["추천대표교통량"].astype(float),
        }
    ).reset_index(drop=True)

    features = features.reset_index(drop=True)
    relative_risk = relative_risk.reset_index(drop=True)

    if len(features) < 5:
        raise ValueError(
            f"학습 가능한 지역이 너무 적습니다: {len(features)}개"
        )

    return features, relative_risk, region_info


def build_models() -> dict[str, Pipeline]:
    return {
        "Dummy": Pipeline(
            steps=[
                ("model", DummyRegressor(strategy="mean")),
            ]
        ),
        "LinearRegression": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("model", LinearRegression()),
            ]
        ),
        "Ridge": Pipeline(
            steps=[
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=10.0)),
            ]
        ),
    }


def evaluate_models(
    features: pd.DataFrame,
    target: pd.Series,
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """
    Leave-One-Out으로 각 지역을 한 번씩 완전히 제외하고 예측합니다.
    """
    loo = LeaveOneOut()
    rows: list[dict] = []
    predictions: dict[str, np.ndarray] = {}

    for name, pipeline in build_models().items():
        predicted = cross_val_predict(
            pipeline,
            features,
            target,
            cv=loo,
            method="predict",
        )
        predicted = np.clip(predicted.astype(float), 0.0, None)
        predictions[name] = predicted

        mae = mean_absolute_error(target, predicted)
        rmse = mean_squared_error(
            target,
            predicted,
        ) ** 0.5
        r2 = r2_score(target, predicted)

        target_series = pd.Series(target).reset_index(drop=True)
        prediction_series = pd.Series(predicted)
        spearman = target_series.corr(
            prediction_series,
            method="spearman",
        )

        rows.append(
            {
                "모델": name,
                "MAE": float(mae),
                "RMSE": float(rmse),
                "R2": float(r2),
                "Spearman": (
                    None
                    if pd.isna(spearman)
                    else float(spearman)
                ),
            }
        )

    evaluation = pd.DataFrame(rows).sort_values(
        by=["MAE", "RMSE"],
        ascending=True,
    ).reset_index(drop=True)

    return evaluation, predictions


def _risk_level(
    value: float,
    low_cut: float,
    high_cut: float,
) -> str:
    if value < low_cut:
        return "낮음"
    if value < high_cut:
        return "보통"
    return "높음"


def _top_factors(
    features: pd.DataFrame,
) -> list[list[str]]:
    """
    지역 평균보다 상대적으로 큰 특성 가운데 상위 2개를 설명 요인으로 사용합니다.
    """
    labels = {
        "악천후_사고구성비": "악천후 사고 구성비",
        "야간_사고구성비": "야간 사고 구성비",
        "고속도로_사고구성비": "고속도로 사고 구성비",
        "보행자_사고구성비": "보행자 사고 구성비",
        "추돌_사고구성비": "추돌 사고 구성비",
        "log_추천대표교통량": "대표 교통량",
    }

    std = features.std(ddof=0).replace(0, np.nan)
    z_scores = (
        features.subtract(features.mean())
        .divide(std)
        .fillna(0.0)
    )

    result: list[list[str]] = []
    for _, row in z_scores.iterrows():
        selected = [
            labels[column]
            for column in row.sort_values(ascending=False).index[:2]
            if row[column] > 0
        ]
        result.append(selected)

    return result


def save_artifacts(
    features: pd.DataFrame,
    target: pd.Series,
    region_info: pd.DataFrame,
    evaluation: pd.DataFrame,
    predictions: dict[str, np.ndarray],
) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    # MAE가 가장 낮은 모델을 최종 모델로 선택합니다.
    best_model_name = str(evaluation.iloc[0]["모델"])
    best_pipeline = build_models()[best_model_name]
    best_pipeline.fit(features, target)

    joblib.dump(
        {
            "pipeline": best_pipeline,
            "feature_names": list(features.columns),
            "model_name": best_model_name,
            "model_version": MODEL_VERSION,
        },
        MODEL_FILE,
    )

    low_cut = float(target.quantile(0.33))
    high_cut = float(target.quantile(0.67))

    # 앱 표시용 지역 점수는 과대평가를 줄이기 위해 LOOCV 예측값을 사용합니다.
    best_predictions = predictions[best_model_name]
    score_percentile = (
        pd.Series(best_predictions)
        .rank(method="average", pct=True)
        .mul(100.0)
    )
    rank = (
        pd.Series(best_predictions)
        .rank(method="min", ascending=False)
        .astype(int)
    )
    main_factors = _top_factors(features)

    records: list[dict] = []
    for index, region_row in region_info.iterrows():
        predicted_relative_risk = float(best_predictions[index])

        records.append(
            {
                "시도": region_row["시도"],
                "relative_risk": round(predicted_relative_risk, 4),
                "risk_score": round(float(score_percentile.iloc[index]), 1),
                "risk_level": _risk_level(
                    predicted_relative_risk,
                    low_cut,
                    high_cut,
                ),
                "rank": int(rank.iloc[index]),
                "total_regions": int(len(region_info)),
                "main_factors": main_factors[index],
                "model_name": best_model_name,
                "model_version": MODEL_VERSION,
                "basis": (
                    "시도별 과거 사고 통계와 주요도로 대표교통량을 이용한 "
                    "지역 상대 위험 지표"
                ),
            }
        )

    records.sort(key=lambda item: item["rank"])

    SCORES_FILE.write_text(
        json.dumps(
            {
                "model_version": MODEL_VERSION,
                "model_name": best_model_name,
                "low_cut": low_cut,
                "high_cut": high_cut,
                "regions": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    metadata = {
        "model_version": MODEL_VERSION,
        "model_name": best_model_name,
        "target": "전국 평균 대비 시도별 상대 위험도",
        "target_interpretation": (
            "실시간 사고 확률이 아니라 과거 지역 집계 자료 기반 상대 지표"
        ),
        "features": list(features.columns),
        "validation": "Leave-One-Out Cross Validation",
        "selection_rule": "가장 낮은 LOOCV MAE",
        "risk_grade_rule": {
            "낮음": f"상대 위험도 < {low_cut:.4f}",
            "보통": f"{low_cut:.4f} 이상, {high_cut:.4f} 미만",
            "높음": f"상대 위험도 >= {high_cut:.4f}",
        },
    }
    METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    evaluation.to_csv(
        EVALUATION_FILE,
        index=False,
        encoding="utf-8-sig",
    )


def main() -> None:
    features, target, region_info = build_training_data()
    evaluation, predictions = evaluate_models(features, target)

    print("=== Leave-One-Out 모델 비교 ===")
    print(evaluation.to_string(index=False))
    print()
    print(f"사용 특성: {list(features.columns)}")
    print(f"학습 지역 수: {len(features)}")

    save_artifacts(
        features=features,
        target=target,
        region_info=region_info,
        evaluation=evaluation,
        predictions=predictions,
    )

    print()
    print(f"모델 저장: {MODEL_FILE}")
    print(f"지역 점수 저장: {SCORES_FILE}")
    print(f"평가 결과 저장: {EVALUATION_FILE}")


if __name__ == "__main__":
    main()
