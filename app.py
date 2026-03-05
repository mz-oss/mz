"""자전거 수거/배치 대시보드 - Streamlit 메인 앱."""

import streamlit as st

st.set_page_config(
    page_title="자전거 수거/배치 대시보드",
    page_icon="🚲",
    layout="wide",
)

# ─── 모바일 반응형 CSS ────────────────────────────────────────
st.markdown(
    """
    <style>
    @media (max-width: 768px) {
        [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
        [data-testid="stHorizontalBlock"] > div {
            flex: 1 1 100% !important;
            min-width: 100% !important;
        }
        [data-testid="stMetric"] { padding: 0.5rem 0; }
        [data-testid="stRadio"] > div { flex-direction: column !important; }
        [data-testid="stDataFrame"] { font-size: 0.8rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

from src.bigquery_client import (
    fetch_area_group_list,
    fetch_district_polygons,
    fetch_district_stats,
    fetch_hex_demand,
    fetch_rebalance_zones,
)
from src.data_processing import (
    allocate_bikes,
    calculate_supply_gap,
    get_summary_kpis,
    select_rebalance_zones,
)
from src.map_utils import create_allocation_map, create_district_map

# ─── 상단 설정 ─────────────────────────────────────────────
st.title("수거/배치 대시보드")
with st.expander("계산 방식 안내", expanded=False):
    st.caption(
        "최근 7일 공급 성공률 기반 | 목표 공급성공률 80% | "
        "적정 대수 = 평균 기기수 × (목표 성공률 / 현재 성공률)"
    )

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

# ─── 데이터 준비: 할당 + 재배치존 선정 ─────────────────────────
result, adjusted_rate = allocate_bikes(
    df, total_bikes_input, mode=mode,
    raw_df=raw_df, initial_target_rate=TARGET_RATE,
)

polygons_df = fetch_district_polygons()
rebalance_zones_df = fetch_rebalance_zones() if mode == "deploy" else None
selected_zones_df = None

if mode == "deploy" and not result.empty and rebalance_zones_df is not None:
    hex_demand_df = fetch_hex_demand()
    if not hex_demand_df.empty:
        selected_zones_df = select_rebalance_zones(
            result, rebalance_zones_df, hex_demand_df, polygons_df,
        )

# ─── 1. 배치/수거 할당 결과 (최우선 노출) ─────────────────────
st.subheader(f"{mode_label} 할당 결과")

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

    # District별 선정 재배치존 이름/대수 집계 (배치 모드에서만)
    alloc_with_zones = result.copy()
    if selected_zones_df is not None and not selected_zones_df.empty:
        selected_only = selected_zones_df[selected_zones_df["selected"]].copy()
        zone_summary = (
            selected_only
            .groupby("h3_district_name")
            .apply(
                lambda g: " / ".join(
                    f"{r['zone_title']}({int(r['allocated'])}대)"
                    for _, r in g.iterrows()
                ),
                include_groups=False,
            )
            .reset_index()
        )
        zone_summary.columns = ["h3_district_name", "재배치존"]
        alloc_with_zones = alloc_with_zones.merge(
            zone_summary, on="h3_district_name", how="left",
        )
        alloc_with_zones["재배치존"] = alloc_with_zones["재배치존"].fillna("")

    # 핵심 정보: District / 할당 대수 / 재배치존
    alloc_main_cols = ["alloc_priority", "h3_district_name", "allocated"]
    alloc_main_labels = {
        "alloc_priority": "할당 순위",
        "h3_district_name": "District",
        "allocated": f"{mode_label} 할당 대수",
    }
    if "재배치존" in alloc_with_zones.columns:
        alloc_main_cols.append("재배치존")

    existing_main_cols = [c for c in alloc_main_cols if c in alloc_with_zones.columns]
    alloc_main_df = alloc_with_zones[existing_main_cols].rename(columns=alloc_main_labels)
    st.dataframe(alloc_main_df, use_container_width=True, hide_index=True)

    alloc_csv = alloc_main_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label=f"{mode_label} 할당 결과 CSV 다운로드",
        data=alloc_csv,
        file_name=f"allocation_{mode}_district.csv",
        mime="text/csv",
    )

# ─── 2. 재배치존 선정 결과 (선정된 존 상단 노출) ─────────────
if selected_zones_df is not None and not selected_zones_df.empty:
    st.divider()
    st.subheader("재배치존 선정 결과")

    selected_only = selected_zones_df[selected_zones_df["selected"]].copy()
    n_selected = len(selected_only)
    n_total = len(selected_zones_df)
    st.success(
        f"총 {n_total}개 재배치존 중 **{n_selected}개** 선정 "
        f"(존당 10대 × {n_selected}개 = {n_selected * 10}대)"
    )

    zone_display_cols = [
        "h3_district_name", "zone_title", "demand_score", "allocated", "selected",
    ]
    zone_labels = {
        "h3_district_name": "District",
        "zone_title": "재배치존",
        "demand_score": "수요 점수",
        "allocated": "배치 대수",
        "selected": "선정",
    }
    existing_zone_cols = [c for c in zone_display_cols if c in selected_zones_df.columns]
    zone_display = selected_zones_df[existing_zone_cols].rename(columns=zone_labels)
    st.dataframe(zone_display, use_container_width=True, hide_index=True)

    zone_csv = zone_display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="재배치존 선정 결과 CSV 다운로드",
        data=zone_csv,
        file_name="selected_rebalance_zones.csv",
        mime="text/csv",
    )

# ─── 3. 지도 ─────────────────────────────────────────────────
st.divider()
st.subheader(f"{mode_label} 대상 지역 지도")

if mode == "deploy":
    st.caption(
        f"빨간색 = {mode_label} 할당 지역 (할당 대수 표시) | "
        f"회색 = 기타 지역 | 파란색 마커 = 선정 Zone | 회색 마커 = 미선정 Zone"
    )
else:
    st.caption(f"빨간색 = {mode_label} 할당 지역 (할당 대수 표시) | 회색 = 기타 지역")

deck = create_allocation_map(
    df, polygons_df, result,
    rebalance_zones_df=rebalance_zones_df,
    selected_zones_df=selected_zones_df,
    mode=mode,
)
st.pydeck_chart(deck, use_container_width=True, height=500)

# ─── 4. 할당 근거 상세 데이터 ────────────────────────────────
if not result.empty:
    st.divider()
    with st.expander("할당 근거 상세 데이터", expanded=False):
        alloc_detail_cols = [
            "alloc_priority", "h3_district_name", "allocated", "gap_int",
            "avg_bike_count", "current_bike_count", "avg_accessibility", "h3_area_name", "area_group",
        ]
        alloc_detail_labels = {
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
        existing_detail_cols = [c for c in alloc_detail_cols if c in result.columns]
        alloc_detail_df = result[existing_detail_cols].rename(columns=alloc_detail_labels)
        st.dataframe(alloc_detail_df, use_container_width=True, hide_index=True)

# ─── 5. 전체 지역 상세 데이터 (마지막) ───────────────────────
st.divider()
with st.expander("전체 지역 상세 데이터", expanded=False):
    kpis = get_summary_kpis(df)
    kpi_r1c1, kpi_r1c2, kpi_r1c3 = st.columns(3)
    kpi_r1c1.metric("평균 공급성공률", f"{kpis['avg_accessibility']:.1%}")
    kpi_r1c2.metric("총 배치 기기 수", f"{kpis['total_bike_count']:,.0f}대")
    kpi_r1c3.metric("분석 지역 수", f"{kpis['total_areas']}개")

    kpi_r2c1, kpi_r2c2 = st.columns(2)
    kpi_r2c1.metric(
        "목표 미달 지역",
        f"{kpis['areas_below_target']}개",
        delta=f"-{kpis['total_deploy_needed']}대 부족",
        delta_color="inverse",
    )
    kpi_r2c2.metric(
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
