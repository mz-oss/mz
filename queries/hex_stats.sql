-- Hex 단위: 최근 14일(2주) 공급 성공률 및 배치 기기 평균
SELECT
    h3_area_name,
    h3_district_name,
    h3_index,
    ROUND(AVG(bike_count_100_avg), 2) AS avg_bike_count,
    ROUND(AVG(accessibility_ratio), 4) AS avg_accessibility,
    ROUND(AVG(conversion_ratio), 4) AS avg_conversion
FROM `management.weekly_bike_accessibility_by_hex`
WHERE week >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND is_operating = TRUE
  AND h3_area_name IS NOT NULL
  AND h3_district_name IS NOT NULL
  AND h3_index IS NOT NULL
GROUP BY h3_area_name, h3_district_name, h3_index
ORDER BY h3_area_name, h3_district_name, h3_index
