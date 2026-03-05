"""자전거 수거/배치 대시보드 - Streamlit 메인 앱."""

import streamlit as st

st.set_page_config(
    page_title="자전거 수거/배치 대시보드",
    page_icon="🚲",
    layout="wide",
)

from src.bigquery_client import (
    fetch_area_group_list,
    fetch_district_polygons,
    fetch_district_stats,
)
from src.data_processing import allocate_bikes, calculate_supply_gap, get_summary_kpis
from src.map_utils import create_district_map

# ─── 상단 설정 ─────────────────────────────────────────────
st.title("자전거 수거/배치 대시보드")
st.caption("최근 7일 공급 성공률 기반 | 목표 공급성공률 80% | 적정 대수 = 평균 기기수 × (목표 성공률 / 현재 성공률)")

TARGET_RATE = 0.80

col_mode, col_area, col_bikes = st.columns(3)

with col_mode:
    alloc_mode = st.radio(
        "모드 선택",
        ["배치 (부족 지역에 공급)", "수거 (과잉 지역에서 회수)"],
        horizontal=True,
    )

with col_area:
    area_groups = fetch_area_group_list()
    selected_area_group = st.selectbox(
        "Area Group 선택",
        options=["전체"] + area_groups,
        index=0,
    )

with col_bikes:
    mode_label_input = "배치" if "배치" in alloc_mode else "수거"
    total_bikes_input = st.number_input(
        f"{mode_label_input} 대수 입력",
        min_value=0,
        max_value=10000,
        value=0,
        step=10,
    )

st.divider()

# ─── 입력 검증: 대수가 입력되어야 데이터 노출 ──────────────
if total_bikes_input <= 0:
    st.info("배치/수거 대수를 입력하면 결과가 표시됩니다.")
    st.stop()

# ─── 데이터 로드 ───────────────────────────────────────────────
with st.spinner("BigQuery에서 데이터를 불러오는 중..."):
    raw_df = fetch_district_stats()

# Area Group 필터 적용
if selected_area_group != "전체":
    raw_df = raw_df[raw_df["area_group"] == selected_area_group]

if raw_df.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# ─── 갭 계산 ──────────────────────────────────────────────────
df = calculate_supply_gap(raw_df, target_rate=TARGET_RATE)

mode = "deploy" if "배치" in alloc_mode else "collect"
mode_label = "배치" if mode == "deploy" else "수거"

# ─── 1. 배치/수거 할당 결과 (최우선 노출) ─────────────────────
st.subheader(f"{mode_label} 할당 결과")

result, adjusted_rate = allocate_bikes(
    df, total_bikes_input, mode=mode,
    raw_df=raw_df, initial_target_rate=TARGET_RATE,
)

if result.empty:
    st.info(f"{mode_label}이 필요한 지역이 없습니다.")
else:
    total_allocated = result["allocated"].sum()
    st.success(
        f"총 {total_bikes_input}대 중 **{total_allocated}대** "
        f"{mode_label} 할당 완료 (잔여: {total_bikes_input - total_allocated}대)"
    )
    if adjusted_rate != TARGET_RATE:
        st.info(
            f"잔여 0 달성을 위해 목표 공급성공률을 "
            f"{TARGET_RATE:.0%} → **{adjusted_rate:.0%}**로 자동 조정했습니다."
        )

    alloc_display_cols = [
        "alloc_priority", "area_group", "h3_area_name", "h3_district_name",
        "avg_bike_count", "current_bike_count", "avg_accessibility", "gap_int", "allocated",
    ]
    alloc_labels = {
        "alloc_priority": "할당 순위",
        "area_group": "Area Group",
        "h3_area_name": "Area",
        "h3_district_name": "District",
        "avg_bike_count": "평균 기기수(7일)",
        "current_bike_count": "현재 기기수",
        "avg_accessibility": "공급성공률",
        "gap_int": f"{'부족' if mode == 'deploy' else '과잉'} 대수",
        "allocated": f"{mode_label} 할당 대수",
    }

    existing_alloc_cols = [c for c in alloc_display_cols if c in result.columns]
    alloc_df = result[existing_alloc_cols].rename(columns=alloc_labels)

    st.dataframe(alloc_df, use_container_width=True, hide_index=True)

    alloc_csv = alloc_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"{mode_label} 할당 결과 CSV 다운로드",
        data=alloc_csv,
        file_name=f"allocation_{mode}_district.csv",
        mime="text/csv",
    )

# ─── 2. 지도 (배치/수거 대상 District만 빨간색) ──────────────
st.divider()
st.subheader(f"{mode_label} 대상 지역 지도")
st.caption(f"빨간색 = {mode_label} 대상 지역 | 회색 = 기타 지역")

# 할당된 district 목록 추출
highlight_districts = set()
if not result.empty and "h3_district_name" in result.columns:
    highlight_districts = set(result["h3_district_name"].tolist())

polygons_df = fetch_district_polygons()
deck = create_district_map(df, polygons_df, highlight_districts=highlight_districts)
st.pydeck_chart(deck, use_container_width=True)

# ─── 3. 전체 지역 상세 데이터 (마지막) ───────────────────────
st.divider()
st.subheader("전체 지역 상세 데이터")

kpis = get_summary_kpis(df)
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("평균 공급성공률", f"{kpis['avg_accessibility']:.1%}")
col2.metric("총 배치 기기 수", f"{kpis['total_bike_count']:,.0f}대")
col3.metric("분석 지역 수", f"{kpis['total_areas']}개")
col4.metric(
    "목표 미달 지역",
    f"{kpis['areas_below_target']}개",
    delta=f"-{kpis['total_deploy_needed']}대 부족",
    delta_color="inverse",
)
col5.metric(
    "목표 초과 지역",
    f"{kpis['areas_above_target']}개",
    delta=f"+{kpis['total_collect_possible']}대 과잉",
    delta_color="inverse",
)

display_cols = [
    "priority", "area_group", "h3_area_name", "h3_district_name",
    "avg_bike_count", "current_bike_count", "avg_accessibility", "optimal_bike_count",
    "gap_int", "status",
]
col_labels = {
    "priority": "우선순위",
    "area_group": "Area Group",
    "h3_area_name": "Area",
    "h3_district_name": "District",
    "avg_bike_count": "평균 기기수(7일)",
    "current_bike_count": "현재 기기수",
    "avg_accessibility": "공급성공률",
    "optimal_bike_count": "적정 기기수",
    "gap_int": "부족/과잉 대수",
    "status": "상태",
}

existing_cols = [c for c in display_cols if c in df.columns]
display_df = df[existing_cols].rename(columns=col_labels)

st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    column_config={
        "공급성공률": st.column_config.NumberColumn(format="%.1%%"),
    },
)

csv_data = display_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="전체 데이터 CSV 다운로드",
    data=csv_data,
    file_name="supply_gap_district.csv",
    mime="text/csv",
)
