-- Rebalance Zone 조회 (활성 존만, 동일 title 중복 제거)
SELECT
    rz.title,
    rz.location,
    rz.weight,
    rz.note
FROM (
    SELECT
        title,
        location,
        weight,
        note,
        ROW_NUMBER() OVER (PARTITION BY title ORDER BY weight DESC) AS rn
    FROM `elecle-9be54.service.rebalance_zone`
    WHERE is_active = TRUE
      AND location IS NOT NULL
) AS rz
WHERE rz.rn = 1
