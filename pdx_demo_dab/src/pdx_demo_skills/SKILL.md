---
name: data-quality-checks
version: 1.0.0
description: |
  Comprehensive data quality validation for Delta tables. Use when users need to:
  - Validate data completeness and accuracy
  - Check for null values, duplicates, or outliers
  - Implement data quality rules and constraints
  - Generate data quality reports
  - Set up automated quality monitoring
author: Field Engineering
tags:
  - data-quality
  - validation
  - delta-lake
  - monitoring
related_skills:
  - data-sampling
  - writing-sql
last_updated: 2025-02-10
---

# Data Quality Checks Skill

## Scope

This skill provides guidance for implementing comprehensive data quality checks on Delta tables in Databricks.

## When to Use This Skill

Load this skill when:
* User asks to validate data quality
* User needs to check for missing or invalid data
* User wants to implement data quality rules
* User needs to generate quality reports
* User is setting up data quality monitoring

## Core Principles

1. **Start with Schema Validation**: Always verify schema before data validation
2. **Use Delta Lake Features**: Leverage CHECK constraints and expectations
3. **Incremental Validation**: For large tables, validate incrementally
4. **Document Quality Rules**: Keep quality rules in version control
5. **Automate Monitoring**: Set up alerts for quality issues