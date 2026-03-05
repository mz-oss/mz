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


def _empty_map() -> pdk.Deck:
    """데이터가 없을 때 기본 지도를 반환합니다."""
    return pdk.Deck(
        layers=[],
        initial_view_state=pdk.ViewState(
            latitude=37.5665, longitude=126.978, zoom=10
        ),
    )
