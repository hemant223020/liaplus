# Database & Storage Optimization - PostgreSQL

This document outlines various optimization techniques for PostgreSQL databases to improve performance, reduce resource consumption, and enhance scalability.

## Performance Analysis

Before implementing optimizations, it's crucial to identify performance bottlenecks. Key metrics to analyze:

1. **Query performance**: Slow queries, frequent queries
2. **Index usage**: Missing or unused indexes
3. **Resource utilization**: CPU, memory, disk I/O
4. **Connection patterns**: Connection pooling effectiveness

## Optimization Techniques

### 1. Indexing Strategies

Proper indexing is the most impactful optimization for most database workloads.

#### Index Types and Use Cases

| Index Type | Best For | Considerations |
|------------|----------|----------------|
| B-tree (default) | Equality and range queries | Good all-purpose index |
| Hash | Equality comparisons only | Faster than B-tree for equality |
| GiST | Geometry, full-text search | Specialized use cases |
| GIN | Arrays, JSON, full-text | Slower to build, faster to search |
| BRIN | Large tables with ordered data | Very space efficient |

#### When to Create Indexes
- Columns used in WHERE clauses
- Columns used in JOIN conditions
- Columns used in ORDER BY and GROUP BY
- Foreign key columns

#### When to Avoid Indexes
- Small tables (sequential scan may be faster)
- Columns with low cardinality (few unique values)
- Columns that are frequently updated
- Tables that are primarily insert-heavy

#### Example: Creating Appropriate Indexes

```sql
-- Before optimization: Table without proper indexes
CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username VARCHAR(100),
  email VARCHAR(255),
  created_at TIMESTAMP,
  last_login TIMESTAMP,
  status VARCHAR(20),
  location_id INTEGER
);

-- Sample slow query without indexes
EXPLAIN ANALYZE
SELECT * FROM users 
WHERE email LIKE '%example.com' 
AND created_at > '2023-01-01';

-- Adding optimized indexes
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_created_at ON users(created_at);
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_location_id ON users(location_id);

-- For frequently joined tables
CREATE INDEX idx_users_location_id_email ON users(location_id, email);

-- After adding indexes, the query plan should show index scans instead of sequential scans
EXPLAIN ANALYZE
SELECT * FROM users 
WHERE email LIKE '%example.com' 
AND created_at > '2023-01-01';

-- Note: For pattern matching with LIKE that starts with wildcard ('%example'),
-- a full index scan is still needed. Consider using a trigram index for this case:
CREATE EXTENSION pg_trgm;
CREATE INDEX idx_users_email_trigram ON users USING gin (email gin_trgm_ops);

### 2. Query Optimization

Inefficient queries can significantly impact database performance. Here are some optimization techniques:

#### Example: Before and After Query Optimization

**Before Optimization:**
```sql
-- Inefficient query with subqueries and full table scans
SELECT u.username, u.email, 
  (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) as order_count,
  (SELECT SUM(amount) FROM payments p WHERE p.user_id = u.id) as total_spent
FROM users u
WHERE u.status = 'active';
```

Execution plan shows nested loops and sequential scans for each subquery execution.

**After Optimization:**
```sql
-- Optimized with JOINs and aggregation
SELECT u.username, u.email, 
  COUNT(o.id) as order_count,
  SUM(p.amount) as total_spent
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
LEFT JOIN payments p ON u.id = p.user_id
WHERE u.status = 'active'
GROUP BY u.id, u.username, u.email;
```

Execution plan shows better use of indexes and hash aggregation.

#### Additional Query Optimization Techniques:

1. **Use EXPLAIN ANALYZE** to understand query execution plans
2. **Limit result sets** with WHERE clauses and LIMIT
3. **Avoid SELECT *** when you only need specific columns
4. **Use appropriate JOINs** (INNER, LEFT, etc.) based on your data requirements
5. **Optimize subqueries** by rewriting as JOINs where possible
6. **Use Common Table Expressions (CTEs)** for better readability and optimization

### 3. Table Partitioning

For very large tables, partitioning can improve query performance and manageability.

```sql
-- Create a partitioned table by date range
CREATE TABLE metrics (
  id SERIAL,
  timestamp TIMESTAMP NOT NULL,
  device_id INTEGER,
  metric_value NUMERIC,
  metric_type VARCHAR(50)
) PARTITION BY RANGE (timestamp);

-- Create partitions by month
CREATE TABLE metrics_y2023m01 PARTITION OF metrics
  FOR VALUES FROM ('2023-01-01') TO ('2023-02-01');

CREATE TABLE metrics_y2023m02 PARTITION OF metrics
  FOR VALUES FROM ('2023-02-01') TO ('2023-03-01');

-- Queries accessing specific time ranges will only scan relevant partitions
EXPLAIN ANALYZE
SELECT * FROM metrics 
WHERE timestamp BETWEEN '2023-01-15' AND '2023-01-20';
```

### 4. Configuring PostgreSQL for Performance

Key configuration parameters to tune in `postgresql.conf`:

```ini
# Memory Configuration
shared_buffers = 4GB         # 25% of available RAM for dedicated servers
work_mem = 16MB              # Increase for complex sorts and joins
maintenance_work_mem = 512MB # Increase for VACUUM, CREATE INDEX, etc.

# Background Writer
bgwriter_delay = 200ms       # Background writer sleep time
bgwriter_lru_maxpages = 100  # Max pages to flush per round

# WAL Configuration
wal_buffers = 16MB           # Typically 1/32 of shared_buffers
checkpoint_timeout = 15min   # Time between checkpoints
max_wal_size = 2GB           # Maximum WAL size between checkpoints

# Planner Configuration
random_page_cost = 1.1       # Lower for SSD storage (default is 4.0)
effective_cache_size = 12GB  # Estimate of available OS cache (75% of RAM)

# Connection Pooling
max_connections = 100        # Keep this reasonable; use connection pooling
```

### 5. Data Partitioning Strategies

Different partitioning strategies suitable for different data patterns:

| Strategy | When to Use | Example |
|----------|-------------|---------|
| Range Partitioning | Time-series data, historical records | Partition by date ranges (months, years) |
| List Partitioning | Categorical data with distinct values | Partition by region, category, status |
| Hash Partitioning | Even distribution when no natural partitioning key exists | Useful for sharding data across multiple servers |

### 6. Connection Pooling

Connection pooling significantly improves performance for applications with many short-lived connections.

**Implementation with PgBouncer:**

```ini
# pgbouncer.ini configuration
[databases]
mydb = host=127.0.0.1 port=5432 dbname=mydb

[pgbouncer]
listen_addr = *
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
```

**Application Connection String Before:**
```
postgresql://user:password@localhost:5432/mydb
```

**Application Connection String After:**
```
postgresql://user:password@localhost:6432/mydb
```

## Before and After Optimization Examples

### Example 1: Complex Reporting Query

**Before Optimization:**
```sql
-- Slow reporting query without proper indexes
SELECT 
    date_trunc('day', o.created_at) as order_date,
    c.name as category_name,
    COUNT(o.id) as order_count,
    SUM(o.total_amount) as revenue
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
JOIN categories c ON p.category_id = c.id
WHERE o.created_at >= '2023-01-01'
GROUP BY order_date, category_name
ORDER BY order_date, revenue DESC;
```

**Execution Time:** 15.3 seconds  
**Execution Plan:** Sequential scans on orders, products tables, nested loops

**Optimization Applied:**
1. Added indexes: 
   ```sql
   CREATE INDEX idx_orders_created_at ON orders(created_at);
   CREATE INDEX idx_order_items_order_id ON order_items(order_id);
   CREATE INDEX idx_order_items_product_id ON order_items(product_id);
   CREATE INDEX idx_products_category_id ON products(category_id);
   ```
2. Partitioned orders table by month
3. Created a materialized view for frequently accessed reporting data:
   ```sql
   CREATE MATERIALIZED VIEW order_category_stats AS
   SELECT 
       date_trunc('day', o.created_at) as order_date,
       c.name as category_name,
       COUNT(o.id) as order_count,
       SUM(o.total_amount) as revenue
   FROM orders o
   JOIN order_items oi ON o.id = oi.order_id
   JOIN products p ON oi.product_id = p.id
   JOIN categories c ON p.category_id = c.id
   GROUP BY order_date, category_name;
   
   -- Create index on the materialized view
   CREATE INDEX idx_order_category_stats_dates ON order_category_stats(order_date);
   ```

**After Optimization:**
```sql
-- Query using the materialized view
SELECT * FROM order_category_stats
WHERE order_date >= '2023-01-01'
ORDER BY order_date, revenue DESC;
```

**Execution Time:** 0.12 seconds  
**Execution Plan:** Index scan on materialized view

### Example 2: User Authentication Query

**Before Optimization:**
```sql
-- Frequent user authentication query
SELECT id, username, password_hash, role, status 
FROM users
WHERE username = 'testuser@example.com' OR email = 'testuser@example.com';
```

**Execution Time:** 120ms (with millions of users)  
**Execution Plan:** Sequential scan on users table

**Optimization Applied:**
1. Added composite index:
   ```sql
   CREATE INDEX idx_users_username_email ON users(username, email);
   ```
2. Updated query to use a UNION:
   ```sql
   SELECT id, username, password_hash, role, status 
   FROM users
   WHERE username = 'testuser@example.com'
   UNION ALL
   SELECT id, username, password_hash, role, status 
   FROM users
   WHERE email = 'testuser@example.com'
   AND username != 'testuser@example.com'
   LIMIT 1;
   ```

**Execution Time:** 5ms  
**Execution Plan:** Index scans with early limit

## Conclusion

Database optimization is an iterative process that should be based on performance data and actual workload patterns. The techniques outlined above can dramatically improve PostgreSQL performance, but should be applied selectively based on your specific requirements and data access patterns.

Key recommendations:
1. Start with proper indexing - the most impactful for most workloads
2. Optimize queries to use those indexes effectively
3. Consider partitioning for very large tables
4. Tune PostgreSQL configuration based on available resources
5. Implement connection pooling for multi-user applications
6. Use materialized views for complex reporting queries
7. Regularly maintain the database (VACUUM, ANALYZE, etc.)

By implementing these optimization techniques, you can ensure your PostgreSQL database performs efficiently even as your data and user load grows.