# StockX API Integration Project

## Overview

This project provides a comprehensive Python integration for StockX's public API, featuring automatic authentication, product search capabilities, market data access, and inventory pricing analysis tools. The system is designed to be user-friendly with zero configuration requirements and robust error handling.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Architecture
- **Language**: Python 3
- **Web Framework**: Flask (minimal web UI)
- **API Integration**: RESTful API client with OAuth 2.0 authentication
- **Data Processing**: CSV-based inventory analysis tools
- **Authentication**: Automated OAuth flow with token refresh
- **Data Storage**: JSON-based token storage, CSV file processing

### Key Design Principles
- Zero-configuration setup with smart defaults
- Automatic authentication and token management
- Modular tool-based architecture
- Robust error handling and retry logic
- Rate limiting and API efficiency optimization

## Key Components

### 1. Authentication System (`auto_auth_system.py`, `smart_stockx_client.py`)
- **Purpose**: Handles OAuth 2.0 flow automatically without manual browser interaction
- **Features**: Token refresh, callback handling, persistent storage
- **Architecture**: HTTP server for OAuth callbacks, automatic browser launching
- **Token Management**: 12-hour automatic refresh cycle

### 2. Core API Client (`smart_stockx_client.py`)
- **Purpose**: Main interface to StockX API
- **Features**: Product search, market data access, product details
- **Rate Limiting**: Optimized for 30 requests/minute
- **Error Handling**: Comprehensive retry logic and exception handling

### 3. eBay Integration Tools (`ebay_tools/`)
- **Purpose**: Price comparison between eBay auctions and StockX market data
- **Features**: CSV processing, intelligent shoe name matching, profit calculations
- **Architecture**: Standalone tool that imports the core client
- **Data Flow**: eBay CSV → Name cleaning → StockX search → Enhanced CSV output

### 4. Inventory Pricing Tools (`pricing_tools/`)
- **Purpose**: Bulk inventory analysis with StockX pricing data
- **Features**: Flexible CSV format support, size matching, profit margin calculations
- **Architecture**: Modular parser with smart format detection
- **Output**: Enhanced CSV with bid/ask prices, SKUs, and profit margins

### 5. Web Interface (`app.py`)
- **Purpose**: Minimal Flask web UI for running scripts
- **Features**: Async script execution, real-time output streaming
- **Architecture**: Simple web interface with subprocess management
- **Functionality**: Web-based tool launcher with progress tracking

## Data Flow

### Authentication Flow
1. Client initialization triggers OAuth process
2. Browser opens to StockX authorization page
3. Local HTTP server captures callback with authorization code
4. Token exchange completed automatically
5. Tokens stored in JSON file for persistence
6. Automatic refresh every 12 hours

### Product Search Flow
1. Input sanitization and standardization
2. StockX API search request with pagination
3. Response parsing and data extraction
4. Caching for duplicate prevention
5. Results formatting and return

### Inventory Analysis Flow
1. CSV file parsing with format detection
2. Item extraction and normalization
3. Batch StockX searches with rate limiting
4. Size variant matching using product details API
5. Profit calculation and uncertainty flagging
6. Enhanced CSV output generation

## External Dependencies

### Required Packages
- **flask**: Web interface framework
- **requests**: HTTP client for API calls
- **urllib3**: URL handling utilities
- **certifi**: SSL certificate verification

### StockX API Integration
- **API Key**: Hardcoded public API key
- **Client Credentials**: OAuth 2.0 application credentials
- **Endpoints**: Product search, product details, market data
- **Authentication**: OAuth 2.0 with refresh tokens
- **Rate Limits**: 30 requests per minute (managed automatically)

### Browser Integration
- **OAuth Flow**: Automatic browser launching for authorization
- **Callback Handling**: Local HTTP server on localhost
- **Cross-Platform**: Works on Windows, macOS, and Linux

## Deployment Strategy

### Local Development
- **Requirements**: Python 3.6+ with pip
- **Setup**: Clone repository, install requirements.txt
- **Configuration**: Zero configuration required - works out of the box
- **Authentication**: Automatic OAuth setup on first run

### File Structure
```
project_root/
├── smart_stockx_client.py       # Core API client
├── auto_auth_system.py          # Authentication system
├── example.py                   # Usage examples
├── app.py                       # Web interface
├── requirements.txt             # Dependencies
├── tokens_full_scope.json       # Token storage
├── ebay_tools/                  # eBay integration
│   ├── ebay_stockxpricing.py   # Price comparison tool
│   └── csv_inputs/             # Input CSV files
└── pricing_tools/              # Inventory analysis
    └── inventory_stockx_analyzer.py
```

### Security Considerations
- API credentials are hardcoded (public API keys)
- OAuth tokens stored in local JSON file
- Local HTTP server for OAuth callbacks (localhost only)
- No sensitive data persistence beyond access tokens

### Scalability Notes
- Rate limiting built-in for API compliance
- Caching implemented to reduce redundant requests
- Modular design allows for easy extension
- CSV processing handles large inventory files efficiently

### Error Handling Strategy
- Comprehensive exception handling throughout
- Retry logic for transient API failures
- Graceful degradation for missing data
- User-friendly error messages and logging