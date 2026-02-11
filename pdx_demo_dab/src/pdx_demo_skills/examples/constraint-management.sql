-- Managing Delta Lake CHECK constraints for data quality

-- Example 1: Add email validation constraint
ALTER TABLE catalog.schema.users
ADD CONSTRAINT valid_email CHECK (email LIKE '%@%.%');

-- Example 2: Add positive amount constraint
ALTER TABLE catalog.schema.transactions
ADD CONSTRAINT positive_amount CHECK (amount > 0);

-- Example 3: Add date range constraint
ALTER TABLE catalog.schema.events
ADD CONSTRAINT valid_date CHECK (event_date <= current_date());

-- Example 4: Add status validation constraint
ALTER TABLE catalog.schema.orders
ADD CONSTRAINT valid_status 
CHECK (status IN ('pending', 'processing', 'completed', 'cancelled'));

-- Example 5: Add age range constraint
ALTER TABLE catalog.schema.customers
ADD CONSTRAINT valid_age CHECK (age >= 0 AND age <= 120);

-- View existing constraints on a table
SHOW TBLPROPERTIES catalog.schema.table;

-- Drop a constraint if needed
ALTER TABLE catalog.schema.table
DROP CONSTRAINT constraint_name;