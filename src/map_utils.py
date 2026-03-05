"""지도 시각화 유틸리티 (pydeck 기반)."""

import json

import pandas as pd
import pydeck as pdk


# 색상 스케일: 빨강(부족) ↔ 회색(적정) ↔ 파랑(과잉)
def _gap_to_color(gap: float, max_abs_gap: float) -> list[int]:
    """부족/과잉 대수를 색상으로 변환합니다.

    빨강 = 배치 필요 (부족), 파랑 = 수거 가능 (과잉)
    """
    if max_abs_gap == 0 or pd.isna(max_abs_gap):
        return [200, 200, 200, 160]

    if pd.isna(gap):
        return [200, 200, 200, 100]

    ratio = min(abs(gap) / max_abs_gap, 1.0)
    alpha = int(80 + 120 * ratio)

    if gap > 0:
        # 빨강 계열 (배치 필요)
        return [220, int(60 * (1 - ratio)), int(60 * (1 - ratio)), alpha]
    elif gap < 0:
        # 파랑 계열 (수거 가능)
        return [int(60 * (1 - ratio)), int(100 * (1 - ratio)), 220, alpha]
    else:
        return [200, 200, 200, 100]


def create_district_map(
    df: pd.DataFrame,
    polygons_df: pd.DataFrame,
    highlight_districts: set[str] | None = None,
) -> pdk.Deck:
    """District 폴리곤 기반 지도를 생성합니다.

    Args:
        highlight_districts: 빨간색으로 강조할 district 이름 집합.
            지정하면 해당 district만 빨간색, 나머지는 회색으로 표시.
    """
    if df.empty:
        return _empty_map()

    max_abs_gap = df["gap"].abs().max() if "gap" in df.columns else 1

    merged = df.merge(
        polygons_df[["name", "polygon"]],
        left_on="h3_district_name",
        right_on="name",
        how="left",
    )

    poly_data = []
    for _, row in merged.iterrows():
        raw_polygon = row.get("polygon")
        try:
            is_na = pd.isna(raw_polygon)
        except (TypeError, ValueError):
            is_na = raw_polygon is None
        if is_na or not raw_polygon:
            continue

        try:
            geo = json.loads(raw_polygon) if isinstance(raw_polygon, str) else raw_polygon
            coords = geo.get("coordinates", [])
            if not coords or not coords[0]:
                continue
            # MultiPolygon → 첫 번째 폴리곤 사용
            polygon_coords = coords[0][0] if geo["type"] == "MultiPolygon" else coords[0]

            # 중심 좌표 계산
            lngs = [c[0] for c in polygon_coords]
            lats = [c[1] for c in polygon_coords]
            if not lats or not lngs:
                continue
            center_lat = sum(lats) / len(lats)
            center_lng = sum(lngs) / len(lngs)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError,
                AttributeError, ZeroDivisionError):
            continue

        gap = row.get("gap", 0)
        if pd.isna(gap):
            gap = 0
        district_name = row.get("h3_district_name", "")

        if highlight_districts is not None:
            if district_name in highlight_districts:
                color = [220, 40, 40, 200]  # 빨간색
            else:
                color = [200, 200, 200, 80]  # 회색
        else:
            color = _gap_to_color(gap, max_abs_gap)

        poly_data.append({
            "polygon": polygon_coords,
            "district": row.get("h3_district_name", ""),
            "bike_count": row.get("avg_bike_count", 0),
            "accessibility": row.get("avg_accessibility", 0),
            "gap": gap,
            "gap_int": row.get("gap_int", 0),
            "status": row.get("status", ""),
            "color": color,
            "lat": center_lat,
            "lng": center_lng,
        })

    if not poly_data:
        return _empty_map()

    avg_lat = sum(d["lat"] for d in poly_data) / len(poly_data)
    avg_lng = sum(d["lng"] for d in poly_data) / len(poly_data)

    layer = pdk.Layer(
        "PolygonLayer",
        data=poly_data,
        get_polygon="polygon",
        get_fill_color="color",
        get_line_color=[50, 50, 50, 180],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        latitude=avg_lat,
        longitude=avg_lng,
        zoom=11,
        pitch=0,
    )

    return pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={
            "html": (
                "<b>{district}</b><br/>"
                "배치 기기: {bike_count}대<br/>"
                "공급성공률: {accessibility:.1%}<br/>"
                "부족/과잉: <b>{gap_int}대</b> ({status})"
            ),
            "style": {"backgroundColor": "#333", "color": "white"},
        },
    )


def create_allocation_map(
    df: pd.DataFrame,
    polygons_df: pd.DataFrame,
    result: pd.DataFrame,
    rebalance_zones_df: pd.DataFrame | None = None,
    mode: str = "deploy",
) -> pdk.Deck:
    """배치/수거 할당 결과와 Rebalance Zone을 함께 표시하는 지도를 생성합니다.

    Args:
        df: calculate_supply_gap 결과 데이터프레임
        polygons_df: District 폴리곤 데이터
        result: allocate_bikes 결과 (allocated 컬럼 포함)
        rebalance_zones_df: Rebalance Zone 데이터 (location 컬럼 포함)
        mode: 'deploy' 또는 'collect'
    """
    if df.empty:
        return _empty_map()

    # 할당된 district 목록
    highlight_districts = {}
    if not result.empty and "h3_district_name" in result.columns:
        for _, row in result.iterrows():
            highlight_districts[row["h3_district_name"]] = int(row.get("allocated", 0))

    merged = df.merge(
        polygons_df[["name", "polygon"]],
        left_on="h3_district_name",
        right_on="name",
        how="left",
    )

    poly_data = []
    text_data = []
    for _, row in merged.iterrows():
        raw_polygon = row.get("polygon")
        try:
            is_na = pd.isna(raw_polygon)
        except (TypeError, ValueError):
            is_na = raw_polygon is None
        if is_na or not raw_polygon:
            continue

        try:
            geo = json.loads(raw_polygon) if isinstance(raw_polygon, str) else raw_polygon
            coords = geo.get("coordinates", [])
            if not coords or not coords[0]:
                continue
            polygon_coords = coords[0][0] if geo["type"] == "MultiPolygon" else coords[0]

            lngs = [c[0] for c in polygon_coords]
            lats = [c[1] for c in polygon_coords]
            if not lats or not lngs:
                continue
            center_lat = sum(lats) / len(lats)
            center_lng = sum(lngs) / len(lngs)
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError,
                AttributeError, ZeroDivisionError):
            continue

        gap = row.get("gap", 0)
        if pd.isna(gap):
            gap = 0
        district_name = row.get("h3_district_name", "")
        allocated = highlight_districts.get(district_name, 0)

        if allocated > 0:
            color = [220, 40, 40, 200]  # 빨간색 (할당 대상)
        else:
            color = [200, 200, 200, 80]  # 회색

        mode_label = "배치" if mode == "deploy" else "수거"
        acc_val = row.get("avg_accessibility", 0)
        acc_str = f"{acc_val:.1%}" if not pd.isna(acc_val) else "N/A"
        alloc_text = f"<b>{mode_label} 할당: {allocated}대</b>" if allocated > 0 else ""

        poly_data.append({
            "polygon": polygon_coords,
            "district": district_name,
            "title": "",
            "bike_count": round(row.get("avg_bike_count", 0), 1),
            "accessibility": acc_str,
            "gap": gap,
            "gap_int": row.get("gap_int", 0),
            "status": row.get("status", ""),
            "allocated": allocated,
            "alloc_text": alloc_text,
            "color": color,
            "lat": center_lat,
            "lng": center_lng,
        })

        # 할당된 지역에 텍스트 라벨 표시
        if allocated > 0:
            mode_label = "배치" if mode == "deploy" else "수거"
            text_data.append({
                "lat": center_lat,
                "lng": center_lng,
                "text": f"{district_name}\n{mode_label} {allocated}대",
            })

    if not poly_data:
        return _empty_map()

    avg_lat = sum(d["lat"] for d in poly_data) / len(poly_data)
    avg_lng = sum(d["lng"] for d in poly_data) / len(poly_data)

    layers = []

    # District 폴리곤 레이어
    layers.append(pdk.Layer(
        "PolygonLayer",
        data=poly_data,
        get_polygon="polygon",
        get_fill_color="color",
        get_line_color=[50, 50, 50, 180],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    ))

    # 할당 대수 텍스트 레이어
    if text_data:
        layers.append(pdk.Layer(
            "TextLayer",
            data=text_data,
            get_position=["lng", "lat"],
            get_text="text",
            get_size=14,
            get_color=[255, 255, 255, 255],
            get_angle=0,
            get_text_anchor='"middle"',
            get_alignment_baseline='"center"',
            font_family='"sans-serif"',
            background=True,
            get_background_color=[0, 0, 0, 160],
            background_padding=[4, 2],
        ))

    # Rebalance Zone 레이어 (파란색 마커)
    if rebalance_zones_df is not None and not rebalance_zones_df.empty:
        rz_data = _parse_rebalance_zones(rebalance_zones_df)
        if rz_data:
            icon_data = {
                "url": "https://raw.githubusercontent.com/visgl/deck.gl-data/master/website/icon-atlas.png",
                "width": 128,
                "height": 128,
                "anchorY": 128,
                "mask": True,
            }
            for d in rz_data:
                d["icon_data"] = icon_data
            layers.append(pdk.Layer(
                "IconLayer",
                data=rz_data,
                get_icon="icon_data",
                get_position=["lng", "lat"],
                get_size=40,
                get_color=[30, 100, 230, 220],  # 파란색
                pickable=True,
                size_scale=1,
            ))

    mode_label = "배치" if mode == "deploy" else "수거"
    view_state = pdk.ViewState(
        latitude=avg_lat,
        longitude=avg_lng,
        zoom=11,
        pitch=0,
    )

    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip={
            "html": (
                "<b>{district}{title}</b><br/>"
                "배치 기기: {bike_count}대<br/>"
                "공급성공률: {accessibility}<br/>"
                "부족/과잉: <b>{gap_int}대</b> {status}<br/>"
                "{alloc_text}"
            ),
            "style": {"backgroundColor": "#333", "color": "white"},
        },
    )


def _parse_rebalance_zones(rz_df: pd.DataFrame) -> list[dict]:
    """Rebalance Zone 데이터를 파싱하여 지도 표시용 데이터로 변환합니다."""
    rz_data = []
    for _, row in rz_df.iterrows():
        location_str = row.get("location")
        if not location_str:
            continue
        try:
            geo = json.loads(location_str) if isinstance(location_str, str) else location_str
            if isinstance(geo, dict):
                geo_type = geo.get("type", "")
                if geo_type == "Point":
                    lng, lat = geo["coordinates"]
                elif geo_type in ("Polygon", "MultiPolygon"):
                    coords = geo["coordinates"]
                    if geo_type == "MultiPolygon":
                        coords = coords[0]
                    flat = coords[0]
                    lng = sum(c[0] for c in flat) / len(flat)
                    lat = sum(c[1] for c in flat) / len(flat)
                else:
                    continue
            elif isinstance(geo, list) and len(geo) == 2:
                lng, lat = float(geo[0]), float(geo[1])
            else:
                continue
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
            continue

        rz_data.append({
            "lat": lat,
            "lng": lng,
            "title": row.get("title", ""),
            "weight": row.get("weight", 0),
            "note": row.get("note", ""),
            "district": "",
            "bike_count": "",
            "accessibility": "",
            "gap_int": "",
            "status": "",
            "alloc_text": f"Rebalance Zone (가중치: {row.get('weight', 0)})",
        })
    return rz_data


def _empty_map() -> pdk.Deck:
    """데이터가 없을 때 기본 지도를 반환합니다."""
    return pdk.Deck(
        layers=[],
        initial_view_state=pdk.ViewState(
            latitude=37.5665, longitude=126.978, zoom=10
        ),
    )
