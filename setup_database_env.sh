#!/bin/bash
# Database Environment Setup Script
# Sets the correct environment variables for connecting to the HFT arbitrage database

export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=arbitrage_data
export POSTGRES_USER=arbitrage_user
export POSTGRES_PASSWORD=dev_password_2024

echo "✅ Database environment variables set:"
echo "   POSTGRES_HOST: $POSTGRES_HOST"
echo "   POSTGRES_PORT: $POSTGRES_PORT"
echo "   POSTGRES_DB: $POSTGRES_DB" 
echo "   POSTGRES_USER: $POSTGRES_USER"
echo "   POSTGRES_PASSWORD: [SET]"
echo ""
echo "To use these settings in your shell session, run:"
echo "source setup_database_env.sh"
echo ""
echo "To run database operations demo:"
echo "python src/examples/demo/db_operations_demo.py"