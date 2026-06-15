# NANOREM MLM System

## Project Overview

A multi-level marketing (MLM) platform for NANOREM automotive care products. This application includes a complete backend system with Telegram bot integration, partner management, commission tracking, and affiliate network functionality.

## Features

- **Partner Management**: Register and manage MLM partners at different levels
- **Commission Tracking**: Automatic calculation and tracking of commissions
- **Network Management**: Track upline/downline relationships and structure
- **Product Management**: Manage NANOREM product catalog and pricing
- **Order Processing**: Handle partner and customer orders
- **Telegram Bot Integration**: User-friendly interface via Telegram
- **Analytics & Reporting**: Partner performance and sales analytics

## Project Structure

```
nanorem-bot/
├── README.md                 # Project documentation
├── requirements.txt          # Python dependencies
├── config.py                 # Configuration settings
├── main.py                   # Application entry point
├── core/                     # MLM system core logic
│   ├── partner_manager.py    # Partner management
│   ├── commission.py         # Commission calculations
│   └── network.py            # Network structure
├── database/                 # Database layer
│   ├── models.py             # Data models
│   └── db.py                 # Database connection
├── telegram/                 # Telegram bot
│   ├── bot.py                # Bot main logic
│   └── handlers.py           # Command handlers
└── utils/                    # Utility functions
    ├── validators.py         # Input validation
    └── helpers.py            # Helper functions
```

## Technology Stack

- **Backend**: Python 3.10+
- **Database**: SQLite/PostgreSQL
- **Bot Framework**: python-telegram-bot
- **Version Control**: Git + GitHub

## Documentation

Detailed documentation and specifications are stored in the project's Yandex.Disk folder:
- [NANOREM MLM System - Project Hub](https://disk.yandex.ru/d/NANOREM_MLM_Project)

Key documents:
- MLM System Structure & Architecture
- Requirements and Specifications
- Database Schema
- API Specifications
- Business Rules

## Getting Started

### Prerequisites
- Python 3.10 or higher
- pip (Python package manager)
- Telegram Bot Token

### Installation

1. Clone the repository
```bash
git clone https://github.com/sercar7-maker/nanorem-bot.git
cd nanorem-bot
```

2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Configure settings
```bash
cp config.example.py config.py
# Edit config.py with your settings
```

5. Initialize database
```bash
python main.py --init-db
```

6. Run the bot
```bash
python main.py
```

## Contributing

Contributions are welcome. Please:
1. Create a feature branch
2. Make your changes
3. Submit a pull request

## License

Private Project - NANOREM

## Contact

## ⚠️ Важное примечание

**Папка `integrations/` устарела и не используется.**

Облачная касса уже подключена производителем NANOREM напрямую. Все файлы в папке `integrations/` (cash_register.py, cash_register_config.py) оставлены только для справки и не требуются для работы системы.

Project Owner: sercar7-maker  
Repository: https://github.com/sercar7-maker/nanorem-bot
