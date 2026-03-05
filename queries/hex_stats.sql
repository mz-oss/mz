-- Hex 단위: 현재 평균 기기수 (daily_hex_48h) + 공급 성공률 (weekly_bike_accessibility_by_hex)
WITH bike AS (
    -- daily_hex_48h: 최근 14일 시간대별 기기수 평균
    SELECT
        h3_area_name,
        h3_district_name,
        h3_index,
        ROUND(AVG(bike_cnt), 2) AS avg_bike_count
    FROM `elecle-9be54.management.daily_hex_48h`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
      AND h3_area_name IS NOT NULL
      AND h3_district_name IS NOT NULL
      AND h3_index IS NOT NULL
    GROUP BY h3_area_name, h3_district_name, h3_index
),
accessibility AS (
    -- weekly_bike_accessibility_by_hex: 최근 14일 공급 성공률
    SELECT
        h3_index,
        ROUND(AVG(accessibility_ratio), 4) AS avg_accessibility,
        ROUND(AVG(conversion_ratio), 4) AS avg_conversion
    FROM `elecle-9be54.management.weekly_bike_accessibility_by_hex`
    WHERE week >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
      AND is_operating = TRUE
      AND h3_index IS NOT NULL
    GROUP BY h3_index
)
SELECT
    b.h3_area_name,
    b.h3_district_name,
    b.h3_index,
    b.avg_bike_count,
    a.avg_accessibility,
    a.avg_conversion
FROM bike b
LEFT JOIN accessibility a
  ON b.h3_index = a.h3_index
ORDER BY b.h3_area_name, b.h3_district_name, b.h3_index
