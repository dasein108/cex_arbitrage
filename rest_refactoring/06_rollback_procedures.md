# Rollback Procedures and Production Safety

## Overview
Comprehensive rollback procedures for the REST to Client Injection conversion, ensuring production safety and rapid recovery in case of issues during or after implementation.

## Rollback Strategy Levels

### 🚨 Level 1: Emergency Complete Rollback
**Use Case**: Critical production issues, complete system failure
**Recovery Time**: <5 minutes
**Scope**: Revert entire conversion to previous working state

### ⚠️ Level 2: Phase-Specific Rollback  
**Use Case**: Issues with specific phase, partial functionality affected
**Recovery Time**: <15 minutes
**Scope**: Revert specific phases while preserving working components

### 🔧 Level 3: Component-Specific Rollback
**Use Case**: Issues with individual exchanges or components
**Recovery Time**: <30 minutes  
**Scope**: Revert specific exchange implementations

## Emergency Rollback Procedures

### Level 1: Complete System Rollback

#### Pre-Rollback Verification
```bash
# 1. Verify current system status
git status
git log --oneline -10

# 2. Check for uncommitted changes
git diff --name-only
git diff --cached --name-only

# 3. Backup current state (optional)
git stash push -m "Emergency backup before rollback $(date)"
```

#### Complete Rollback Commands
```bash
# EMERGENCY ROLLBACK - Restore to pre-conversion state

# 1. Identify conversion start commit
git log --oneline --grep="Phase 1" --grep="BaseRestInterface" --grep="client injection"

# 2. Complete rollback to last known good state
git reset --hard [COMMIT_BEFORE_CONVERSION]

# 3. Alternative: Revert specific conversion commits
git revert [PHASE_5_COMMIT] [PHASE_4_COMMIT] [PHASE_3_COMMIT] [PHASE_2_COMMIT] [PHASE_1_COMMIT]

# 4. Force update if needed (CAUTION: loses all conversion work)
git reset --hard HEAD~20  # Adjust number based on commits

# 5. Verify rollback successful
grep -r "create_rest_manager" src/exchanges/integrations/*/rest/*.py
# Should show async def create_rest_manager methods restored

grep -r "_ensure_rest_manager" src/exchanges/interfaces/rest/rest_base.py
# Should show lazy initialization restored
```

#### Post-Rollback Validation
```bash
# 1. Verify system functionality
python -m pytest tests/integration/ -v

# 2. Check critical files restored
ls -la src/exchanges/interfaces/rest/rest_base.py
grep -n "Optional\[RestManager\]" src/exchanges/interfaces/rest/rest_base.py

# 3. Verify factory function restored (if applicable)
grep -n "create_rest_transport_manager" src/infrastructure/networking/http/utils.py

# 4. Test one exchange implementation
python -c "
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
from config.structs import ExchangeConfig
config = ExchangeConfig(name='mexc', base_url='https://api.mexc.com')
rest = MexcPrivateSpotRest(config)
print('✅ MEXC REST client creation successful')
"
```

### Level 2: Phase-Specific Rollback

#### Phase 5 Rollback (Validation Issues)
```bash
# Rollback only validation additions - safe
git checkout HEAD~1 -- tests/integration/
git checkout HEAD~1 -- tests/performance/
# Core system remains intact
```

#### Phase 4 Rollback (Composite Integration Issues)
```bash
# Revert composite changes only
git checkout HEAD~3 -- src/exchanges/interfaces/composite/base_private_composite.py
git checkout HEAD~3 -- src/exchanges/integrations/mexc/mexc_composite_private.py
git checkout HEAD~3 -- src/exchanges/integrations/gateio/gateio_composite_private.py

# Verify rollback
grep -n "Optional\[RestT\]" src/exchanges/interfaces/composite/base_private_composite.py
# Should show Optional types restored
```

#### Phase 3 Rollback (Request Pipeline Issues)
```bash
# Restore lazy initialization in request method
git checkout HEAD~5 -- src/exchanges/interfaces/rest/rest_base.py

# Verify lazy initialization restored
grep -n "_ensure_rest_manager" src/exchanges/interfaces/rest/rest_base.py
# Should show method exists

grep -A 5 "async def request" src/exchanges/interfaces/rest/rest_base.py
# Should show await self._ensure_rest_manager() line
```

#### Phase 2 Rollback (Exchange Implementation Issues)
```bash
# Revert all exchange implementations
git checkout HEAD~10 -- src/exchanges/integrations/mexc/rest/
git checkout HEAD~10 -- src/exchanges/integrations/gateio/rest/

# Verify abstract methods restored
grep -r "async def create_rest_manager" src/exchanges/integrations/*/rest/*.py
# Should show multiple results

# Test one implementation
python -c "
import asyncio
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
async def test():
    config = ExchangeConfig(name='mexc', base_url='https://api.mexc.com')
    rest = MexcPrivateSpotRest(config)
    # Should have create_rest_manager method
    assert hasattr(rest, 'create_rest_manager')
    print('✅ Abstract method restored')
asyncio.run(test())
"
```

#### Phase 1 Rollback (BaseRestInterface Issues)
```bash
# Revert base interface changes
git checkout HEAD~15 -- src/exchanges/interfaces/rest/rest_base.py

# Verify abstract base class restored
grep -n "ABC" src/exchanges/interfaces/rest/rest_base.py
# Should show ABC inheritance

grep -n "abstractmethod" src/exchanges/interfaces/rest/rest_base.py
# Should show abstract create_rest_manager method
```

### Level 3: Component-Specific Rollback

#### Single Exchange Rollback
```bash
# Rollback specific exchange only
git checkout HEAD~5 -- src/exchanges/integrations/mexc/rest/mexc_rest_spot_private.py

# Or restore from working version
cp backups/mexc_rest_spot_private.py.backup src/exchanges/integrations/mexc/rest/mexc_rest_spot_private.py

# Verify specific implementation
python -c "
from exchanges.integrations.mexc.rest.mexc_rest_spot_private import MexcPrivateSpotRest
rest = MexcPrivateSpotRest.__dict__
assert 'create_rest_manager' in rest
print('✅ MEXC implementation restored')
"
```

#### Single Component Rollback
```bash
# Rollback specific component functionality
git checkout HEAD~2 -- src/exchanges/interfaces/composite/mixins/withdrawal_mixin.py

# Verify mixin functionality restored
python -c "
from exchanges.interfaces.composite.mixins.withdrawal_mixin import WithdrawalMixin
methods = dir(WithdrawalMixin)
print('✅ WithdrawalMixin methods:', [m for m in methods if not m.startswith('_')])
"
```

## Pre-Implementation Safety Measures

### Backup Creation
```bash
# Create comprehensive backup before starting conversion
mkdir -p backups/pre_conversion_$(date +%Y%m%d_%H%M%S)

# Backup critical files
cp -r src/exchanges/interfaces/rest/ backups/pre_conversion_*/
cp -r src/exchanges/integrations/mexc/rest/ backups/pre_conversion_*/
cp -r src/exchanges/integrations/gateio/rest/ backups/pre_conversion_*/
cp -r src/exchanges/interfaces/composite/ backups/pre_conversion_*/

# Backup configuration
cp -r src/infrastructure/networking/http/ backups/pre_conversion_*/

# Create git backup branch
git branch backup_pre_client_injection_$(date +%Y%m%d)
git checkout backup_pre_client_injection_$(date +%Y%m%d)
git add -A
git commit -m "Backup before client injection conversion $(date)"
git checkout main  # or original branch
```

### Testing Safety Net
```bash
# Create comprehensive test run before conversion
python -m pytest tests/ -v --tb=short > test_results_pre_conversion.log 2>&1

# Verify all tests pass
if [ $? -eq 0 ]; then
    echo "✅ All tests pass - safe to proceed with conversion"
else
    echo "❌ Tests failing - fix before conversion"
    exit 1
fi

# Performance baseline
python scripts/performance_benchmark.py > performance_baseline.log 2>&1
```

## Issue Detection and Monitoring

### Critical Issue Indicators

#### Performance Degradation Signs
```bash
# Monitor request latency
tail -f logs/application.log | grep "rest_base_request_duration_ms" | awk '{print $NF}' 

# Check for timeout errors
grep -c "timeout" logs/application.log

# Monitor memory usage
ps aux | grep python | awk '{print $6}' | sort -n | tail -1
```

#### Functional Issue Signs
```bash
# Check for authentication failures
grep -c "authentication failed" logs/application.log

# Monitor exchange connection errors
grep -c "connection refused\|connection timeout" logs/application.log

# Check for missing method errors
grep -c "AttributeError.*create_rest_manager\|AttributeError.*_ensure_rest_manager" logs/application.log
```

#### Type Safety Issue Signs
```bash
# Check for type errors
grep -c "TypeError\|AttributeError" logs/application.log

# Monitor None reference errors
grep -c "NoneType.*has no attribute" logs/application.log

# Check for import errors
grep -c "ImportError\|ModuleNotFoundError" logs/application.log
```

### Automated Monitoring Setup
```bash
# Create monitoring script
cat > monitor_conversion.sh << 'EOF'
#!/bin/bash

# Monitor critical metrics during conversion
while true; do
    echo "=== $(date) ==="
    
    # Check system health
    python -c "
import asyncio
from exchanges.integrations.mexc.mexc_composite_private import MexcPrivateComposite
from config.structs import ExchangeConfig

async def health_check():
    try:
        config = ExchangeConfig(name='mexc', base_url='https://api.mexc.com')
        composite = MexcPrivateComposite(config, None)
        print('✅ MEXC composite creation: OK')
        await composite.close()
    except Exception as e:
        print(f'❌ MEXC composite creation: FAILED - {e}')
        exit(1)

asyncio.run(health_check())
"
    
    # Check error rates
    error_count=$(grep -c "ERROR\|CRITICAL" logs/application.log)
    echo "Error count: $error_count"
    
    if [ $error_count -gt 10 ]; then
        echo "🚨 HIGH ERROR RATE DETECTED - CONSIDER ROLLBACK"
    fi
    
    sleep 30
done
EOF

chmod +x monitor_conversion.sh
```

## Rollback Validation Procedures

### Post-Rollback Health Check
```bash
# Comprehensive system validation after rollback
cat > validate_rollback.sh << 'EOF'
#!/bin/bash

echo "🔍 Validating rollback completion..."

# 1. Verify file structure restored
if grep -q "Optional\[RestManager\]" src/exchanges/interfaces/rest/rest_base.py; then
    echo "✅ BaseRestInterface lazy initialization restored"
else
    echo "❌ BaseRestInterface rollback incomplete"
    exit 1
fi

# 2. Verify abstract methods restored
if grep -r "async def create_rest_manager" src/exchanges/integrations/*/rest/*.py | wc -l | grep -q "6"; then
    echo "✅ Exchange abstract methods restored"
else
    echo "❌ Exchange abstract methods rollback incomplete"
    exit 1
fi

# 3. Test system functionality
python -m pytest tests/integration/test_mexc_integration.py -v
if [ $? -eq 0 ]; then
    echo "✅ MEXC integration tests pass"
else
    echo "❌ MEXC integration tests fail"
    exit 1
fi

# 4. Test performance baseline
python scripts/performance_test.py > rollback_performance.log
echo "✅ Performance test completed - check rollback_performance.log"

echo "🎉 Rollback validation complete - system restored"
EOF

chmod +x validate_rollback.sh
./validate_rollback.sh
```

### Rollback Documentation
```bash
# Document rollback actions taken
cat > rollback_report_$(date +%Y%m%d_%H%M%S).md << EOF
# Rollback Report - $(date)

## Issue Description
[Describe the issue that triggered rollback]

## Rollback Actions Taken
- [ ] Level 1 Complete Rollback
- [ ] Level 2 Phase-Specific Rollback (Phases: [X, Y, Z])
- [ ] Level 3 Component-Specific Rollback (Components: [A, B, C])

## Commands Executed
\`\`\`bash
[List exact git commands used]
\`\`\`

## Validation Results
- [ ] File structure restored
- [ ] Abstract methods present
- [ ] Integration tests pass
- [ ] Performance baseline met

## Root Cause Analysis
[Analysis of what went wrong and prevention measures]

## Next Steps
[Plan for re-attempting conversion or alternative approach]

## Lessons Learned
[Document insights for future conversions]
EOF
```

## Prevention and Risk Mitigation

### Pre-Conversion Checklist
- [ ] Complete backup created and verified
- [ ] All tests passing in current state
- [ ] Performance baseline established
- [ ] Rollback procedures tested on development environment
- [ ] Monitoring systems in place
- [ ] Team notified of conversion timeline
- [ ] Emergency contact procedures established

### Conversion Safety Guidelines
- [ ] Implement one phase at a time
- [ ] Validate each phase before proceeding
- [ ] Monitor system health continuously
- [ ] Maintain communication during conversion
- [ ] Keep rollback procedures immediately accessible
- [ ] Document any deviations from plan

### Post-Conversion Monitoring
- [ ] Monitor performance metrics for 24 hours
- [ ] Watch error logs for unusual patterns
- [ ] Validate trading operations functionality
- [ ] Confirm type safety compliance
- [ ] Verify memory usage stability

## Recovery Time Objectives

### Target Recovery Times
- **Level 1 Emergency Rollback**: <5 minutes
- **Level 2 Phase Rollback**: <15 minutes  
- **Level 3 Component Rollback**: <30 minutes
- **Full System Validation**: <60 minutes

### Communication Procedures
```bash
# Emergency notification template
cat > emergency_notification.txt << 'EOF'
🚨 EMERGENCY ROLLBACK INITIATED

System: HFT Arbitrage Engine
Component: REST Client Injection Conversion
Status: ROLLING BACK
Estimated Recovery: [X] minutes

Actions Taken:
- [List rollback actions]

Current Status:
- [System status]

Next Update: [Time]

Contact: [Emergency contact info]
EOF
```

**Risk Level**: Critical procedure - test thoroughly before implementation
**Dependencies**: Git version control, backup systems, monitoring infrastructure
**Maintenance**: Review and update procedures quarterly