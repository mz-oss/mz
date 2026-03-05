-- District 단위: 최근 14일 공급 성공률 및 배치 기기 평균
WITH bike AS (
    -- daily_hex_48h: 시간대별 → 일별 평균 → 일간 평균 (2단계 집계), district 기준
    SELECT h3_area_name, h3_district_name, AVG(avg_bike_count) AS avg_bike_count
    FROM (
      SELECT
        h3_area_name,
        h3_district_name,
        date,
        ROUND(SUM(bike_cnt), 2) AS avg_bike_count
      FROM `elecle-9be54.management.daily_hex_48h`
      WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
        AND h3_area_name IS NOT NULL
        AND h3_district_name IS NOT NULL
      GROUP BY h3_area_name, h3_district_name, date
    )
    GROUP BY h3_area_name, h3_district_name
),
accessibility AS (
    SELECT
        h3_area_name,
        h3_district_name,
        ROUND(AVG(accessibility_ratio), 4) AS avg_accessibility,
        ROUND(AVG(conversion_ratio), 4) AS avg_conversion,
        SUM(total_log_cnt) AS total_log_cnt,
        -- 안드로이드만 로그가 찍히므로 1.5배 보정
        CAST(ROUND(SUM(total_log_cnt) * 1.5) AS INT64) AS estimated_total_demand,
        COUNT(DISTINCT date) AS days_count
    FROM `elecle-9be54.management.daily_bike_accessibility_by_district`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
      AND h3_area_name IS NOT NULL
      AND h3_district_name IS NOT NULL
    GROUP BY h3_area_name, h3_district_name
)
SELECT
    b.h3_area_name,
    b.h3_district_name,
    b.avg_bike_count,
    a.avg_accessibility,
    a.avg_conversion,
    a.total_log_cnt,
    a.estimated_total_demand,
    a.days_count
FROM bike b
LEFT JOIN accessibility a
  ON b.h3_area_name = a.h3_area_name
  AND b.h3_district_name = a.h3_district_name
ORDER BY b.h3_area_name, b.h3_district_name
