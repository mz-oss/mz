"""적정 대수, 부족/과잉 대수, 우선순위 계산 로직."""

import json
import math

import h3
import pandas as pd

DEFAULT_TARGET_RATE = 0.80


def calculate_supply_gap(
    df: pd.DataFrame,
    target_rate: float = DEFAULT_TARGET_RATE,
    bike_col: str = "avg_bike_count",
    accessibility_col: str = "avg_accessibility",
) -> pd.DataFrame:
    """공급 갭(부족/과잉 대수)을 계산합니다.

    적정 대수 = 현재 대수 × (목표 공급성공률 / 현재 공급성공률)
    부족 대수 = 적정 대수 - 현재 대수
      양수 → 배치 필요
      음수 → 수거 가능

    Args:
        df: avg_bike_count, avg_accessibility 컬럼을 포함한 데이터프레임
        target_rate: 목표 공급 성공률 (기본 0.80)
        bike_col: 기기 대수 컬럼명
        accessibility_col: 공급 성공률 컬럼명

    Returns:
        적정_대수, 부족_대수, 우선순위 컬럼이 추가된 데이터프레임
    """
    result = df.copy()

    # 공급성공률이 0이거나 NULL인 경우 처리 (NaN → 1.0 = 100%)
    result[accessibility_col] = result[accessibility_col].fillna(1.0)
    safe_accessibility = result[accessibility_col].clip(lower=0.01)

    result["optimal_bike_count"] = (
        result[bike_col] * (target_rate / safe_accessibility)
    ).round(1)

    result["gap"] = (result["optimal_bike_count"] - result[bike_col]).round(1)

    # 양수 = 배치 필요, 음수 = 수거 가능
    result["gap_int"] = result["gap"].round(0).astype(int)

    result["status"] = result["gap_int"].apply(
        lambda x: "배치 필요" if x > 0 else ("수거 가능" if x < 0 else "적정")
    )

    # 우선순위: 부족 수량이 많은 곳이 높은 우선순위
    result["priority"] = result["gap"].abs().rank(ascending=False, method="min").astype(int)

    return result.sort_values("priority")


def _compute_rounded_demand(gap_df: pd.DataFrame, mode: str) -> int:
    """10대 단위 올림 적용 시 전체 수요 합계를 계산합니다."""
    if mode == "deploy":
        gaps = gap_df[gap_df["gap_int"] > 0]["gap_int"]
    else:
        gaps = gap_df[gap_df["gap_int"] < 0]["gap_int"].abs()
    return sum(math.ceil(g / 10) * 10 for g in gaps)


def _find_target_rate(
    raw_df: pd.DataFrame,
    total_bikes: int,
    mode: str,
    initial_rate: float = DEFAULT_TARGET_RATE,
) -> float:
    """잔여대수가 0이 되도록 목표 공급성공률을 탐색합니다.

    initial_rate에서 시작하여 0.01 단위로 올려가며(배치) 또는 내려가며(수거),
    10대 단위 올림 기준 전체 수요 >= total_bikes가 되는 최소 목표성공률을 찾습니다.
    """
    # 초기 비율에서 수요가 충분한지 확인
    gap_df = calculate_supply_gap(raw_df, target_rate=initial_rate)
    if _compute_rounded_demand(gap_df, mode) >= total_bikes:
        return initial_rate

    # 배치: 목표성공률을 올리면 gap 증가 → 수요 증가
    # 수거: 목표성공률을 내리면 gap(음수) 증가 → 수거 수요 증가
    if mode == "deploy":
        lo, hi = initial_rate, 0.99
        step_dir = 1
    else:
        lo, hi = 0.01, initial_rate
        step_dir = -1

    # 0.01 단위 선형 탐색 (최대 99단계이므로 충분히 빠름)
    rate = initial_rate
    while True:
        rate = round(rate + step_dir * 0.01, 2)
        if mode == "deploy" and rate > 0.99:
            return 0.99
        if mode == "collect" and rate < 0.01:
            return 0.01
        gap_df = calculate_supply_gap(raw_df, target_rate=rate)
        if _compute_rounded_demand(gap_df, mode) >= total_bikes:
            return rate

    return rate


def allocate_bikes(
    df: pd.DataFrame,
    total_bikes: int,
    mode: str = "deploy",
    raw_df: pd.DataFrame | None = None,
    initial_target_rate: float = DEFAULT_TARGET_RATE,
) -> tuple[pd.DataFrame, float]:
    """총 배치/수거 대수를 우선순위 기반으로 지역에 할당합니다.

    - 각 지역 할당 대수는 10대 단위 올림
    - 잔여대수가 남으면 목표 공급성공률을 조정하여 잔여 0 달성

    Args:
        df: calculate_supply_gap 결과 데이터프레임
        total_bikes: 총 배치 또는 수거할 대수
        mode: 'deploy'(배치) 또는 'collect'(수거)
        raw_df: 원본 데이터프레임 (목표성공률 자동 조정 시 필요)
        initial_target_rate: 초기 목표 공급성공률

    Returns:
        (allocated 컬럼이 추가된 데이터프레임, 적용된 목표성공률) 튜플
    """
    # 목표성공률 자동 조정: raw_df가 있으면 잔여 0이 되는 비율 탐색
    adjusted_rate = initial_target_rate
    gap_df = df
    if raw_df is not None:
        adjusted_rate = _find_target_rate(
            raw_df, total_bikes, mode, initial_rate=initial_target_rate
        )
        if adjusted_rate != initial_target_rate:
            gap_df = calculate_supply_gap(raw_df, target_rate=adjusted_rate)

    if mode == "deploy":
        target = gap_df[gap_df["gap_int"] > 0].copy()
        target = target.sort_values("gap", ascending=False)
    else:
        target = gap_df[gap_df["gap_int"] < 0].copy()
        target["gap"] = target["gap"].abs()
        target["gap_int"] = target["gap_int"].abs()
        target = target.sort_values("gap", ascending=False)

    remaining = total_bikes
    allocated = []

    for idx, row in target.iterrows():
        if remaining <= 0:
            allocated.append(0)
            continue
        need = row["gap_int"]
        # 10대 단위 올림 (예: 3 → 10, 15 → 20)
        assign = math.ceil(need / 10) * 10
        assign = min(assign, remaining)
        allocated.append(assign)
        remaining -= assign

    # 목표성공률 최대까지 올렸는데도 잔여가 남으면 마지막 할당 지역에 추가
    if remaining > 0 and any(a > 0 for a in allocated):
        for i in range(len(allocated) - 1, -1, -1):
            if allocated[i] > 0:
                allocated[i] += remaining
                remaining = 0
                break

    target["allocated"] = allocated
    target = target[target["allocated"] > 0]

    if not target.empty:
        target["alloc_priority"] = range(1, len(target) + 1)

    return target, adjusted_rate


def _parse_zone_location(location) -> tuple[float, float] | None:
    """Rebalance Zone의 location 필드에서 (lat, lng)를 추출합니다."""
    if not location:
        return None
    try:
        geo = json.loads(location) if isinstance(location, str) else location
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
                return None
        elif isinstance(geo, list) and len(geo) == 2:
            lng, lat = float(geo[0]), float(geo[1])
        else:
            return None
        return (lat, lng)
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
        return None


def select_rebalance_zones(
    alloc_result: pd.DataFrame,
    rz_df: pd.DataFrame,
    hex_demand_df: pd.DataFrame,
    polygons_df: pd.DataFrame,
    bikes_per_zone: int = 10,
) -> pd.DataFrame:
    """District별 할당 대수에 따라 최적 재배치존을 선정합니다.

    각 재배치존을 hex에 매핑하고, 해당 hex + 인접 hex의 수요량 합계로 점수를 매겨
    점수가 높은 존부터 선정합니다.

    Args:
        alloc_result: allocate_bikes 결과 (h3_district_name, allocated 포함)
        rz_df: Rebalance Zone 원본 데이터 (id, title, location, weight, note)
        hex_demand_df: hex별 수요량 (h3_index, h3_district_name, estimated_demand)
        polygons_df: District 폴리곤 데이터
        bikes_per_zone: 존당 배치 대수 (기본 10)

    Returns:
        선정 결과 데이터프레임 (district, zone_title, demand_score, allocated, selected)
    """
    from src.map_utils import _point_in_polygon

    if alloc_result.empty or rz_df.empty or hex_demand_df.empty:
        return pd.DataFrame()

    # hex 수요 딕셔너리: {h3_index: demand}
    hex_demand = dict(
        zip(hex_demand_df["h3_index"], hex_demand_df["estimated_demand"])
    )

    # hex 데이터에서 해상도 추출
    sample_h3 = hex_demand_df["h3_index"].iloc[0]
    h3_resolution = h3.get_resolution(sample_h3)

    # 할당된 District별 폴리곤 준비
    alloc_districts = dict(
        zip(alloc_result["h3_district_name"], alloc_result["allocated"])
    )
    district_polygons = {}
    for _, row in polygons_df.iterrows():
        name = row.get("name", "")
        if name not in alloc_districts:
            continue
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
            district_polygons[name] = polygon_coords
        except (json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError):
            continue

    # 각 재배치존의 위치 파싱 + District 매핑 + 수요 점수 계산
    zone_rows = []
    for _, rz in rz_df.iterrows():
        loc = _parse_zone_location(rz.get("location"))
        if loc is None:
            continue
        lat, lng = loc

        # 어느 할당 District에 속하는지 판별
        matched_district = None
        for dist_name, poly in district_polygons.items():
            if _point_in_polygon(lat, lng, poly):
                matched_district = dist_name
                break
        if matched_district is None:
            continue

        # zone 위치를 hex로 변환 → 해당 hex + 인접 hex의 수요 합산
        zone_h3 = h3.latlng_to_cell(lat, lng, h3_resolution)
        neighbors = h3.grid_ring(zone_h3, 1)
        demand_score = hex_demand.get(zone_h3, 0)
        for nb in neighbors:
            demand_score += hex_demand.get(nb, 0)

        zone_rows.append({
            "h3_district_name": matched_district,
            "zone_id": rz.get("id", ""),
            "zone_title": rz.get("title", ""),
            "note": rz.get("note", ""),
            "lat": lat,
            "lng": lng,
            "demand_score": demand_score,
        })

    if not zone_rows:
        return pd.DataFrame()

    zones_df = pd.DataFrame(zone_rows)

    # District별로 수요 점수 순 정렬 → 상위 N개 선정
    selected_rows = []
    for district_name, allocated in alloc_districts.items():
        n_zones = math.ceil(allocated / bikes_per_zone)
        district_zones = zones_df[zones_df["h3_district_name"] == district_name].copy()
        district_zones = district_zones.sort_values("demand_score", ascending=False)

        for i, (_, zone) in enumerate(district_zones.iterrows()):
            row = zone.to_dict()
            row["selected"] = i < n_zones
            row["allocated"] = bikes_per_zone if i < n_zones else 0
            selected_rows.append(row)

    if not selected_rows:
        return pd.DataFrame()

    result = pd.DataFrame(selected_rows)
    result = result.sort_values(
        ["h3_district_name", "selected", "demand_score"],
        ascending=[True, False, False],
    )
    return result


def get_summary_kpis(df: pd.DataFrame) -> dict:
    """전체 KPI 요약을 계산합니다."""
    return {
        "avg_accessibility": round(df["avg_accessibility"].mean(), 4),
        "total_bike_count": round(df["avg_bike_count"].sum(), 0),
        "total_areas": len(df),
        "areas_below_target": int((df["avg_accessibility"] < DEFAULT_TARGET_RATE).sum()),
        "areas_above_target": int((df["avg_accessibility"] >= DEFAULT_TARGET_RATE).sum()),
        "total_deploy_needed": int(df[df["gap_int"] > 0]["gap_int"].sum()),
        "total_collect_possible": int(df[df["gap_int"] < 0]["gap_int"].abs().sum()),
    }
