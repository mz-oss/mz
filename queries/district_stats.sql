-- District 단위: 최근 14일 공급 성공률 및 배치 기기 평균
SELECT
    h3_area_name,
    h3_district_name,
    ROUND(AVG(bike_count_100_avg), 2) AS avg_bike_count,
    ROUND(AVG(accessibility_ratio), 4) AS avg_accessibility,
    ROUND(AVG(conversion_ratio), 4) AS avg_conversion,
    SUM(total_log_cnt) AS total_log_cnt,
    -- 안드로이드만 로그가 찍히므로 1.5배 보정
    CAST(ROUND(SUM(total_log_cnt) * 1.5) AS INT64) AS estimated_total_demand,
    COUNT(DISTINCT date) AS days_count
FROM `management.daily_bike_accessibility_by_district`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
  AND is_operating = TRUE
  AND h3_area_name IS NOT NULL
  AND h3_district_name IS NOT NULL
GROUP BY h3_area_name, h3_district_name
ORDER BY h3_area_name, h3_district_name
