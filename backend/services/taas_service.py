import pandas as pd
import numpy as np
from datetime import datetime
from config import ACCIDENT_FILES


# =========================================================
# 1. TAAS 엑셀 파일 읽기
# =========================================================

def read_accident_excel(file_name):

    raw = pd.read_excel(file_name, header=None)

    data_types = [
        "사고[건]",
        "사망[명]",
        "부상[명]",
    ]

    data_start_rows = raw[
        raw.iloc[:, 1].isin(data_types)
    ].index

    if len(data_start_rows) == 0:
        raise ValueError(
            f"데이터 시작 행을 찾을 수 없습니다: {file_name}"
        )

    data_start = data_start_rows[0]

    header = raw.iloc[:data_start].copy()

    # 병합 셀의 오른쪽 빈칸 채우기
    header = header.ffill(axis=1)

    column_names = ["시도", "구분"]

    for column_number in range(2, raw.shape[1]):

        parts = []

        for value in header.iloc[:, column_number]:

            if pd.isna(value):
                continue

            value = str(value).strip()

            if value in ["2025", "시도", "연도"]:
                continue

            if len(parts) == 0 or parts[-1] != value:
                parts.append(value)

        column_name = "_".join(parts)

        column_names.append(column_name)

    df = raw.iloc[data_start:].copy()

    df.columns = column_names

    # 사고, 사망, 부상 행만 남김
    # 마지막 행을 무조건 삭제하는 것보다 안전함
    df = df[
        df["구분"].isin(data_types)
    ].copy()

    df = df.reset_index(drop=True)

    return df


# =========================================================
# 2. 날씨 데이터 전처리
# =========================================================

def preprocess_accident_weather(df):

    weather_df = df.copy()

    # 합계와 지역별 데이터 분리
    weather_total = (
        weather_df[
            weather_df["시도"] == "합계"
        ]
        .copy()
        .reset_index(drop=True)
    )

    weather_region = (
        weather_df[
            weather_df["시도"] != "합계"
        ]
        .copy()
        .reset_index(drop=True)
    )

    # 시도, 구분, 합계를 제외하면 날씨 열
    weather_columns = [
        column
        for column in weather_region.columns
        if column not in ["시도", "구분", "합계"]
    ]

    number_columns = ["합계"] + weather_columns

    for column in number_columns:

        weather_total[column] = pd.to_numeric(
            weather_total[column]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce",
        ).fillna(0)

        weather_region[column] = pd.to_numeric(
            weather_region[column]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce",
        ).fillna(0)

    accident_type_map = {
        "사고[건]": "사고",
        "사망[명]": "사망",
        "부상[명]": "부상",
    }

    weather_region["사고유형"] = (
        weather_region["구분"]
        .map(accident_type_map)
    )

    weather_region = (
        weather_region
        .dropna(subset=["사고유형"])
        .reset_index(drop=True)
    )

    # 넓은 형태를 긴 형태로 변경
    weather_long = weather_region.melt(
        id_vars=["시도", "사고유형"],
        value_vars=weather_columns,
        var_name="날씨",
        value_name="값",
    )

    # 같은 지역, 같은 사고유형의 전체 날씨 합계
    weather_long["시도_사고유형_합계"] = (
        weather_long
        .groupby(
            ["시도", "사고유형"]
        )["값"]
        .transform("sum")
    )

    weather_long["비중"] = np.where(
        weather_long["시도_사고유형_합계"] != 0,
        (
            weather_long["값"]
            / weather_long["시도_사고유형_합계"]
        ),
        np.nan,
    )

    weather_long["비중(%)"] = (
        weather_long["비중"]
        .mul(100)
        .round(2)
    )

    weather_ratio_matrix = (
        weather_long
        .pivot_table(
            index=["시도", "날씨"],
            columns="사고유형",
            values="비중(%)",
            aggfunc="first",
        )
        .reindex(
            columns=["사고", "사망", "부상"]
        )
        .reset_index()
    )

    weather_ratio_matrix.columns.name = None

    weather_ratio_matrix = (
        weather_ratio_matrix.rename(
            columns={
                "사고": "사고비중(%)",
                "사망": "사망비중(%)",
                "부상": "부상비중(%)",
            }
        )
    )

    return (
        weather_total,
        weather_region,
        weather_long,
        weather_ratio_matrix,
    )


# =========================================================
# 3. 선택한 날씨 분석
# =========================================================

def select_weather_analysis(
    weather_long_df,
    weather,
):

    selected = (
        weather_long_df[
            weather_long_df["날씨"] == weather
        ]
        .copy()
    )

    if selected.empty:
        return pd.DataFrame()

    value_matrix = (
        selected
        .pivot_table(
            index="시도",
            columns="사고유형",
            values="값",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(
            columns=["사고", "사망", "부상"],
            fill_value=0,
        )
        .reset_index()
    )

    value_matrix.columns.name = None

    value_matrix = value_matrix.rename(
        columns={
            "사고": "사고건수",
            "사망": "사망자수",
            "부상": "부상자수",
        }
    )

    ratio_matrix = (
        selected
        .pivot_table(
            index="시도",
            columns="사고유형",
            values="비중(%)",
            aggfunc="first",
        )
        .reindex(
            columns=["사고", "사망", "부상"]
        )
        .reset_index()
    )

    ratio_matrix.columns.name = None

    ratio_matrix = ratio_matrix.rename(
        columns={
            "사고": "지역내_사고비중(%)",
            "사망": "지역내_사망비중(%)",
            "부상": "지역내_부상비중(%)",
        }
    )

    result = value_matrix.merge(
        ratio_matrix,
        on="시도",
        how="left",
    )

    result.insert(1, "날씨", weather)

    accident_total = result["사고건수"].sum()
    death_total = result["사망자수"].sum()
    injury_total = result["부상자수"].sum()

    result["전국대비_사고비중(%)"] = np.where(
        accident_total != 0,
        result["사고건수"] / accident_total * 100,
        np.nan,
    ).round(2)

    result["전국대비_사망비중(%)"] = np.where(
        death_total != 0,
        result["사망자수"] / death_total * 100,
        np.nan,
    ).round(2)

    result["전국대비_부상비중(%)"] = np.where(
        injury_total != 0,
        result["부상자수"] / injury_total * 100,
        np.nan,
    ).round(2)

    result["사고순위"] = (
        result["사고건수"]
        .rank(
            method="min",
            ascending=False,
        )
        .astype("Int64")
    )

    result["사망순위"] = (
        result["사망자수"]
        .rank(
            method="min",
            ascending=False,
        )
        .astype("Int64")
    )

    result["부상순위"] = (
        result["부상자수"]
        .rank(
            method="min",
            ascending=False,
        )
        .astype("Int64")
    )

    accident_mean = result["사고건수"].mean()
    death_mean = result["사망자수"].mean()
    injury_mean = result["부상자수"].mean()

    result["사고_지역평균대비(배)"] = np.where(
        accident_mean != 0,
        result["사고건수"] / accident_mean,
        np.nan,
    ).round(2)

    result["사망_지역평균대비(배)"] = np.where(
        death_mean != 0,
        result["사망자수"] / death_mean,
        np.nan,
    ).round(2)

    result["부상_지역평균대비(배)"] = np.where(
        injury_mean != 0,
        result["부상자수"] / injury_mean,
        np.nan,
    ).round(2)

    result = (
        result
        .sort_values(
            by=["사고건수", "사망자수"],
            ascending=[False, False],
        )
        .reset_index(drop=True)
    )

    return result


# =========================================================
# 4. raw 폴더의 엑셀 데이터 불러오기
# =========================================================

def load_accident_excel_files():

    accident_data = {
        "type": read_accident_excel(
            ACCIDENT_FILES["type"]
        ),
        "road": read_accident_excel(
            ACCIDENT_FILES["road"]
        ),
        "time": read_accident_excel(
            ACCIDENT_FILES["time"]
        ),
        "weather": read_accident_excel(
            ACCIDENT_FILES["weather"]
        ),
    }

    return accident_data


# =========================================================
# 5. 날씨 데이터까지 전처리해서 반환
# =========================================================

def load_preprocessed_weather_data():

    # 날씨 엑셀 파일 읽기
    weather_df = read_accident_excel(
        ACCIDENT_FILES["weather"]
    )

    (
        weather_total,
        weather_region,
        weather_long,
        weather_ratio,
    ) = preprocess_accident_weather(weather_df)

    return {
        "original": weather_df,
        "total": weather_total,
        "region": weather_region,
        "long": weather_long,
        "ratio": weather_ratio,
    }


# =========================================================
# 6. 시간대 데이터 전처리
# =========================================================

TIME_BANDS = [
    "0시~2시",
    "2시~4시",
    "4시~6시",
    "6시~8시",
    "8시~10시",
    "10시~12시",
    "12시~14시",
    "14시~16시",
    "16시~18시",
    "18시~20시",
    "20시~22시",
    "22시~24시",
]


def preprocess_accident_time(df):
    """
    TAAS 시간대별 사고 데이터를 분석하기 쉬운 긴 형태로 변환합니다.

    반환값:
    - time_total: 전국 합계 행
    - time_region: 지역별 원본 형태
    - time_long: 시도·사고유형·시간대별 긴 형태
    - time_ratio: 지역 내 시간대 비중 행렬
    """

    time_df = df.copy()

    time_total = (
        time_df[time_df["시도"] == "합계"]
        .copy()
        .reset_index(drop=True)
    )

    time_region = (
        time_df[time_df["시도"] != "합계"]
        .copy()
        .reset_index(drop=True)
    )

    missing_columns = [
        column
        for column in TIME_BANDS
        if column not in time_region.columns
    ]

    if missing_columns:
        raise ValueError(
            "시간대 열을 찾을 수 없습니다: "
            + ", ".join(missing_columns)
        )

    number_columns = ["합계"] + TIME_BANDS

    for column in number_columns:
        if column not in time_region.columns:
            continue

        time_total[column] = pd.to_numeric(
            time_total[column]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce",
        ).fillna(0)

        time_region[column] = pd.to_numeric(
            time_region[column]
            .astype(str)
            .str.replace(",", "", regex=False),
            errors="coerce",
        ).fillna(0)

    accident_type_map = {
        "사고[건]": "사고",
        "사망[명]": "사망",
        "부상[명]": "부상",
    }

    time_region["사고유형"] = (
        time_region["구분"].map(accident_type_map)
    )

    time_region = (
        time_region
        .dropna(subset=["사고유형"])
        .reset_index(drop=True)
    )

    time_long = time_region.melt(
        id_vars=["시도", "사고유형"],
        value_vars=TIME_BANDS,
        var_name="시간대",
        value_name="값",
    )

    time_long["시도_사고유형_합계"] = (
        time_long
        .groupby(["시도", "사고유형"])["값"]
        .transform("sum")
    )

    time_long["비중"] = np.where(
        time_long["시도_사고유형_합계"] != 0,
        (
            time_long["값"]
            / time_long["시도_사고유형_합계"]
        ),
        np.nan,
    )

    time_long["비중(%)"] = (
        time_long["비중"]
        .mul(100)
        .round(2)
    )

    time_ratio_matrix = (
        time_long
        .pivot_table(
            index=["시도", "시간대"],
            columns="사고유형",
            values="비중(%)",
            aggfunc="first",
        )
        .reindex(columns=["사고", "사망", "부상"])
        .reset_index()
    )

    time_ratio_matrix.columns.name = None

    time_ratio_matrix = time_ratio_matrix.rename(
        columns={
            "사고": "사고비중(%)",
            "사망": "사망비중(%)",
            "부상": "부상비중(%)",
        }
    )

    return (
        time_total,
        time_region,
        time_long,
        time_ratio_matrix,
    )


# =========================================================
# 7. 현재 시각을 TAAS 시간 구간으로 변환
# =========================================================


def get_current_time_band(current_time=None):
    """
    현재 시각을 TAAS의 2시간 단위 구간명으로 변환합니다.

    예: 09:30 -> '8시~10시'
    """

    if current_time is None:
        current_time = datetime.now()

    start_hour = (current_time.hour // 2) * 2
    end_hour = start_hour + 2

    return f"{start_hour}시~{end_hour}시"


# =========================================================
# 8. 선택한 시간대 분석
# =========================================================


def select_time_analysis(
    time_long_df,
    time_band=None,
    current_time=None,
):
    """
    특정 시간대의 지역별 사고·사망·부상 현황을 반환합니다.

    time_band를 생략하면 current_time 또는 현재 시스템 시각을 사용합니다.
    """

    if time_band is None:
        time_band = get_current_time_band(current_time)

    if time_band not in TIME_BANDS:
        raise ValueError(
            f"지원하지 않는 시간대입니다: {time_band}"
        )

    selected = (
        time_long_df[
            time_long_df["시간대"] == time_band
        ]
        .copy()
    )

    if selected.empty:
        return pd.DataFrame()

    value_matrix = (
        selected
        .pivot_table(
            index="시도",
            columns="사고유형",
            values="값",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(
            columns=["사고", "사망", "부상"],
            fill_value=0,
        )
        .reset_index()
    )

    value_matrix.columns.name = None

    value_matrix = value_matrix.rename(
        columns={
            "사고": "사고건수",
            "사망": "사망자수",
            "부상": "부상자수",
        }
    )

    ratio_matrix = (
        selected
        .pivot_table(
            index="시도",
            columns="사고유형",
            values="비중(%)",
            aggfunc="first",
        )
        .reindex(columns=["사고", "사망", "부상"])
        .reset_index()
    )

    ratio_matrix.columns.name = None

    ratio_matrix = ratio_matrix.rename(
        columns={
            "사고": "지역내_사고비중(%)",
            "사망": "지역내_사망비중(%)",
            "부상": "지역내_부상비중(%)",
        }
    )

    result = value_matrix.merge(
        ratio_matrix,
        on="시도",
        how="left",
    )

    result.insert(1, "시간대", time_band)

    metric_columns = {
        "사고": "사고건수",
        "사망": "사망자수",
        "부상": "부상자수",
    }

    for label, value_column in metric_columns.items():
        total = result[value_column].sum()
        mean = result[value_column].mean()

        result[f"전국대비_{label}비중(%)"] = np.where(
            total != 0,
            result[value_column] / total * 100,
            np.nan,
        ).round(2)

        result[f"{label}순위"] = (
            result[value_column]
            .rank(method="min", ascending=False)
            .astype("Int64")
        )

        result[f"{label}_지역평균대비(배)"] = np.where(
            mean != 0,
            result[value_column] / mean,
            np.nan,
        ).round(2)

    result = (
        result
        .sort_values(
            by=["사고건수", "사망자수"],
            ascending=[False, False],
        )
        .reset_index(drop=True)
    )

    return result


# =========================================================
# 9. 시간대 데이터까지 전처리해서 반환
# =========================================================


def load_preprocessed_time_data():
    time_df = read_accident_excel(
        ACCIDENT_FILES["time"]
    )

    (
        time_total,
        time_region,
        time_long,
        time_ratio,
    ) = preprocess_accident_time(time_df)

    return {
        "original": time_df,
        "total": time_total,
        "region": time_region,
        "long": time_long,
        "ratio": time_ratio,
    }


# =========================================================
# 10. 도로 종류 데이터 전처리
# =========================================================


def preprocess_accident_road(df):
    """
    TAAS 도로 종류별 사고 데이터를 긴 형태로 변환합니다.

    주의:
    - 사고건수는 건수, 사망자수·부상자수는 사람 수입니다.
    - 부상자수 / 사고건수는 확률이 아니라 사고당 인원 지표입니다.
    """

    road_df = df.copy()

    road_total = (
        road_df[road_df["시도"] == "합계"]
        .copy()
        .reset_index(drop=True)
    )

    road_region = (
        road_df[road_df["시도"] != "합계"]
        .copy()
        .reset_index(drop=True)
    )

    road_columns = [
        column
        for column in road_region.columns
        if column not in ["시도", "구분", "합계"]
        and str(column).strip()
    ]

    if not road_columns:
        raise ValueError("도로 종류 열을 찾을 수 없습니다.")

    number_columns = ["합계"] + road_columns

    for column in number_columns:
        for frame in (road_total, road_region):
            frame[column] = pd.to_numeric(
                frame[column]
                .astype(str)
                .str.replace(",", "", regex=False),
                errors="coerce",
            ).fillna(0)

    accident_type_map = {
        "사고[건]": "사고",
        "사망[명]": "사망",
        "부상[명]": "부상",
    }

    road_region["사고유형"] = (
        road_region["구분"].map(accident_type_map)
    )

    road_region = (
        road_region
        .dropna(subset=["사고유형"])
        .reset_index(drop=True)
    )

    road_long = road_region.melt(
        id_vars=["시도", "사고유형"],
        value_vars=road_columns,
        var_name="도로종류",
        value_name="값",
    )

    road_long["도로종류"] = road_long["도로종류"].replace(
        {"시도(도로)": "시도"}
    )

    return road_total, road_region, road_long


# =========================================================
# 11. 도로 종류별 분석
# =========================================================


def select_road_analysis(
    road_long_df,
    sidos=None,
):
    """
    시도·도로 종류별 사고 빈도와 심각도 지표를 반환합니다.

    이 데이터만으로는 교통량·도로 길이를 고려한 진짜 '사고율'을
    계산할 수 없습니다. 따라서 다음처럼 구분하여 제공합니다.

    - 지역내_도로사고비중(%): 해당 지역 사고 중 도로 종류의 구성비
    - 사고100건당_사망자수: 사고 100건당 사망 인원
    - 사고100건당_부상자수: 사고 100건당 부상 인원(100 초과 가능)
    - 사고1건당_부상자수: 사고 한 건당 평균 부상 인원
    - 사상자중_사망비율(%): 사망자 / (사망자 + 부상자)
    """

    if road_long_df.empty:
        return pd.DataFrame()

    result = (
        road_long_df
        .pivot_table(
            index=["시도", "도로종류"],
            columns="사고유형",
            values="값",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(
            columns=["사고", "사망", "부상"],
            fill_value=0,
        )
        .reset_index()
    )

    result.columns.name = None

    result = result.rename(
        columns={
            "사고": "사고건수",
            "사망": "사망자수",
            "부상": "부상자수",
        }
    )

    # 필터링 전에 전국 및 지역별 분모를 계산해야 합니다.
    region_accident_total = (
        result.groupby("시도")["사고건수"]
        .transform("sum")
    )

    nationwide_same_road_total = (
        result.groupby("도로종류")["사고건수"]
        .transform("sum")
    )

    casualties = (
        result["사망자수"] + result["부상자수"]
    )

    result["지역내_도로사고비중(%)"] = np.where(
        region_accident_total > 0,
        result["사고건수"] / region_accident_total * 100,
        np.nan,
    ).round(2)

    result["전국동일도로_사고비중(%)"] = np.where(
        nationwide_same_road_total > 0,
        result["사고건수"] / nationwide_same_road_total * 100,
        np.nan,
    ).round(2)

    result["사고100건당_사망자수"] = np.where(
        result["사고건수"] > 0,
        result["사망자수"] / result["사고건수"] * 100,
        np.nan,
    ).round(2)

    result["사고100건당_부상자수"] = np.where(
        result["사고건수"] > 0,
        result["부상자수"] / result["사고건수"] * 100,
        np.nan,
    ).round(2)

    result["사고1건당_부상자수"] = np.where(
        result["사고건수"] > 0,
        result["부상자수"] / result["사고건수"],
        np.nan,
    ).round(3)

    result["사상자중_사망비율(%)"] = np.where(
        casualties > 0,
        result["사망자수"] / casualties * 100,
        np.nan,
    ).round(2)

    result["지역내_사고건수순위"] = (
        result.groupby("시도")["사고건수"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )

    # 사고가 없는 도로는 치명도 순위에서 제외합니다.
    positive_accident = result["사고건수"] > 0
    result["지역내_치명도순위"] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="Int64",
    )
    result.loc[positive_accident, "지역내_치명도순위"] = (
        result.loc[positive_accident]
        .groupby("시도")["사고100건당_사망자수"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )

    if sidos:
        result = result[
            result["시도"].isin(sidos)
        ].copy()

    return (
        result
        .sort_values(
            by=["시도", "지역내_사고건수순위", "도로종류"],
            ascending=[True, True, True],
        )
        .reset_index(drop=True)
    )


# =========================================================
# 12. 도로 데이터까지 전처리해서 반환
# =========================================================


def load_preprocessed_road_data():
    road_df = read_accident_excel(
        ACCIDENT_FILES["road"]
    )

    (
        road_total,
        road_region,
        road_long,
    ) = preprocess_accident_road(road_df)

    return {
        "original": road_df,
        "total": road_total,
        "region": road_region,
        "long": road_long,
    }

# =========================================================
# 13. 사고 유형 데이터 전처리
# =========================================================


def preprocess_accident_type(df):
    """
    TAAS 사고 유형 데이터를 대분류와 세분류로 나누어 긴 형태로 변환합니다.

    엑셀에는 다음 값이 함께 들어 있습니다.
    - 대분류 합계: 차대사람_합계, 차대차_합계, 차량단독_합계
    - 중간 합계: 차량단독_도로이탈_합계
    - 세부 유형: 차대사람_횡단중, 차대차_추돌 등

    합계 열과 세부 열을 한 번에 합산하면 중복 집계되므로,
    major_long과 detail_long을 별도로 반환합니다.
    """

    type_df = df.copy()

    type_total = (
        type_df[type_df["시도"] == "합계"]
        .copy()
        .reset_index(drop=True)
    )

    type_region = (
        type_df[type_df["시도"] != "합계"]
        .copy()
        .reset_index(drop=True)
    )

    type_columns = [
        column
        for column in type_region.columns
        if column not in ["시도", "구분", "합계"]
        and str(column).strip()
    ]

    if not type_columns:
        raise ValueError("사고 유형 열을 찾을 수 없습니다.")

    number_columns = ["합계"] + type_columns

    for column in number_columns:
        for frame in (type_total, type_region):
            frame[column] = pd.to_numeric(
                frame[column]
                .astype(str)
                .str.replace(",", "", regex=False),
                errors="coerce",
            ).fillna(0)

    metric_map = {
        "사고[건]": "사고",
        "사망[명]": "사망",
        "부상[명]": "부상",
    }

    type_region["사고유형"] = (
        type_region["구분"].map(metric_map)
    )

    type_region = (
        type_region
        .dropna(subset=["사고유형"])
        .reset_index(drop=True)
    )

    # -------------------------
    # 대분류
    # -------------------------
    # '_합계'가 한 번만 붙은 열은 최상위 대분류 합계입니다.
    # 철길건널목처럼 하위 분류가 없는 열도 대분류로 취급합니다.
    major_column_map = {}

    for column in type_columns:
        if (
            column.endswith("_합계")
            and column.count("_") == 1
        ):
            major_column_map[column] = (
                column.removesuffix("_합계")
            )
        elif "_" not in column:
            major_column_map[column] = column

    if not major_column_map:
        raise ValueError(
            "사고 유형 대분류 합계 열을 찾을 수 없습니다."
        )

    major_long = type_region.melt(
        id_vars=["시도", "사고유형"],
        value_vars=list(major_column_map.keys()),
        var_name="원본열",
        value_name="값",
    )

    major_long["집계수준"] = "대분류"
    major_long["사고형태대분류"] = (
        major_long["원본열"].map(major_column_map)
    )
    major_long["사고형태세분류"] = ""
    major_long["사고형태"] = (
        major_long["사고형태대분류"]
    )

    major_long = major_long[
        [
            "시도",
            "사고유형",
            "집계수준",
            "사고형태대분류",
            "사고형태세분류",
            "사고형태",
            "값",
        ]
    ]

    # -------------------------
    # 세분류
    # -------------------------
    # 모든 '*_합계' 열은 제외하여 중복 집계를 방지합니다.
    # 철길건널목은 하위 분류가 없으므로 세분류 결과에도 그대로 포함합니다.
    detail_columns = [
        column
        for column in type_columns
        if not column.endswith("_합계")
    ]

    detail_long = type_region.melt(
        id_vars=["시도", "사고유형"],
        value_vars=detail_columns,
        var_name="원본열",
        value_name="값",
    )

    detail_long["집계수준"] = "세분류"

    detail_long["사고형태대분류"] = (
        detail_long["원본열"].apply(
            lambda column: (
                column.split("_", 1)[0]
                if "_" in column
                else column
            )
        )
    )

    detail_long["사고형태세분류"] = (
        detail_long["원본열"].apply(
            lambda column: (
                column.rsplit("_", 1)[-1]
                if "_" in column
                else ""
            )
        )
    )

    detail_long["사고형태"] = np.where(
        detail_long["사고형태세분류"].eq(""),
        detail_long["사고형태대분류"],
        (
            detail_long["사고형태대분류"]
            + "_"
            + detail_long["사고형태세분류"]
        ),
    )

    detail_long = detail_long[
        [
            "시도",
            "사고유형",
            "집계수준",
            "사고형태대분류",
            "사고형태세분류",
            "사고형태",
            "값",
        ]
    ]

    return (
        type_total,
        type_region,
        major_long,
        detail_long,
    )


# =========================================================
# 14. 사고 유형별 분석
# =========================================================


def select_type_analysis(
    type_long_df,
    sidos=None,
    min_accidents_for_severity=30,
):
    """
    시도·사고 유형별 빈도와 심각도 지표를 반환합니다.

    주요 지표:
    - 지역내_사고비중(%): 해당 지역 전체 사고 중 해당 유형의 비중
    - 전국동일유형_사고비중(%): 전국의 같은 유형 사고 중 해당 지역 비중
    - 사고100건당_사망자수: 사고 100건당 사망 인원
    - 사고1건당_부상자수: 사고 한 건당 평균 부상 인원
    - 사상자중_사망비율(%): 사망자 / (사망자 + 부상자)
    - 전국동일유형대비_치명도(배): 같은 유형의 전국 치명도 대비 배수

    사고가 너무 적은 유형은 치명도 순위가 과장될 수 있으므로,
    기본적으로 사고 30건 이상인 유형만 치명도 순위를 계산합니다.
    """

    if type_long_df.empty:
        return pd.DataFrame()

    result = (
        type_long_df
        .pivot_table(
            index=[
                "시도",
                "집계수준",
                "사고형태대분류",
                "사고형태세분류",
                "사고형태",
            ],
            columns="사고유형",
            values="값",
            aggfunc="sum",
            fill_value=0,
        )
        .reindex(
            columns=["사고", "사망", "부상"],
            fill_value=0,
        )
        .reset_index()
    )

    result.columns.name = None

    result = result.rename(
        columns={
            "사고": "사고건수",
            "사망": "사망자수",
            "부상": "부상자수",
        }
    )

    # 전국 기준 지표는 시도 필터링 전에 계산해야 합니다.
    region_accident_total = (
        result.groupby("시도")["사고건수"]
        .transform("sum")
    )

    nationwide_same_type_accidents = (
        result.groupby("사고형태")["사고건수"]
        .transform("sum")
    )

    nationwide_same_type_deaths = (
        result.groupby("사고형태")["사망자수"]
        .transform("sum")
    )

    casualties = (
        result["사망자수"] + result["부상자수"]
    )

    result["지역내_사고비중(%)"] = np.where(
        region_accident_total > 0,
        (
            result["사고건수"]
            / region_accident_total
            * 100
        ),
        np.nan,
    ).round(2)

    result["전국동일유형_사고비중(%)"] = np.where(
        nationwide_same_type_accidents > 0,
        (
            result["사고건수"]
            / nationwide_same_type_accidents
            * 100
        ),
        np.nan,
    ).round(2)

    result["사고100건당_사망자수"] = np.where(
        result["사고건수"] > 0,
        (
            result["사망자수"]
            / result["사고건수"]
            * 100
        ),
        np.nan,
    ).round(2)

    result["사고1건당_부상자수"] = np.where(
        result["사고건수"] > 0,
        result["부상자수"] / result["사고건수"],
        np.nan,
    ).round(3)

    result["사상자중_사망비율(%)"] = np.where(
        casualties > 0,
        result["사망자수"] / casualties * 100,
        np.nan,
    ).round(2)

    nationwide_fatality = np.where(
        nationwide_same_type_accidents > 0,
        (
            nationwide_same_type_deaths
            / nationwide_same_type_accidents
            * 100
        ),
        np.nan,
    )

    result["전국동일유형대비_치명도(배)"] = np.where(
        nationwide_fatality > 0,
        (
            result["사고100건당_사망자수"]
            / nationwide_fatality
        ),
        np.nan,
    ).round(2)

    result["지역내_사고건수순위"] = (
        result.groupby("시도")["사고건수"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )

    # 표본이 너무 작은 유형은 치명도 순위에서 제외합니다.
    severity_eligible = (
        result["사고건수"]
        >= min_accidents_for_severity
    )

    result["지역내_치명도순위"] = pd.Series(
        pd.NA,
        index=result.index,
        dtype="Int64",
    )

    result.loc[
        severity_eligible,
        "지역내_치명도순위",
    ] = (
        result.loc[severity_eligible]
        .groupby("시도")["사고100건당_사망자수"]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )

    if sidos:
        result = result[
            result["시도"].isin(sidos)
        ].copy()

    return (
        result
        .sort_values(
            by=[
                "시도",
                "지역내_사고건수순위",
                "사고형태",
            ],
            ascending=[True, True, True],
        )
        .reset_index(drop=True)
    )


# =========================================================
# 15. 사고 유형 데이터까지 전처리해서 반환
# =========================================================


def load_preprocessed_type_data():
    type_df = read_accident_excel(
        ACCIDENT_FILES["type"]
    )

    (
        type_total,
        type_region,
        type_major_long,
        type_detail_long,
    ) = preprocess_accident_type(type_df)

    return {
        "original": type_df,
        "total": type_total,
        "region": type_region,
        "major_long": type_major_long,
        "detail_long": type_detail_long,
    }








