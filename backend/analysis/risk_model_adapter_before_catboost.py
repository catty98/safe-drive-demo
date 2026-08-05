from model.accident_predictor import predict_region_risk


def _normalize_prediction(prediction):
    if prediction is None:
        return {
            "risk_available": False,
        }

    if isinstance(prediction, (int, float)):
        probability = float(prediction)

        if not 0 <= probability <= 1:
            return {
                "risk_available": False,
                "risk_error": (
                    "모델 확률은 0~1 사이여야 합니다."
                ),
            }

        return {
            "risk_available": True,
            "accident_probability": probability,
        }

    if not isinstance(prediction, dict):
        return {
            "risk_available": False,
            "risk_error": (
                "모델 반환값은 None, 숫자 또는 dict여야 합니다."
            ),
        }

    result = {
        "risk_available": True,
    }

    probability = prediction.get("probability")

    if probability is None:
        probability = prediction.get(
            "accident_probability"
        )

    if probability is not None:
        probability = float(probability)

        if not 0 <= probability <= 1:
            return {
                "risk_available": False,
                "risk_error": (
                    "모델 probability는 0~1 사이여야 합니다."
                ),
            }

        result["accident_probability"] = probability

    probability_percent = prediction.get(
        "probability_percent"
    )

    if (
        "accident_probability" not in result
        and probability_percent is not None
    ):
        probability_percent = float(probability_percent)

        if not 0 <= probability_percent <= 100:
            return {
                "risk_available": False,
                "risk_error": (
                    "probability_percent는 0~100 사이여야 합니다."
                ),
            }

        result["accident_probability"] = (
            probability_percent / 100
        )

    for source_key, target_key in [
        ("risk_level", "risk_level"),
        ("risk_score", "risk_score"),
        ("relative_risk", "relative_risk"),
        ("model_version", "model_version"),
    ]:
        if source_key in prediction:
            result[target_key] = prediction[source_key]

    if len(result) == 1:
        return {
            "risk_available": False,
            "risk_error": "모델 결과에 표시할 값이 없습니다.",
        }

    return result


def _build_features(
    region,
    weather,
    current_time_band,
    main_road_type,
):
    return {
        "시도": region.get("시도", ""),
        "시군구": region.get("시군구", ""),
        "시간대": current_time_band,
        "날씨": weather,
        "도로종류": main_road_type,
        "혼잡도코드": region.get(
            "congestion_level",
            0,
        ),
        "혼잡도": region.get(
            "congestion_name",
            "정보없음",
        ),
        "평균속도_kmh": region.get(
            "average_speed_kmh"
        ),
        "지역진입예정_분": region.get(
            "entry_minutes",
            region.get("eta_minutes", 0),
        ),
        "지역주행시간_분": region.get(
            "duration_minutes",
            0,
        ),
        "지역주행거리_km": region.get(
            "distance_km",
            0,
        ),
    }


def attach_risk_predictions(
    regions,
    weather,
    current_time_band,
    main_road_type="기타",
    predictor=None,
):
    """
    지역별 입력값을 모델에 전달하고 결과를 같은 지역 dict에 붙입니다.

    predictor를 주지 않으면 model/accident_predictor.py의
    predict_region_risk()를 사용합니다.
    """

    if predictor is None:
        predictor = predict_region_risk

    enriched = []

    for region in regions:
        item = dict(region)
        features = _build_features(
            region=item,
            weather=weather,
            current_time_band=current_time_band,
            main_road_type=main_road_type,
        )

        try:
            prediction = predictor(features)
            normalized = _normalize_prediction(prediction)
        except Exception as exc:
            normalized = {
                "risk_available": False,
                "risk_error": str(exc),
            }

        item["model_features"] = features
        item.update(normalized)
        enriched.append(item)

    return enriched
