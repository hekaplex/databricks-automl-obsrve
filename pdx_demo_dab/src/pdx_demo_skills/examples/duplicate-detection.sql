-- examples/duplicate-detection.sql
-- Find duplicate records based on key columns

-- Method 1: Simple duplicate count
WITH duplicate_summary AS (
  SELECT 
    c_custkey,
    COUNT(*) as record_count
  FROM samples.tpch.customer
  GROUP BY c_custkey
  HAVING COUNT(*) > 1
)
SELECT 
  COUNT(*) as total_duplicate_groups,
  SUM(record_count) as total_duplicate_records
FROM duplicate_summary;

-- Method 2: Detailed duplicate analysis
-- WITH duplicates AS (
--   SELECT 
--     c_custkey,
--     c_name,
--     c_phone,
--     COUNT(*) as duplicate_count,
--     ROW_NUMBER() OVER (PARTITION BY c_custkey ORDER BY c_name) as row_num
--   FROM samples.tpch.customer
--   GROUP BY c_custkey, c_name, c_phone
--   HAVING COUNT(*) > 1
-- )
-- SELECT 
--   c_custkey,
--   c_name,
--   c_phone,
--   duplicate_count,
--   CASE WHEN row_num = 1 THEN 'KEEP' ELSE 'REMOVE' END as recommendation
-- FROM duplicates
-- ORDER BY duplicate_count DESC, c_custkey;

-- Method 3: Find duplicates with all original records
-- SELECT 
--   c.*,
--   COUNT(*) OVER (PARTITION BY c.c_custkey) as duplicate_count
-- FROM samples.tpch.customer c
-- QUALIFY duplicate_count > 1
-- ORDER BY c.c_custkey;