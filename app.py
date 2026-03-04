"""자전거 수거/배치 대시보드 - Streamlit 메인 앱."""

import streamlit as st

st.set_page_config(
    page_title="자전거 수거/배치 대시보드",
    page_icon="🚲",
    layout="wide",
)

from src.bigquery_client import (
    fetch_area_list,
    fetch_district_polygons,
    fetch_district_stats,
    fetch_hex_stats,
)
from src.data_processing import allocate_bikes, calculate_supply_gap, get_summary_kpis
from src.map_utils import create_district_map, create_hex_map

# ─── 사이드바 설정 ─────────────────────────────────────────────
st.sidebar.title("설정")

# Area 선택
areas = fetch_area_list()
selected_area = st.sidebar.selectbox(
    "Area (지역) 선택",
    options=["전체"] + areas,
    index=0,
)

# District / Hex 단위 선택
view_mode = st.sidebar.radio(
    "분석 단위", ["District", "Hex"], horizontal=True
)

# 목표 공급성공률
target_rate = st.sidebar.slider(
    "목표 공급성공률 (%)",
    min_value=50,
    max_value=100,
    value=80,
    step=5,
) / 100.0

st.sidebar.divider()

# 총 배치/수거 대수 입력
st.sidebar.subheader("배치/수거 할당 시뮬레이션")
alloc_mode = st.sidebar.radio(
    "모드 선택", ["배치 (부족 지역에 공급)", "수거 (과잉 지역에서 회수)"], horizontal=False
)
total_bikes_input = st.sidebar.number_input(
    "총 대수 입력",
    min_value=0,
    max_value=10000,
    value=0,
    step=10,
)
run_allocation = st.sidebar.button("할당 계산 실행", type="primary", use_container_width=True)

# ─── 데이터 로드 ───────────────────────────────────────────────
st.title("자전거 수거/배치 대시보드")
st.caption("최근 14일 공급 성공률 기반 | 적정 대수 = 현재 대수 × (목표 성공률 / 현재 성공률)")

with st.spinner("BigQuery에서 데이터를 불러오는 중..."):
    if view_mode == "District":
        raw_df = fetch_district_stats()
    else:
        raw_df = fetch_hex_stats()

# Area 필터 적용
if selected_area != "전체":
    raw_df = raw_df[raw_df["h3_area_name"] == selected_area]

if raw_df.empty:
    st.warning("선택한 조건에 해당하는 데이터가 없습니다.")
    st.stop()

# ─── 갭 계산 ──────────────────────────────────────────────────
df = calculate_supply_gap(raw_df, target_rate=target_rate)
kpis = get_summary_kpis(df)

# ─── KPI 카드 ─────────────────────────────────────────────────
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

# ─── 지도 ─────────────────────────────────────────────────────
st.subheader("지역별 공급 현황 지도")
st.caption("빨강 = 배치 필요 (부족) | 파랑 = 수거 가능 (과잉)")

if view_mode == "Hex":
    deck = create_hex_map(df)
else:
    polygons_df = fetch_district_polygons()
    deck = create_district_map(df, polygons_df)

st.pydeck_chart(deck, use_container_width=True)

# ─── 상세 테이블 ──────────────────────────────────────────────
st.subheader("지역별 상세 데이터")

# 표시용 컬럼 구성
if view_mode == "District":
    display_cols = [
        "priority", "h3_area_name", "h3_district_name",
        "avg_bike_count", "avg_accessibility", "optimal_bike_count",
        "gap_int", "status",
    ]
    col_labels = {
        "priority": "우선순위",
        "h3_area_name": "Area",
        "h3_district_name": "District",
        "avg_bike_count": "현재 평균 기기수",
        "avg_accessibility": "공급성공률",
        "optimal_bike_count": "적정 기기수",
        "gap_int": "부족/과잉 대수",
        "status": "상태",
    }
else:
    display_cols = [
        "priority", "h3_area_name", "h3_district_name", "h3_index",
        "avg_bike_count", "avg_accessibility", "optimal_bike_count",
        "gap_int", "status",
    ]
    col_labels = {
        "priority": "우선순위",
        "h3_area_name": "Area",
        "h3_district_name": "District",
        "h3_index": "H3 Index",
        "avg_bike_count": "현재 평균 기기수",
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

# ─── CSV 다운로드 ─────────────────────────────────────────────
csv_data = display_df.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    label="CSV 다운로드",
    data=csv_data,
    file_name=f"supply_gap_{view_mode.lower()}.csv",
    mime="text/csv",
)

# ─── 할당 시뮬레이션 ─────────────────────────────────────────
if run_allocation and total_bikes_input > 0:
    st.divider()
    st.subheader("배치/수거 할당 결과")

    mode = "deploy" if "배치" in alloc_mode else "collect"
    mode_label = "배치" if mode == "deploy" else "수거"

    result = allocate_bikes(df, total_bikes_input, mode=mode)

    if result.empty:
        st.info(f"{mode_label}이 필요한 지역이 없습니다.")
    else:
        total_allocated = result["allocated"].sum()
        st.success(
            f"총 {total_bikes_input}대 중 **{total_allocated}대** "
            f"{mode_label} 할당 완료 (잔여: {total_bikes_input - total_allocated}대)"
        )

        if view_mode == "District":
            alloc_display_cols = [
                "alloc_priority", "h3_area_name", "h3_district_name",
                "avg_bike_count", "avg_accessibility", "gap_int", "allocated",
            ]
            alloc_labels = {
                "alloc_priority": "할당 순위",
                "h3_area_name": "Area",
                "h3_district_name": "District",
                "avg_bike_count": "현재 기기수",
                "avg_accessibility": "공급성공률",
                "gap_int": f"{'부족' if mode == 'deploy' else '과잉'} 대수",
                "allocated": f"{mode_label} 할당 대수",
            }
        else:
            alloc_display_cols = [
                "alloc_priority", "h3_area_name", "h3_district_name", "h3_index",
                "avg_bike_count", "avg_accessibility", "gap_int", "allocated",
            ]
            alloc_labels = {
                "alloc_priority": "할당 순위",
                "h3_area_name": "Area",
                "h3_district_name": "District",
                "h3_index": "H3 Index",
                "avg_bike_count": "현재 기기수",
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
            file_name=f"allocation_{mode}_{view_mode.lower()}.csv",
            mime="text/csv",
        )
elif run_allocation and total_bikes_input == 0:
    st.warning("총 대수를 1 이상 입력해주세요.")
