-- analytics.sql
-- How downstream teams query the unified model. Runs on the DuckDB warehouse:
--   duckdb output/mal.duckdb < queries/analytics.sql
-- Every query hits ONE table (payment_events) regardless of source squad,
-- which is the entire point of the canonical model.

-- 1. Daily payment volume + value by payment type (the cross-product view that
--    was impossible before unification, since each squad had its own table).
SELECT
    CAST(event_timestamp AS DATE) AS event_date,
    payment_type,
    COUNT(*)                      AS num_payments,
    SUM(amount)                   AS total_amount,
    SUM(fee_amount)               AS total_fees
FROM payment_events
WHERE status = 'completed'
GROUP BY 1, 2
ORDER BY 1, 2;

-- 2. Success rate by source system (a core platform health / DQ metric).
SELECT
    source_system,
    COUNT(*)                                                          AS total,
    COUNT(*) FILTER (WHERE status = 'completed')                      AS completed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'completed')
          / COUNT(*), 1)                                             AS success_pct
FROM payment_events
GROUP BY source_system
ORDER BY success_pct DESC;

-- 3. Customer 360: total spend across ALL products for each customer.
SELECT
    customer_id,
    COUNT(*)                                              AS payments,
    SUM(amount) FILTER (WHERE status = 'completed')       AS total_completed_value,
    COUNT(DISTINCT payment_type)                          AS products_used
FROM payment_events
GROUP BY customer_id
ORDER BY total_completed_value DESC NULLS LAST
LIMIT 10;

-- 4. Currency mix (matters for a UAE neobank doing AED + FX).
SELECT currency,
       COUNT(*)    AS payments,
       SUM(amount) AS total_amount
FROM payment_events
WHERE status = 'completed'
GROUP BY currency
ORDER BY total_amount DESC;

-- 5. Shariah-compliance audit: flag any non-compliant completed payments.
SELECT source_system, payment_type, COUNT(*) AS non_compliant
FROM payment_events
WHERE is_shariah_compliant = FALSE AND status = 'completed'
GROUP BY 1, 2;

-- 6. Failed / reversed payments for ops follow-up.
SELECT source_event_id, source_system, payment_type, amount, status
FROM payment_events
WHERE status IN ('failed', 'reversed')
ORDER BY amount DESC;
