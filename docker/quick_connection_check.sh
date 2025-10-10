#!/bin/bash
# Quick connection check for HFT trading system
docker exec arbitrage_db psql -U arbitrage_user -d arbitrage_data -c "
SELECT 
    COUNT(*) as current_connections,
    (SELECT setting::int FROM pg_settings WHERE name = \"max_connections\") as max_connections,
    ROUND((COUNT(*)::numeric / (SELECT setting::int FROM pg_settings WHERE name = \"max_connections\")) * 100, 2) as usage_percentage
FROM pg_stat_activity;
"
