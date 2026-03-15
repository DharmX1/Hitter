# AutoHitter Telegram Bot

## Overview
A Telegram bot for parsing Stripe checkout URLs and processing card transactions with enhanced efficiency and automatic 3DS bypass. Features a premium key system for access control.

## Project Structure
```
/
├── bot.py              # Main entry point
├── config.py           # Configuration (uses environment variables)
├── commands/
│   ├── __init__.py     # Router setup
│   ├── start.py        # /start and /help commands
│   ├── co.py           # Checkout and charge commands
│   └── premium.py      # Premium key management commands
├── functions/
│   ├── __init__.py     # Exports all functions
│   ├── session.py      # Shared aiohttp session
│   ├── card_utils.py   # Card parsing utilities
│   ├── checkout.py     # Stripe checkout parsing
│   ├── charge.py       # Card charging logic (optimized)
│   ├── proxy.py        # Proxy management
│   ├── premium.py      # Premium key logic
│   └── fonts.py        # Unicode font utilities
├── proxies.json        # Per-user proxy storage (auto-created)
├── premium_keys.json   # Generated keys storage (auto-created)
└── premium_users.json  # Premium users storage (auto-created)
```

## Environment Variables
- `BOT_TOKEN` - **Required** - Telegram bot token from @BotFather
- `ALLOWED_GROUP` - Optional - Telegram group ID for access (default: -1002361694932)
- `OWNER_IDS` - Optional - Comma-separated owner user IDs (default: 7593550190,5927846778,7714896632)

## Commands
| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Help text |
| `/co url` | Parse Stripe checkout URL (Premium) |
| `/co url cc\|mm\|yy\|cvv` | Charge card (Premium) |
| `/co cc\|mm\|yy\|cvv` | Retry with saved session (Premium) |
| `/session` | View saved checkout session status |
| `/addproxy` | Add/view proxies |
| `/removeproxy` | Remove proxy |
| `/proxy check` | Check all user proxies |

### Premium Commands
| Command | Description |
|---------|-------------|
| `/key` | Check your premium status |
| `/redeem KEY` | Redeem a premium key |
| `/genkey 7d` | Generate key (Owner only) |
| `/keys` | List all keys and premium users (Owner only) |
| `/revoke user_id` | Revoke user's premium (Owner only) |
| `/delkey KEY` | Delete unused key (Owner only) |

## Running the Bot
```bash
python bot.py
```

## Features
- **Premium Key System** - Time-based keys (1d, 7d, 30d) for access control
- **Automatic 3DS bypass** - All checkouts use bypass by default
- **Concurrent charging** - Up to 3 cards processed in parallel
- **Session pooling** - Faster requests with connection reuse
- **Stop on charge** - Stops processing when a card is charged
- **Multiple bypass techniques** - Standard, return_url, frictionless, challenge modes
- **Session memory** - Remembers last checkout URL per user for 5 minutes
- **Inline buttons** - Retry, New Card, Clear Session buttons after results
- **Progress bar** - Live progress display when processing multiple cards
- **Auto card formatting** - Fixes common card format mistakes (spaces, wrong separators)
- **Screenshot capture** - Takes screenshot of checkout page on successful charge
- **Premium UI** - Dual-font formatting with bold labels and monospace values

## UI Formatting
The bot uses a premium dual-font formatting style:
- **Bold Unicode** for labels (𝗟𝗮𝗯𝗲𝗹)
- **Monospace Unicode** for values (𝙼𝙾𝙽𝙾 𝚅𝙰𝙻𝚄𝙴)
- **Code blocks** for copyable content like cards

Format pattern: `[⌯] 𝗕𝗼𝗹𝗱𝗟𝗮𝗯𝗲𝗹 ⌁ 𝙼𝚘𝚗𝚘𝚅𝚊𝚕𝚞𝚎`

## Production Features (Jan 2026)
- **Rate Limiting** - Throttling middleware prevents abuse (10 requests per 10 seconds per user)
- **Global Error Handler** - Catches all unhandled exceptions and displays user-friendly messages
- **Chromium Path Fallback** - Automatic detection of system Chromium with multiple fallback paths
- **Thread-safe File Storage** - JSON storage uses threading.Lock for concurrent access safety
- **Atomic File Writes** - Uses temp files and os.replace() to prevent data corruption
- **Connection Pooling** - Efficient aiohttp session management with 100 connection limit
- **Graceful Shutdown** - Proper cleanup of sessions and resources on exit

## Recent Changes (Jan 2026)
- Added premium key system with time-based expiry (1d, 7d, 30d)
- Added /genkey, /redeem, /key, /keys, /revoke, /delkey commands
- Premium users can access /co, owners have unlimited access
- Premium dual-font UI formatting throughout
- Card numbers displayed in monospace `<code>` for easy copying
- Added inline buttons (Retry, New Card, Clear Session) after charge results
- Added /session command to view saved checkout status
- Added live progress bar for multi-card processing
- Added auto card formatting to fix common mistakes
- Session memory with 5-minute auto-expiration
