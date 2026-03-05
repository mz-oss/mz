-- District 단위: 최근 7일 공급 성공률 및 배치 기기 평균 + 최신일 현재 기기수 (area_group 포함)
WITH daily_bike AS (
    -- daily_hex_48h: Hex별 bike_cnt를 일별 District 합산
    SELECT
        h3_area_name,
        h3_district_name,
        date,
        ROUND(SUM(bike_cnt), 2) AS daily_bike_count
    FROM `elecle-9be54.management.daily_hex_48h`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
      AND h3_area_name IS NOT NULL
      AND h3_district_name IS NOT NULL
    GROUP BY h3_area_name, h3_district_name, date
),
bike AS (
    -- 7일 평균 기기수
    SELECT h3_area_name, h3_district_name, AVG(daily_bike_count) AS avg_bike_count
    FROM daily_bike
    GROUP BY h3_area_name, h3_district_name
),
current_bike AS (
    -- 가장 최신 날짜의 기기수 (현재 기기수)
    SELECT h3_area_name, h3_district_name, daily_bike_count AS current_bike_count
    FROM daily_bike
    WHERE date = (SELECT MAX(date) FROM daily_bike)
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
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
      AND h3_area_name IS NOT NULL
      AND h3_district_name IS NOT NULL
    GROUP BY h3_area_name, h3_district_name
)
SELECT
    `elecle-9be54.udf.get_area_group`(b.h3_area_name) AS area_group,
    b.h3_area_name,
    b.h3_district_name,
    b.avg_bike_count,
    COALESCE(cb.current_bike_count, b.avg_bike_count) AS current_bike_count,
    a.avg_accessibility,
    a.avg_conversion,
    a.total_log_cnt,
    a.estimated_total_demand,
    a.days_count
FROM bike b
LEFT JOIN current_bike cb
  ON b.h3_area_name = cb.h3_area_name
  AND b.h3_district_name = cb.h3_district_name
LEFT JOIN accessibility a
  ON b.h3_area_name = a.h3_area_name
  AND b.h3_district_name = a.h3_district_name
ORDER BY area_group, b.h3_area_name, b.h3_district_name
