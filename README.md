# Multi-Symbol Smart ATR Grid Trading Bot

A production-quality Python application for MetaTrader 5 that runs an ATR-based pending-order grid strategy on one or more independently configured symbols.

## Architecture

```
smart_grid_bot/
├── main.py                  # Entry point and event loop
├── config/                  # Configuration models, loader, setup wizard
├── mt5_client/              # MT5 connection, account, market data, orders, positions
├── strategy/                # ATR, grid builder, target calculator, cycle manager, state machine
├── models/                  # Data models and enums
├── services/                # Symbol manager, commission, persistence, recovery
├── dashboard/               # Live terminal dashboard
├── utils/                   # Logger, price/volume helpers, retry, console I/O
├── data/                    # SQLite database, saved defaults
├── logs/                    # Rotating log files
└── tests/                   # pytest unit tests
```

## System Requirements

- Windows 10/11 with MetaTrader 5 installed
- Python 3.11 or later
- MetaTrader 5 Hedging account (not Netting)
- Python MetaTrader5 package

## Installation

```bash
pip install -r requirements.txt
```

### MetaTrader 5 Setup

1. Install MetaTrader 5 from your broker.
2. Log in to your Hedging account.
3. Enable automated trading in MT5 (Tools > Options > Expert Advisors).
4. Ensure symbols you want to trade are visible in Market Watch.

### Environment Variables (Optional)

Copy `.env.example` to `.env` and fill in:

```
MT5_LOGIN=12345678
MT5_SERVER=Broker-Demo
MT5_PASSWORD=your_password
MT5_TERMINAL_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
```

Leave these empty if you want to use an already-authenticated terminal session.

## Hedging Account Requirement

This strategy requires an MT5 Hedging account (not Netting). At startup the application checks the account margin mode. If the account uses Netting mode, a clear error is printed and no orders are sent.

## Usage

### First Run

```bash
python main.py
```

The interactive setup wizard will:
1. Connect to MT5.
2. Ask you to select symbols.
3. Configure grid parameters per symbol.
4. Validate every value.
5. Save as defaults for future runs.

### Later Runs

```bash
python main.py
```

A configuration menu lets you:
1. Run with saved settings.
2. Edit temporarily for this run only.
3. Edit and save as new defaults.
4. Create a completely new configuration.
5. Exit safely.

### Dry Run Mode

```bash
python main.py --dry-run
```

Calculates ATR, builds grids, calculates target prices, and shows the dashboard without sending any real orders.

### Skip Confirmation

```bash
python main.py --yes
```

Skips the final live-trading confirmation. Requires valid saved defaults.

### Custom Configuration

```bash
python main.py --config my_config.yaml
```

## How the Strategy Works

### Cycle Flow

1. **Read prices**: Get current Bid and Ask, calculate anchor = (bid + ask) / 2.
2. **Calculate ATR**: Download closed candles, apply Wilder smoothing.
3. **Build grid**: Place Buy Stop orders above anchor and Sell Stop orders below anchor at ATR/grid_count intervals.
4. **Monitor**: Wait for orders to fill as open positions.
5. **Set basket TP**: When positions are active, dynamically calculate a target price for the whole basket and assign it to one trigger position.
6. **Target hit**: When the trigger position reaches TP, cancel all remaining pending orders, close all positions, record results, start next cycle.
7. **All grids filled**: If every grid order becomes a position, close everything and start the next cycle without waiting for TP.

### Key Design Decisions

- **No maximum loss**: The strategy intentionally has no max-loss or stop-loss rule.
- **Equal Buy/Sell exposure**: When Buy and Sell volumes are equal, no target exists and positions remain open until a new order creates net exposure.
- **Commission model**: Configured commission per position is the total round-turn cost (open + close). Swap is treated as zero.
- **Dynamic target**: Basket target price is recalculated numerically from actual position data using `order_calc_profit` whenever the position set changes.

## Dashboard

The live terminal dashboard shows:

- Account: Login, Server, Currency, Balance, Equity, Margin, Free Margin, Margin Level
- PnL: Gross floating PnL, estimated commission, estimated net PnL, realized PnL
- Runtime and connection status
- Per-symbol: State, Cycle, Bid, Ask, Buy/Sell positions, PnL, Target

Uses Rich library when available with a plain-text fallback.

## Database

SQLite database at `data/bot.db` stores:

- Application runs
- Cycles with all parameters and results
- Orders with fill/cancel timestamps
- Positions with open/close prices and PnL
- Events for audit trail
- Saved configuration history

## Logging

Rotating log files at `logs/trading.log` with structured fields:

timestamp, level, symbol, magic, cycle, grid, state, event, prices, PnL, retcode, errors

## Startup Recovery

On restart, the application:
1. Reads existing MT5 orders and positions.
2. Groups them by symbol and cycle number using the C{i}_{j} comment format.
3. Restores state and continues monitoring without creating duplicate grids.

If multiple active cycles are found for one symbol, that symbol is set to ERROR and excluded from trading.

## Safe Shutdown

Press Ctrl+C to stop. Default behavior: leave all existing positions and orders unchanged. No automatic position closure occurs on shutdown unless configured otherwise.

## Running Tests

```bash
pytest tests/ -v
```

## Configuration Structure

```yaml
application:
  polling_interval_seconds: 0.25
  dashboard_refresh_seconds: 1.0
  dry_run: false
  console_mode: rich
  log_level: INFO
  shutdown_mode: leave_open

mt5:
  terminal_path: null
  deviation_points: 20
  request_timeout_seconds: 10

symbols:
  - name: XAUUSD
    enabled: true
    grid_count: 5
    lot_size: 0.01
    atr_timeframe: M5
    atr_period: 14
    commission_per_position: 0.14
    target_profit: 10.0
    magic_number: 710001
```

## Common MT5 Retcodes

| Retcode | Meaning |
|---------|---------|
| 10009 | Done |
| 10010 | Done (partial) |
| 10011 | Rejected |
| 10012 | Cancelled |
| 10013 | Not enough money |
| 10014 | Price changed |
| 10015 | Off quotes |
| 10016 | Broker busy |
| 10017 | Invalid price |
| 10018 | Invalid stops |
| 10019 | Trade is disabled |
| 10020 | Market is closed |
| 10021 | No connection |

## Risks

- **Grid trading amplifies losses** in trending markets.
- **No maximum-loss rule** is implemented. Losses can accumulate beyond the configured account size.
- **Broker margin requirements** may prevent grid placement during high volatility.
- **Always test on a Demo account** before using real funds.
- This bot does not guarantee profitability.

## License

For personal and educational use only. Use at your own risk.
