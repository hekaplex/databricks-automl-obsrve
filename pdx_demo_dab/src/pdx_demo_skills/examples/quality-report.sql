-- examples/quality-report.sql
-- Comprehensive data quality report

WITH table_stats AS (
  SELECT 
    COUNT(*) as total_rows,
    COUNT(DISTINCT c_custkey) as unique_customers,
    
    -- Null counts
    SUM(CASE WHEN c_custkey IS NULL THEN 1 ELSE 0 END) as null_custkey,
    SUM(CASE WHEN c_name IS NULL THEN 1 ELSE 0 END) as null_name,
    SUM(CASE WHEN c_phone IS NULL THEN 1 ELSE 0 END) as null_phone,
    SUM(CASE WHEN c_acctbal IS NULL THEN 1 ELSE 0 END) as null_balance,
    
    -- Value ranges
    MIN(c_acctbal) as min_balance,
    MAX(c_acctbal) as max_balance,
    AVG(c_acctbal) as avg_balance,
    
    -- Data freshness (if date column exists)
    CURRENT_DATE() as report_date
    
  FROM samples.tpch.customer
)
SELECT 
  report_date,
  total_rows,
  unique_customers,
  ROUND(100.0 * unique_customers / total_rows, 2) as uniqueness_pct,
  
  -- Completeness metrics
  null_custkey,
  ROUND(100.0 * null_custkey / total_rows, 2) as null_custkey_pct,
  null_name,
  ROUND(100.0 * null_name / total_rows, 2) as null_name_pct,
  null_phone,
  ROUND(100.0 * null_phone / total_rows, 2) as null_phone_pct,
  null_balance,
  ROUND(100.0 * null_balance / total_rows, 2) as null_balance_pct,
  
  -- Value statistics
  ROUND(min_balance, 2) as min_balance,
  ROUND(max_balance, 2) as max_balance,
  ROUND(avg_balance, 2) as avg_balance,
  
  -- Overall quality score (100 - average null percentage)
  ROUND(100 - (
    (null_custkey + null_name + null_phone + null_balance) * 100.0 / (total_rows * 4)
  ), 2) as overall_quality_score
  
FROM table_stats;