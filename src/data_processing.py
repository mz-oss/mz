"""적정 대수, 부족/과잉 대수, 우선순위 계산 로직."""

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
    safe_accessibility = result[accessibility_col].fillna(1.0).clip(lower=0.01)

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


def allocate_bikes(
    df: pd.DataFrame,
    total_bikes: int,
    mode: str = "deploy",
) -> pd.DataFrame:
    """총 배치/수거 대수를 우선순위 기반으로 지역에 할당합니다.

    Args:
        df: calculate_supply_gap 결과 데이터프레임
        total_bikes: 총 배치 또는 수거할 대수
        mode: 'deploy'(배치) 또는 'collect'(수거)

    Returns:
        allocated 컬럼이 추가된 필터링된 데이터프레임
    """
    if mode == "deploy":
        # 배치: gap > 0 인 지역만 (부족한 곳)
        target = df[df["gap_int"] > 0].copy()
        target = target.sort_values("gap", ascending=False)
    else:
        # 수거: gap < 0 인 지역만 (과잉인 곳)
        target = df[df["gap_int"] < 0].copy()
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
        assign = min(need, remaining)
        allocated.append(assign)
        remaining -= assign

    target["allocated"] = allocated
    target = target[target["allocated"] > 0]

    # 할당 후 우선순위 재계산
    if not target.empty:
        target["alloc_priority"] = range(1, len(target) + 1)

    return target


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
