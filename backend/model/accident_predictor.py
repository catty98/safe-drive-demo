from .risk_model_runtime import get_runtime


def predict_region_risk(features):
    """
    학습된 TAAS 모델로 현재 주행조건의 상대위험도를 계산합니다.

    오류를 숨기지 않고 상위 코드로 전달합니다.
    risk_model_adapter.py가 오류를 받아 risk_error에 저장합니다.
    """

    runtime = get_runtime()
    result = runtime.predict(features)

    if result is None:
        sido = features.get("시도", "")
        sigungu = features.get("시군구", "")

        raise LookupError(
            "학습 데이터에서 현재 지역을 찾지 못했습니다: "
            f"{sido} {sigungu}"
        )

    return result