# Asset Transfer Demo - MEXC to Gate.io

Complete demonstration of cross-exchange asset transfers using the AssetTransferModule.

## Features

- ✅ **Complete Transfer Lifecycle**: From validation to completion tracking
- ✅ **Real-time Monitoring**: 30-second interval status checks with timeout protection  
- ✅ **Comprehensive Validation**: Balance, network, and limit checks before execution
- ✅ **Balance Verification**: Pre/post transfer balance comparison
- ✅ **Error Handling**: Robust error handling with cleanup
- ✅ **Dry Run Mode**: Validation-only mode for testing
- ✅ **Detailed Logging**: Step-by-step progress with emoji indicators

## Prerequisites

1. **Exchange API Credentials**: MEXC and Gate.io API keys configured
2. **Asset Balance**: Sufficient balance on MEXC for the transfer amount
3. **Network Configuration**: Ensure both exchanges support common networks for the asset

## Usage

### Basic Transfer
```bash
# Transfer 10 USDT from MEXC to Gate.io
python src/examples/demo/asset_transfer_demo.py --asset USDT --amount 10.0
```

### Dry Run (Validation Only)
```bash
# Validate transfer requirements without executing
python src/examples/demo/asset_transfer_demo.py --asset USDT --amount 100.0 --dry-run
```

### Custom Asset Transfer
```bash
# Transfer 0.01 BTC
python src/examples/demo/asset_transfer_demo.py --asset BTC --amount 0.01

# Transfer 1000 USDC
python src/examples/demo/asset_transfer_demo.py --asset USDC --amount 1000.0
```

## Command Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--asset` | string | `USDT` | Asset to transfer |
| `--amount` | float | `10.0` | Amount to transfer |
| `--dry-run` | flag | `false` | Validation only, no execution |

## Transfer Process

### 1. **Initialization Phase**
- Initialize MEXC and Gate.io exchange connections
- Test connectivity by fetching account balances
- Create AssetTransferModule instance

### 2. **Validation Phase**
- Check sufficient balance on MEXC
- Verify withdrawal enabled on MEXC
- Verify deposits enabled on Gate.io
- Find common networks between exchanges
- Validate transfer amount against network limits
- Display optimal network selection with fees

### 3. **Execution Phase**
- Record pre-transfer balances
- Execute transfer using AssetTransferModule
- Get transfer ID and transaction ID
- Log estimated fees and status

### 4. **Monitoring Phase**
- Monitor transfer status every 30 seconds
- Display detailed withdrawal status
- Handle timeout (30 minutes default)
- Track elapsed time

### 5. **Verification Phase**
- Compare pre/post transfer balances
- Verify expected balance changes
- Account for withdrawal fees
- Confirm successful completion

### 6. **Cleanup Phase**
- Close exchange connections
- Clean up resources
- Exit with appropriate status code

## Example Output

```
================================================================================
🎯 Asset Transfer Demo - MEXC to Gate.io
================================================================================
Asset: USDT
Amount: 10.0
From: MEXC
To: Gate.io
================================================================================
🚀 Initializing exchange connections...
✅ Exchange connections initialized successfully
🔍 Testing exchange connectivity...
✅ MEXC: Connected (8 assets with balance)
✅ GATEIO: Connected (12 assets with balance)
💰 Checking USDT balances...
  MEXC: 150.25000000 USDT
  GATEIO: 75.50000000 USDT
🔍 Validating transfer requirements for 10.0 USDT...
✅ Found 2 valid networks:
  TRC20: fee=1.0, min=5.0, max=None
  ERC20: fee=5.0, min=10.0, max=None
🚀 Starting transfer: 10.0 USDT from MEXC to Gate.io...
✅ Transfer initiated successfully!
  Transfer ID: USDT_MEXC_GATEIO_1729567890
  Transaction ID: 1234567890abcdef
  Estimated Fee: 1.0 USDT
  Initiated: True
👀 Monitoring transfer 1234567890abcdef...
⏳ Transfer status: PENDING
⏱️  Elapsed: 0.5 minutes, checking again in 30 seconds...
⏳ Transfer status: PROCESSING
⏱️  Elapsed: 1.0 minutes, checking again in 30 seconds...
✅ Transfer completed successfully!
🔍 Verifying transfer completion...
💰 Balance changes:
  MEXC: -11.00000000 USDT
  GATEIO: +10.00000000 USDT
✅ Transfer verified! Balances updated correctly
🎉 Asset transfer demo completed successfully!
```

## Error Scenarios

### Insufficient Balance
```
❌ Insufficient USDT balance on MEXC: 5.0 < 10.0
❌ Transfer requirements not met. Aborting.
```

### Withdrawals Disabled
```
❌ USDT withdrawals disabled on MEXC
❌ Transfer requirements not met. Aborting.
```

### No Common Networks
```
❌ No common networks between MEXC and Gate.io for BTC
  MEXC networks: {'BTC', 'BEP20'}
  Gate.io networks: {'BTC', 'ERC20'}
❌ Transfer requirements not met. Aborting.
```

### Transfer Timeout
```
⏰ Transfer monitoring timed out after 30 minutes
❌ Transfer did not complete within timeout
```

## Configuration

The demo uses the HftConfig system to load exchange configurations:

```python
# Loads from config files with environment variable substitution
mexc_config = config_manager.get_exchange_config("mexc_spot")
gateio_config = config_manager.get_exchange_config("gateio_spot")
```

Ensure your configuration files have valid API credentials:
- `config/exchanges/mexc.yaml`
- `config/exchanges/gateio.yaml`

## Security Notes

- API credentials are loaded from secure configuration files
- No sensitive data is logged
- Withdrawal transactions are properly authenticated
- All connections use secure HTTPS/WSS protocols

## Troubleshooting

### Connection Issues
- Verify API credentials are correct
- Check network connectivity
- Ensure API permissions include trading/withdrawal rights

### Transfer Failures
- Check asset withdrawal/deposit status on exchanges
- Verify network availability
- Ensure sufficient balance including fees
- Check transfer limits on both exchanges

### Monitoring Issues
- Network delays may cause status update delays
- Some exchanges have different confirmation requirements
- Manual verification via exchange web interfaces may be needed

## Integration with Trading Strategies

This demo shows how to integrate the AssetTransferModule into trading strategies:

```python
# Initialize transfer module
transfer_module = AssetTransferModule(exchanges)

# Execute transfer as part of arbitrage strategy
transfer_request = await transfer_module.transfer_asset(
    asset=AssetName("USDT"),
    from_exchange=ExchangeEnum.MEXC,
    to_exchange=ExchangeEnum.GATEIO,
    amount=rebalance_amount
)

# Monitor transfer completion
while not await transfer_module.update_transfer_status(transfer_request.transfer_id):
    await asyncio.sleep(30)

# Continue with trading strategy
```