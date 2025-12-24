# Tyl Bot - Military Logistics Assistant

A Telegram bot designed to assist Ukrainian military personnel with logistics and supply chain questions. The bot provides answers based on official regulatory documents for three main service areas: fuel and lubricants (PMM), food supply, and material supply.

## Features

- **Service Assistance**: Get answers to questions about three main logistics services:
  - PMM (Fuel and Lubricants)
  - Food Supply
  - Material Supply

- **AI-Powered Responses**: Uses OpenAI Assistants API to provide accurate answers based on official documents

- **Payment System**: Integrated Monobank payment processing for balance top-ups
  - Automatic payment detection
  - Balance updates in real-time
  - Payment notifications

- **User Management**: 
  - User registration and tracking
  - Balance management
  - Usage statistics
  - Account blocking/unblocking

- **Operator Panel**: Administrative interface for:
  - User management
  - Balance adjustments
  - User search and profile viewing
  - Account blocking/unblocking

- **Rate Limiting**: Protection against abuse with configurable rate limits

- **Thread Management**: Maintains conversation context using OpenAI threads

## Requirements

- Python 3.8+
- Telegram Bot Token
- OpenAI API Key with Assistant IDs
- Monobank API Token (optional, for payment processing)

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd tyl_bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create a `.env` file based on `config_example.txt`:
```bash
cp config_example.txt .env
```


## Configuration

### Telegram Bot Token
Get your bot token from [@BotFather](https://t.me/BotFather) on Telegram.

### OpenAI Configuration
1. Create an OpenAI account and get your API key
2. Create three assistants in OpenAI (one for each service)
3. Add the Assistant IDs to your `.env` file

### Monobank API Token
1. Get a Monobank API token from their personal account
2. Add it to your `.env` file
3. Set the card number for receiving payments

### Group Chat ID
Set the Telegram group chat ID where notifications will be sent (new users, payments, errors).

### Operator ID
The operator ID is hardcoded in `operator_menu.py`. Change `OPERATOR_ID` to your Telegram user ID.

## Database

The bot uses SQLite database (`users.db`) to store:
- User information (Telegram ID, username, name)
- Balance and payment history
- Usage statistics
- Account status (blocked/active)

The database is automatically initialized on first run.

## Usage

### Starting the Bot

Run the bot:
```bash
python bot.py
```

The bot will:
- Initialize the database
- Start the payment checker (if Monobank token is configured)
- Begin polling for Telegram messages

### User Commands

- `/start` - Start the bot and see the main menu
- `/help` - Get help information
- `/cancel` - Cancel current action and return to main menu

### Main Menu Options

- **Services** - Choose a service (PMM, Food, Material Supply)
- **Top Up** - Get payment instructions to top up balance
- **Balance** - Check current balance and account information
- **Statistics** - View usage statistics
- **About Bot** - Information about the bot and how to use it
- **Operator** - Contact operator information

### Payment Process

1. User selects "Top Up" from the main menu
2. Bot provides payment instructions with card number
3. User makes payment via Monobank with their username or Telegram ID in the comment
4. Bot automatically detects payment and updates balance
5. User receives confirmation message

### Operator Panel

Operators can:
- View list of all users (paginated)
- Search users by username or Telegram ID
- View user profiles with detailed information
- Add or subtract balance
- Block or unblock user accounts

## Project Structure

```
tyl_bot/
├── bot.py                      # Main bot file with handlers and FSM states
├── db.py                       # Database operations with connection pooling
├── openai_service.py           # OpenAI API integration and thread management
├── monobank_payments.py        # Payment processing and automatic balance updates
├── operator_menu.py            # Operator panel with user management
├── rate_limiter.py             # Rate limiting implementation
├── ux_improvements.py          # UX formatting functions and message templates
├── additional_improvements.py  # Additional utilities (locks, cache, deduction tracker)
├── requirements.txt            # Python dependencies
├── config_example.txt          # Configuration template
├── README.md                   # This file
├── .gitignore                  # Git ignore rules
└── users.db                    # SQLite database (created automatically)
```

### File Descriptions

- **bot.py**: Main entry point, handles all Telegram bot interactions, menu navigation, and service requests
- **db.py**: Database layer with thread-safe connections, transaction management, and user data operations
- **openai_service.py**: Manages OpenAI Assistant API calls, thread creation, message formatting, and retry logic
- **monobank_payments.py**: Monitors Monobank API for incoming payments and automatically updates user balances
- **operator_menu.py**: Administrative interface for operators to manage users, balances, and account status
- **rate_limiter.py**: Implements sliding window rate limiting for different types of requests
- **ux_improvements.py**: Provides formatted messages, balance displays, and user-friendly interfaces
- **additional_improvements.py**: Contains UserRequestLock, BalanceCache, and BalanceDeductionTracker utilities

## Key Components

### Rate Limiting
- Message rate limiter: 20 requests per 60 seconds
- Service rate limiter: 10 requests per 60 seconds
- Payment rate limiter: 5 requests per 300 seconds
- Sliding window algorithm for accurate rate limiting

### Thread Management
Each user gets a unique OpenAI thread per service to maintain conversation context. Threads are cleared when users return to the main menu.

### Balance System
- New users receive 5 free requests
- Each service request costs 1 request from balance
- Balance can be topped up via Monobank payments
- Operators can manually adjust balances
- Balance caching with TTL (30 seconds) to reduce database load
- Protection against double deduction using deduction tracker

### Request Locking
- Prevents concurrent requests from the same user
- Uses async locks to prevent race conditions
- Ensures only one request is processed per user at a time

### Balance Caching
- Reduces database queries by 70-80%
- Automatic cache invalidation on balance changes
- TTL-based expiration (30 seconds)

### Error Handling
- Comprehensive error logging
- User-friendly error messages
- Automatic retry for API failures with exponential backoff
- Group notifications for critical errors
- Input validation and XSS protection

## Security Features

- Input validation for user messages (max 4000 characters)
- Protection against XSS attacks and injection attempts
- Rate limiting to prevent abuse and spam
- User blocking functionality
- Secure database transactions with WAL mode
- Thread-local database connections for thread safety
- Request locking to prevent concurrent operations
- Balance deduction tracking to prevent double charges

## Logging

The bot uses Python's logging module with INFO level by default. Logs include:
- User actions
- API requests and responses
- Payment processing
- Errors and exceptions

## Development

### Adding New Services

1. Create a new OpenAI Assistant
2. Add the Assistant ID to `.env`
3. Add the service to `SERVICE_ASSISTANTS` in `openai_service.py`
4. Add menu option in `bot.py`

### Modifying Rate Limits

Edit the rate limiter instances in `rate_limiter.py`:
```python
message_rate_limiter = RateLimiter(max_requests=20, window_seconds=60)
service_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
```

## Troubleshooting

### Bot not responding
- Check if the bot is running
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Check logs for errors

### Payments not processing
- Verify `MONOBANK_API_TOKEN` is correct
- Check if payment checker is running
- Ensure user includes username or ID in payment comment

### OpenAI errors
- Verify `OPENAI_API_KEY` is valid
- Check Assistant IDs are correct
- Ensure you have sufficient API credits

### Database errors
- Check file permissions for `users.db`
- Verify database is not locked by another process
- Check logs for specific error messages

## License

This project is for internal use by Ukrainian military logistics personnel.

## Support

For technical support or questions, contact the operator via Telegram: @TylBotOperator

## Technical Details

### Database
- SQLite with WAL (Write-Ahead Logging) mode for better concurrency
- Thread-local connections for thread safety
- Automatic transaction management with rollback on errors
- Indexed queries for fast user lookups

### Performance Optimizations
- Balance caching reduces database load by 70-80%
- Request locking prevents unnecessary concurrent operations
- Rate limiting protects against abuse
- Efficient thread management for OpenAI conversations

### API Integration
- OpenAI Assistants API with retry logic and exponential backoff
- Monobank API for payment processing with automatic detection
- Telegram Bot API via aiogram framework

## Notes

- The bot operates 24/7
- All responses are based on official regulatory documents
- User data is stored locally in SQLite database
- Payment processing requires active Monobank API connection
- Database files (users.db, users.db-shm, users.db-wal) are automatically created
- Temporary files and cache are excluded from version control via .gitignore

