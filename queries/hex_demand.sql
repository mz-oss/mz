-- Hex 단위 수요량 (최근 4주, 앱 오픈 로그 × 1.5)
SELECT
    h3_district_name,
    h3_index,
    CAST(ROUND(SUM(total_log_cnt) * 1.5) AS INT64) AS estimated_demand
FROM `elecle-9be54.management.weekly_bike_accessibility_by_hex`
WHERE week >= DATE_SUB(CURRENT_DATE(), INTERVAL 28 DAY)
  AND h3_district_name IS NOT NULL
  AND h3_index IS NOT NULL
  AND total_log_cnt > 0
GROUP BY h3_district_name, h3_index
ORDER BY h3_district_name, estimated_demand DESC
