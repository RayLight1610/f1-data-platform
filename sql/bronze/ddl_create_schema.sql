-- Create Medallion architecture schemas
-- Run as postgres superuser (or any user with CREATE privilege on database)

CREATE SCHEMA IF NOT EXISTS bronze;
CREATE SCHEMA IF NOT EXISTS silver;
CREATE SCHEMA IF NOT EXISTS gold;

-- Grant privileges to application user
GRANT ALL ON SCHEMA bronze TO f1_app;
GRANT ALL ON SCHEMA silver TO f1_app;
GRANT ALL ON SCHEMA gold TO f1_app;