# 📊 StockX Inventory Pricing Tools

This folder contains tools for analyzing sneaker inventory and getting real-time StockX pricing data.

## 🚀 Main Tool: Inventory StockX Analyzer

### Overview
`inventory_stockx_analyzer.py` is a comprehensive tool that:
- Processes CSV inventory files with flexible format support
- Searches StockX API for each item to find exact matches
- Extracts real-time bid/ask prices, SKUs, and product URLs
- Calculates profit margins automatically
- Handles uncertain size matches (GS/PS/Women's sizing)
- Provides detailed progress tracking and error handling

### Features

#### ✅ **Smart CSV Parsing**
- Handles multiple CSV formats automatically
- Supports both grouped (shoe name + sizes below) and row-based formats
- Flexible size and price detection

#### ✅ **Advanced StockX Integration**
- OAuth 2.0 authentication with automatic token refresh
- Intelligent product matching with scoring algorithm
- Exact size variant matching using proper API endpoints
- Rate limiting optimized (30 requests/minute)

#### ✅ **Enhanced Output**
- **Profit Calculations**: Automatic bid/ask profit margins
- **Uncertainty Indicators**: Flags for size category mismatches
- **StockX URLs**: Direct links to product pages
- **Complete Data**: SKU, exact names, sizes, and pricing

### Usage

```bash
# Basic usage
python3 inventory_stockx_analyzer.py "your_inventory.csv"

# The script will:
# 1. Parse your CSV file
# 2. Authenticate with StockX API
# 3. Search for each item
# 4. Generate enhanced CSV with StockX data
```

### Input CSV Format Support

The analyzer supports multiple CSV formats:

#### Format 1: Grouped Layout
```csv
Nike Dunk Low Blueberry,60
4.5,60
5,60
5.5,60
6,60
6.5,60
7,60
```

#### Format 2: Row-based Layout
```csv
Nike Dunk Reverse Panda,M10,Brand New,,60,
Jordan 1 Black Toe Reimagined,13,Used,,75,
```

### Output Columns

The enhanced CSV includes:

| Column | Description |
|--------|-------------|
| `original_shoe_name` | Original shoe name from inventory |
| `original_size` | Original size from inventory |
| `original_price` | Original price from inventory |
| `condition` | Condition (Brand New, Used, etc.) |
| `bid_profit` | Profit if sold at current bid price |
| `ask_profit` | Profit if sold at current ask price |
| `stockx_bid` | Current highest bid on StockX |
| `stockx_ask` | Current lowest ask on StockX |
| `stockx_sku` | StockX SKU/Product ID |
| `stockx_url` | Direct link to StockX product page |
| `stockx_size` | Exact size as listed on StockX |
| `size_match_uncertain` | Flag for uncertain size matches |
| `stockx_shoe_name` | Exact shoe name from StockX |

### Rate Limiting

- **Optimal Speed**: 2-second intervals (30 requests/minute)
- **No Rate Limiting Errors**: Tested with 169+ items
- **Progress Tracking**: Updates every 15 items

### Error Handling

- **Size Mismatches**: Automatically tries Y/C/W suffixes for uncertain matches
- **No Matches**: Clearly marked in output with StockX data as empty
- **API Errors**: Graceful handling with retry logic
- **Caching**: Avoids duplicate API calls for same items

### Example Results

```
✅ Jordan 4 Thunder (Size 9): $260 → Bid: $310 (+$50), Ask: $359 (+$99)
✅ Jordan 1 Black Toe Reimagined (Size 13): $75 → Bid: $93 (+$18), Ask: $106 (+$31)
⚠️ Nike Dunk Low Blueberry (Size 4.5): $60 → Bid: $45Y (-$15), Ask: $52Y (-$8) [UNCERTAIN]
```

### Requirements

- Python 3.7+
- `smart_stockx_client.py` (in parent directory)
- `auto_auth_system.py` (in parent directory)
- StockX API credentials configured

### Files

- `inventory_stockx_analyzer.py` - Main pricing analysis tool
- `Copy of SNKR DEPT LIST 6_14 - Sheet1.csv` - Sample inventory file
- `stockx_enhanced_*.csv` - Generated output files with StockX data 