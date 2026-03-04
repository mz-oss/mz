-- District 폴리곤 정보 조회
SELECT
    gd.id,
    gd.code,
    gd.name,
    gd.polygon,
    gd.area_id
FROM `service.geo_district` AS gd
WHERE gd.polygon IS NOT NULL
  AND JSON_EXTRACT(gd.polygon, '$.coordinates') != '[]'
