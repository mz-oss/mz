-- Rebalance Zone 조회 (활성 존만)
SELECT
    rz.id,
    rz.title,
    rz.location,
    rz.weight,
    rz.note,
    rz.gbg_id,
    rz.is_active
FROM `elecle-9be54.service.rebalance_zone` AS rz
WHERE rz.is_active = TRUE
  AND rz.location IS NOT NULL
