-- examples/completeness-checks.sql
-- Check for null values across multiple columns

-- Method 1: Individual column checks
SELECT 
  'user_id' as column_name,
  COUNT(*) as total_rows,
  SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_count,
  ROUND(100.0 * SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as null_percentage,
  CASE 
    WHEN SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) = 0 THEN 'PASS'
    ELSE 'FAIL'
  END as status
FROM samples.tpch.customer

UNION ALL

SELECT 
  'c_name' as column_name,
  COUNT(*) as total_rows,
  SUM(CASE WHEN c_name IS NULL THEN 1 ELSE 0 END) as null_count,
  ROUND(100.0 * SUM(CASE WHEN c_name IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as null_percentage,
  CASE 
    WHEN SUM(CASE WHEN c_name IS NULL THEN 1 ELSE 0 END) = 0 THEN 'PASS'
    ELSE 'FAIL'
  END as status
FROM samples.tpch.customer

UNION ALL

SELECT 
  'c_phone' as column_name,
  COUNT(*) as total_rows,
  SUM(CASE WHEN c_phone IS NULL THEN 1 ELSE 0 END) as null_count,
  ROUND(100.0 * SUM(CASE WHEN c_phone IS NULL THEN 1 ELSE 0 END) / COUNT(*), 2) as null_percentage,
  CASE 
    WHEN SUM(CASE WHEN c_phone IS NULL THEN 1 ELSE 0 END) = 0 THEN 'PASS'
    ELSE 'FAIL'
  END as status
FROM samples.tpch.customer;