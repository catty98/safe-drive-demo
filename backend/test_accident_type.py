from services.taas_service import (
    load_preprocessed_type_data,
    select_type_analysis,
)


def test_type_totals_match_original():
    data = load_preprocessed_type_data()

    major_result = select_type_analysis(
        data["major_long"]
    )

    detail_result = select_type_analysis(
        data["detail_long"]
    )

    original = data["region"]

    accident_rows = original[
        original["구분"] == "사고[건]"
    ]

    for _, row in accident_rows.iterrows():
        sido = row["시도"]
        expected_total = float(row["합계"])

        major_total = float(
            major_result[
                major_result["시도"] == sido
            ]["사고건수"].sum()
        )

        detail_total = float(
            detail_result[
                detail_result["시도"] == sido
            ]["사고건수"].sum()
        )

        assert major_total == expected_total
        assert detail_total == expected_total


def test_region_accident_shares_sum_to_100():
    data = load_preprocessed_type_data()

    for key in ["major_long", "detail_long"]:
        result = select_type_analysis(data[key])

        share_sum = (
            result.groupby("시도")[
                "지역내_사고비중(%)"
            ]
            .sum()
            .round(1)
        )

        assert share_sum.between(99.9, 100.1).all()