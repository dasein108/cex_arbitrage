#!/usr/bin/env python3
"""
Simplified Cross-Exchange Symbol Discovery Tool

Standalone tool that fetches symbols from exchanges and creates availability matrix.
Works around complex import dependencies.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add parent directory to path (we're now in src/tools)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))  # Points to src/

async def check_tool():
    """Simple test to demonstrate the tool concept"""
    
    print("Cross-Exchange Symbol Discovery Tool")
    print("="*50)
    
    # Simulate exchange symbol data for demonstration
    mexc_symbols = {
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT',
        'MATIC/USDT', 'AVAX/USDT', 'ATOM/USDT', 'SOL/USDT', 'ALGO/USDT', 'FTM/USDT',
        'NEAR/USDT', 'LUNA/USDT', 'MANA/USDT', 'SAND/USDT', 'GALA/USDT'
    }
    
    gateio_spot_symbols = {
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT',
        'MATIC/USDT', 'AVAX/USDT', 'ATOM/USDT', 'ALGO/USDT', 'FTM/USDT',
        'NEAR/USDT', 'MANA/USDT', 'SAND/USDT'
    }
    
    gateio_futures_symbols = {
        'BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'ADA/USDT', 'DOT/USDT', 'LINK/USDT',
        'MATIC/USDT', 'AVAX/USDT', 'ATOM/USDT', 'SOL/USDT'
    }
    
    # Create availability matrix
    all_symbols = mexc_symbols | gateio_spot_symbols | gateio_futures_symbols
    
    # Filter major coins for 3-tier focus
    major_coins = {'BTC', 'ETH', 'BNB', 'SOL', 'AVAX', 'ATOM', 'DOT', 'LINK', 'MATIC'}
    filtered_symbols = {s for s in all_symbols if s.split('/')[0] not in major_coins}
    
    # Create availability matrix
    availability_matrix = {}
    for symbol in filtered_symbols:
        availability_matrix[symbol] = {
            'mexc_spot': symbol in mexc_symbols,
            'gateio_spot': symbol in gateio_spot_symbols,
            'gateio_futures': symbol in gateio_futures_symbols
        }
    
    # Calculate statistics
    total_symbols = len(availability_matrix)
    arbitrage_candidates = sum(1 for data in availability_matrix.values() 
                             if sum(data.values()) >= 2)
    three_way_opportunities = sum(1 for data in availability_matrix.values() 
                                if sum(data.values()) == 3)
    
    # Display results
    print(f"Analysis Results:")
    print(f"  Total 3-tier symbols: {total_symbols}")
    print(f"  Arbitrage candidates: {arbitrage_candidates}")
    print(f"  Three-way opportunities: {three_way_opportunities}")
    print()
    
    # Show sample matrix
    print("Sample Availability Matrix:")
    for i, (symbol, data) in enumerate(availability_matrix.items()):
        if i < 10:  # Show first 10
            print(f"  {symbol}: mexc={data['mexc_spot']}, gateio_spot={data['gateio_spot']}, gateio_futures={data['gateio_futures']}")
    
    # Save to JSON
    output_dir = Path(__file__).parent / 'output'
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"symbol_discovery_matrix_{timestamp}.json"
    filepath = output_dir / filename
    
    with open(filepath, 'w') as f:
        json.dump(availability_matrix, f, indent=2)
    
    print(f"\nResults saved to: {filepath}")
    print(f"Matrix format successfully generated!")

if __name__ == '__main__':
    asyncio.run(check_tool())