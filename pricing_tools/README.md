# StockX Pricing Tools

Advanced tools for analyzing inventory against StockX market data with Alias pricing insights.

## Features

- **CSV Processing**: Parse structured CSV files with flexible column detection
- **Pasted List Processing**: Handle complex inventory lists copied from Excel/Google Sheets (separate feature)
- **Smart Matching**: Intelligent shoe name and size matching with StockX products
- **Rate Limiting**: Built-in retry logic and optimal request pacing
- **Profit Calculations**: Automatic bid/ask profit calculations
- **Alias Pricing Data**: Complete pricing insights from Alias API including consignment data
- **Caching**: Results caching to avoid duplicate API calls

## Quick Start

### CSV Processing (Default)
```bash
python inventory_stockx_analyzer.py your_inventory.csv
```

### Pasted List Processing (Manual)
```bash
python inventory_stockx_analyzer.py --list your_pasted_shoes.txt
```

## Input Formats

### CSV Format
Flexible CSV with any combination of:
- Shoe name/product name
- Size (including Y/W youth/women sizes)
- Price
- Condition

Example CSV:
```csv
Shoe Name,Size,Price,Condition
Nike Dunk Low Panda,10.5,120,Used
Jordan 1 High Chicago,11,450,New
```

### Pasted List Format (Manual Option)
For when you copy inventory from Excel/Google Sheets:

```text
Jordan 3 white cement 88 - size 11 ($460)
Supreme air max 1 87 white - size 11.5x2, 12 ($210)
Yeezy bone 500 - size 4.5x13, 5x9, 5.5x4 ($185)
White cement 4 - size 8,8.5x2,9.5,10.5,11x8,11.5x3,12x4 ($245)
```

Features:
- Complex shoe names with descriptors
- Multiple sizes with quantities (11.5x2 = 2 pairs of size 11.5)
- Comma-separated sizes
- Price extraction from parentheses
- Special notes handling

## Output

Enhanced CSV with exact column order:
1. `original_shoe_name`, `original_size` - Your original data
2. `stockx_bid`, `stockx_ask` - Current StockX market prices
3. **Alias Pricing Data:**
   - `lowest_consigned` - Lowest consigned price
   - `last_consigned_price` - Most recent consigned sale price
   - `last_consigned_date` - Days since last consigned sale (e.g., "5 days ago")
   - `lowest_with_you` - Overall lowest price available
   - `last_with_you_price` - Most recent sale price
   - `last_with_you_date` - Days since last sale (e.g., "3 days ago")
4. `stockx_sku`, `stockx_url`, `stockx_size`, `stockx_shoe_name` - StockX details

## Alias Pricing Data

Integrates with Alias API to provide comprehensive pricing insights:
- **Ship to Verify Price**: Lowest available listing price
- **Consignment Price**: Pricing specifically for consigned items
- **Lowest With You**: Overall lowest price across all channels
- **Lowest Consigned**: Lowest price among consigned items only
- **Last Sales Data**: Most recent sale prices and dates (overall and consigned)
- **Date Information**: When items were last sold for pricing trends

## Enhanced Features (Latest Updates)

### 🔍 **Improved Size Recognition**
- **Women's sizes**: `6w`, `6W`, `W6` all correctly recognized as women's size 6
- **Youth sizes**: `7y`, `7Y`, `Y7` all correctly recognized as youth/GS size 7  
- **Child sizes**: `5c`, `5C`, `C5` all correctly recognized as child/PS size 5
- **Better parsing**: No more failed size matches due to case sensitivity

### 👟 **Smarter Shoe Name Matching**
- **Preserves important details**: Years (2016), special notes (without laces), colorways
- **Only removes condition notes**: Removes (DS), (VNDS), (no box) but keeps meaningful details
- **Better accuracy**: More precise matches by considering all descriptive words

### 📊 **Enhanced Logging & Progress**
- **Detailed StockX progress**: Shows search → match → variant → market data retrieval
- **SKU verification**: Compares StockX and Alias SKUs to verify same shoe
- **Size category display**: Shows men/women/youth categorization
- **Clear error messages**: Better debugging information

### 🗓️ **User-Friendly Dates**
- **Days ago format**: "3 days ago" instead of "2025-01-15T12:34:56Z"
- **Natural language**: "today", "1 day ago", "15 days ago"
- **Easy interpretation**: Quick understanding of sale recency

### 🎯 **SKU Cross-Verification**
- **Dual API verification**: Ensures StockX and Alias refer to same shoe
- **Mismatch detection**: Warns when SKUs don't match between platforms
- **Confidence boost**: Higher accuracy through SKU validation

## Size Matching

Automatically handles:
- Standard US men's sizes (8, 8.5, 9, etc.)
- Youth sizes (Y6, Y7, etc.) - **Enhanced recognition**
- Women's sizes (W8, W8.5, etc.) - **Enhanced recognition**  
- Child sizes (C5, C6, etc.) - **Enhanced recognition**
- International sizes (UK, EU when available)

## Performance

- **Rate Limiting**: 30 requests/minute (2-second intervals)
- **Retry Logic**: Up to 3 attempts on rate limit errors
- **Caching**: Duplicate searches avoided
- **Progress Tracking**: Real-time progress updates
- **Dual API Integration**: StockX for market data, Alias for pricing insights

## Files

- `inventory_stockx_analyzer.py` - Main analyzer
- `README.md` - This documentation

## Authentication

Requires valid StockX authentication. The system will use your existing authentication setup from the main application. Alias API integration uses embedded API key. 