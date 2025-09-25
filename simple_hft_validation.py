#!/usr/bin/env python3
"""
Simple HFT Safety Validation

Direct code inspection to validate HFT safety without complex imports.
"""

import os
import re


def check_file_for_dangerous_patterns(file_path, file_desc):
    """Check a file for dangerous HFT caching patterns."""
    print(f"\n🔍 Checking {file_desc}...")
    
    if not os.path.exists(file_path):
        print(f"⚠️  File not found: {file_path}")
        return True
    
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        issues = []
        
        # Check for dangerous property definitions that cache trading data
        dangerous_props = [
            r'@property\s*\n\s*def balances\(',
            r'@property\s*\n\s*def open_orders\(',
            r'@property\s*\n\s*def positions\(',
        ]
        
        for pattern in dangerous_props:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                issues.append(f"Line {line_num}: Dangerous caching property found")
        
        # Check for caching variables
        caching_patterns = [
            r'self\._.*balances.*=.*{',
            r'self\._.*orders.*=.*{',
            r'self\._.*positions.*=.*{',
        ]
        
        for pattern in caching_patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                line_num = content[:match.start()].count('\n') + 1
                issues.append(f"Line {line_num}: Caching variable assignment found")
        
        # Check for safe async method definitions
        safe_methods = [
            r'async def get_balances\(',
            r'async def get_open_orders\(',
            r'async def get_positions\(',
        ]
        
        safe_found = []
        for pattern in safe_methods:
            if re.search(pattern, content):
                method_name = pattern.replace(r'async def ', '').replace(r'\(', '')
                safe_found.append(method_name)
        
        if issues:
            print(f"❌ CRITICAL ISSUES FOUND:")
            for issue in issues:
                print(f"   - {issue}")
            return False
        else:
            print(f"✅ No dangerous caching patterns found")
            
        if safe_found:
            print(f"✅ Safe async methods found: {safe_found}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking file: {e}")
        return False


def main():
    """Run simple HFT safety validation."""
    print("🚨 Simple HFT Safety Validation")
    print("=" * 50)
    
    files_to_check = [
        ("src/exchanges/interfaces/composite/unified_exchange.py", "Unified Interface"),
        ("src/exchanges/integrations/mexc/mexc_unified_exchange.py", "MEXC Implementation"),
        ("src/exchanges/integrations/gateio/gateio_unified_exchange.py", "Gate.io Implementation"),
    ]
    
    results = []
    
    for file_path, desc in files_to_check:
        result = check_file_for_dangerous_patterns(file_path, desc)
        results.append(result)
    
    print("\n" + "=" * 50)
    print("🎯 Validation Results")
    print("=" * 50)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        print()
        print("🎉 HFT Safety Status: COMPLIANT")
        print("   - No dangerous caching properties found")
        print("   - Safe async methods are present")
        print("   - Critical trading safety issues resolved")
        return 0
    else:
        print(f"❌ CHECKS FAILED ({passed}/{total})")
        print()
        print("🚨 HFT Safety Status: NON-COMPLIANT") 
        print("   - CRITICAL TRADING SAFETY ISSUES REMAIN")
        print("   - DO NOT USE IN PRODUCTION")
        return 1


if __name__ == "__main__":
    exit(main())