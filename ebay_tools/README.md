# eBay Tools Directory

This directory contains all eBay-specific functionality and data for the StockX integration project.

## Contents

### `ebay_stockxpricing.py`
The main eBay-StockX price comparison tool that:
- Processes eBay auction CSV files
- Searches StockX for matching products
- Adds StockX pricing data and profit calculations
- Outputs enhanced CSV files with detailed analysis

### `csv_inputs/`
Directory containing eBay auction data files:
- Input CSV files from eBay auctions
- Enhanced output CSV files with StockX data added

## Usage

From the project root directory, run:

```bash
cd ebay_tools
python ebay_stockxpricing.py
```

The tool will:
1. Process CSV files in the `csv_inputs/` directory
2. Search StockX for matching products
3. Calculate profit margins and price differences
4. Output enhanced CSV files with additional columns

## Features

- Intelligent shoe name cleaning and matching
- Size extraction from eBay titles
- StockX product search and market data retrieval
- Profit analysis with customizable thresholds
- Rate limiting and caching for API efficiency
- Detailed logging and progress tracking

## Requirements

Requires the parent directory's `smart_stockx_client.py` for StockX API access. 