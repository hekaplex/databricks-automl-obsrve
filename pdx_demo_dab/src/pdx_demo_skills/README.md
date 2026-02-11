# Data Quality Checks Skill

## Overview

This skill provides comprehensive guidance for implementing data quality validation on Delta tables in Databricks. It includes patterns for completeness checks, duplicate detection, constraint enforcement, and automated monitoring.

## Quick Start

1. **Load the Skill**: The Assistant will automatically load this skill when you ask about data quality validation
2. **Review Patterns**: Check the SKILL.md file for common validation patterns
3. **Run Examples**: Use the SQL queries in the examples section
4. **Customize**: Adapt the patterns to your specific data quality requirements

## What's Included

* **SKILL.md**: Main skill documentation with YML frontmatter
* **SQL Examples**: Completeness checks, duplicate detection, constraint management
* **Best Practices**: Guidelines for implementing quality checks at scale
* **Automation Scripts**: Sample workflows for scheduled quality monitoring

## Use Cases

* Validate data completeness (null checks)
* Detect duplicate records
* Enforce data constraints (CHECK constraints)
* Generate quality reports
* Set up automated quality monitoring
* Track quality metrics over time

## Prerequisites

* Databricks Runtime 13.3 LTS or higher
* Access to Unity Catalog (for constraint management)
* SQL Warehouse or Cluster with appropriate permissions

## Example Usage

### Check for Null Values

```
%sql
SELECT 
  'user_id' as column_name,
  COUNT(*) as total_rows,
  SUM(CASE WHEN user_id IS NULL THEN 1 ELSE 0 END) as null_count
FROM catalog.schema.customers;
```
## Find Duplicates
```
%sql
SELECT 
  customer_id,
  COUNT(*) as duplicate_count
FROM catalog.schema.customers
GROUP BY customer_id
HAVING COUNT(*) > 1;
```
### Add Quality Constraints
```
%sql
ALTER TABLE catalog.schema.customers
ADD CONSTRAINT valid_email CHECK (email LIKE '%@%.%');
```
## File Structure
```
skills/data-quality-checks/
├── SKILL.md                    # Main skill file with YML frontmatter
├── README.md                   # This file
├── examples/
│   ├── completeness-checks.sql # Null value detection queries
│   ├── duplicate-detection.sql # Duplicate finding queries
│   └── quality-report.sql      # Comprehensive quality reports
└── workflows/
    └── daily-quality-check.yml # Sample workflow definition
```
## Related Skills
* **data-sampling**: Best practices for sampling data before validation
* **writing-sql**: SQL patterns for quality checks
* **using-metric-views**: Creating reusable quality metrics
### Contributing
To improve this skill:

1. Add new validation patterns to SKILL.md
1. Include SQL examples in the examples/ directory
1. Update the version number in the YML frontmatter
1. Document any new dependencies or prerequisites

## Version History

* **1.0.0** (2026-02-10): Initial release with SQL-based quality checks

## Support

For questions or issues with this skill, contact the Field Engineering team or submit feedback through the Assistant.
```