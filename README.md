# 🚀 StockX API Integration

A complete Python integration for StockX's public API with automatic authentication, product search, market data access, and inventory pricing analysis.

## 📋 Table of Contents

- [Features](#-features)
- [Quick Start](#-quick-start)
- [Project Structure](#-project-structure)
- [Authentication](#-authentication)
- [Usage Examples](#-usage-examples)
- [Inventory Pricing](#-inventory-pricing)
- [API Reference](#-api-reference)
- [Configuration](#-configuration)
- [Troubleshooting](#-troubleshooting)
- [Technical Details](#-technical-details)

## ✨ Features

- **🔐 Automatic Authentication** - Handles OAuth flow and token refresh automatically
- **🔍 Product Search** - Search StockX's catalog of 50,000+ products
- **📊 Market Data** - Access real-time pricing and sales data
- **💰 Inventory Pricing** - Bulk analyze inventory with profit calculations
- **⚡ Zero Configuration** - Works out of the box with smart defaults
- **🛡️ Error Handling** - Robust error handling and retry logic
- **🕒 Token Management** - Automatic token refresh every 12 hours

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <your-repo-url>
cd stockx1

# Install dependencies
pip install -r requirements.txt
```

### 2. Run Your First Search

```python
from smart_stockx_client import SmartStockXClient

# Initialize client (auto-authenticates)
client = SmartStockXClient()

# Search for products
results = client.search_products("Jordan 1", limit=5)

print(f"Found {results['count']:,} products")
for product in results['products']:
    print(f"- {product['title']} ({product['brand']})")
```

### 3. Run the Demo

```bash
python3 smart_stockx_client.py
```

## 📁 Project Structure

```
stockx1/
├── smart_stockx_client.py      # 🤖 Main client with auto-authentication
├── auto_auth_system.py         # 🔐 Standalone authentication system
├── example.py                  # 📝 Usage examples and demos
├── pricing_tools/              # 💰 Inventory pricing analysis
│   ├── inventory_stockx_analyzer.py  # 📊 Bulk inventory pricing tool
│   ├── Copy of SNKR DEPT LIST 6_14 - Sheet1.csv  # 📁 Sample inventory
│   ├── stockx_enhanced_*.csv   # 📄 Generated pricing reports
│   └── README.md               # 📖 Pricing tools documentation
├── ebay_tools/                 # 💰 eBay integration tools
│   ├── ebay_stockxpricing.py   # 📊 eBay-StockX price comparison
│   ├── csv_inputs/             # 📁 eBay auction data files
│   └── README.md               # 📖 eBay tools documentation
├── tokens_full_scope.json      # 🔑 Authentication tokens (auto-generated)
├── requirements.txt            # 📦 Python dependencies
└── README.md                   # 📖 This file
```

### Core Files

| File | Purpose | Use When |
|------|---------|----------|
| `smart_stockx_client.py` | Main API client | Building applications |
| `auto_auth_system.py` | Authentication only | Token management only |
| `example.py` | Usage examples | Learning the API |
| `pricing_tools/` | Inventory analysis | Bulk pricing analysis |
| `ebay_tools/` | eBay integration | Price comparison |
| `tokens_full_scope.json` | Stored tokens | Auto-generated |

## 🔐 Authentication

### Authentication Flow

The system uses **smart authentication** that minimizes user intervention:

1. **First Run** → Full OAuth (browser opens once)
2. **Normal Use** → Automatic token refresh (invisible)
3. **Token Expires** → Browser opens again (every 30-90 days)

### Authentication Timeline

| Event | Frequency | User Action |
|-------|-----------|-------------|
| Access Token Refresh | Every 12 hours | ❌ None (automatic) |
| Full Re-authentication | Every 30-90 days | ✅ Browser login |

### Setup Options

#### Option A: Localhost Callback (Recommended)
- **Callback URL**: `http://localhost:8080/callback`
- **Experience**: Browser opens → Login → Auto-redirect → Done
- **Setup**: Update callback URL in StockX Developer Portal

#### Option B: Example.com Callback (Current)
- **Callback URL**: `https://example.com`
- **Experience**: Browser opens → Login → Copy code from address bar
- **Setup**: No changes needed

### Manual Authentication

If you need to re-authenticate manually:

```bash
python3 auto_auth_system.py
```

## 📚 Usage Examples

### Basic Product Search

```python
from smart_stockx_client import SmartStockXClient

client = SmartStockXClient()

# Simple search
results = client.search_products("Nike Dunk", page_size=10)
print(f"Found {results['count']:,} products")

# Quick search with output
products = client.quick_search("Yeezy 350", limit=5)
```

### Advanced Search with Details

```python
# Search with pagination
page1 = client.search_products("Jordan 1", page_size=20, page_number=1)
page2 = client.search_products("Jordan 1", page_size=20, page_number=2)

# Get product details
product_id = page1['products'][0]['id']
details = client.get_product_details(product_id)

print(f"Product: {details['title']}")
print(f"Brand: {details['brand']}")
print(f"Style: {details.get('styleId', 'N/A')}")
```

### Market Data Analysis

```python
# Get market data for a product
market_data = client.get_market_data(product_id)

if market_data:
    print(f"Lowest Ask: ${market_data.get('lowestAsk', 'N/A')}")
    print(f"Highest Bid: ${market_data.get('highestBid', 'N/A')}")
    print(f"Last Sale: ${market_data.get('lastSale', 'N/A')}")
```

### Batch Processing

```python
# Search multiple brands
brands = ["Nike", "Jordan", "adidas", "New Balance"]

for brand in brands:
    results = client.search_products(brand, page_size=5)
    print(f"{brand}: {results['count']:,} products")
    
    for product in results['products']:
        print(f"  - {product['title']}")
```

## 💰 Inventory Pricing

### Bulk Inventory Analysis

The `pricing_tools/` folder contains a powerful inventory pricing system that can analyze entire CSV files of sneaker inventory and get real-time StockX pricing data.

#### Quick Start

```bash
# Navigate to pricing tools
cd pricing_tools

# Analyze your inventory
python3 inventory_stockx_analyzer.py "your_inventory.csv"
```

#### Features

- **📊 Smart CSV Parsing** - Handles multiple CSV formats automatically
- **🔍 Intelligent Matching** - Finds exact StockX products with scoring algorithm
- **💰 Profit Calculations** - Automatic bid/ask profit margin calculations
- **⚠️ Uncertainty Handling** - Flags uncertain size matches (GS/PS/Women's)
- **⚡ Optimized Performance** - 30 requests/minute with no rate limiting
- **📈 Complete Data** - SKU, URLs, exact names, sizes, and pricing

#### Example Output

```
✅ Jordan 4 Thunder (Size 9): $260 → Bid: $310 (+$50), Ask: $359 (+$99)
✅ Jordan 1 Black Toe Reimagined (Size 13): $75 → Bid: $93 (+$18), Ask: $106 (+$31)
⚠️ Nike Dunk Low Blueberry (Size 4.5): $60 → Bid: $45Y (-$15), Ask: $52Y (-$8) [UNCERTAIN]
```

#### Supported CSV Formats

**Format 1: Grouped Layout**
```csv
Nike Dunk Low Blueberry,60
4.5,60
5,60
5.5,60
```

**Format 2: Row-based Layout**
```csv
Nike Dunk Reverse Panda,M10,Brand New,,60,
Jordan 1 Black Toe Reimagined,13,Used,,75,
```

For detailed documentation, see [`pricing_tools/README.md`](pricing_tools/README.md).

## 🔧 API Reference

### SmartStockXClient

#### Constructor

```python
SmartStockXClient(auto_authenticate=True)
```

- `auto_authenticate` (bool): Automatically handle authentication

#### Methods

##### `search_products(query, page_size=20, page_number=1)`

Search the StockX product catalog.

**Parameters:**
- `query` (str): Search term (e.g., "Jordan 1", "Nike Dunk")
- `page_size` (int): Results per page (max 100)
- `page_number` (int): Page number (starts at 1)

**Returns:**
```python
{
    'products': [
        {
            'id': 'product-uuid',
            'title': 'Product Name',
            'brand': 'Brand Name',
            'style_id': 'Style ID',
            'product_type': 'sneakers',
            'url_key': 'product-slug',
            'attributes': {...},
            'raw': {...}  # Original API response
        }
    ],
    'count': 12345,
    'page_number': 1,
    'page_size': 20,
    'has_next_page': True,
    'query': 'search term'
}
```

##### `get_product_details(product_id)`

Get detailed information for a specific product.

**Parameters:**
- `product_id` (str): Product UUID from search results

**Returns:** Complete product details including attributes and variants

##### `get_market_data(product_id)`

Get market data (pricing, sales) for a product.

**Parameters:**
- `product_id` (str): Product UUID

**Returns:** Market data including pricing and sales information

##### `quick_search(query, limit=5)`

Convenience method for quick searches with console output.

**Parameters:**
- `query` (str): Search term
- `limit` (int): Number of results

**Returns:** List of products

## ⚙️ Configuration

### Environment Variables

None required! The system works with built-in configuration.

### Customization

You can customize the client behavior:

```python
# Disable auto-authentication
client = SmartStockXClient(auto_authenticate=False)

# Manual authentication later
client._ensure_authentication()
```

### Token Storage

Tokens are automatically saved to `tokens_full_scope.json`. This file contains:

- `access_token`: Short-lived API access token
- `refresh_token`: Long-lived token for automatic refresh
- `expires_in`: Token expiration time (seconds)
- `scope`: Granted permissions

## 🛠️ Troubleshooting

### Common Issues

#### "Authentication failed"
- **Cause**: Browser didn't open or auth flow interrupted
- **Solution**: Run `python3 auto_auth_system.py`

#### "401 Unauthorized" 
- **Cause**: Access token expired and refresh failed
- **Solution**: Delete `tokens_full_scope.json` and restart

#### "Search failed: 401"
- **Cause**: Token refresh needed
- **Solution**: Client automatically refreshes, try again

#### "Connection timeout"
- **Cause**: Network issues or API downtime  
- **Solution**: Check internet connection, try again

### Debug Mode

For detailed debugging information:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

client = SmartStockXClient()
```

### Manual Token Refresh

If automatic refresh fails:

```python
client = SmartStockXClient(auto_authenticate=False)
success = client._refresh_access_token()
print(f"Refresh successful: {success}")
```

## 🔧 Technical Details

### API Endpoints

- **Base URL**: `https://api.stockx.com/v2`
- **Search**: `/catalog/search`
- **Product Details**: `/catalog/products/{id}`
- **Market Data**: `/catalog/products/{id}/market-data`

### Authentication Details

- **OAuth Provider**: `https://accounts.stockx.com`
- **Grant Type**: Authorization Code
- **Scopes**: `openid offline_access read:catalog read:products read:market`
- **Audience**: `gateway.stockx.com`

### Rate Limiting

StockX API has rate limits (exact limits not documented):
- Use reasonable delays between requests
- Implement retry logic for 429 responses
- Cache results when possible

### Security Notes

- **Tokens**: Stored locally in `tokens_full_scope.json`
- **Credentials**: Hardcoded (for demo purposes)
- **HTTPS**: All API calls use HTTPS
- **Localhost**: Callback server runs temporarily during auth

## 📊 Example Applications

### Price Monitoring

```python
# Monitor prices for specific products
def monitor_prices(product_ids):
    client = SmartStockXClient()
    
    for product_id in product_ids:
        market_data = client.get_market_data(product_id)
        details = client.get_product_details(product_id)
        
        print(f"{details['title']}: ${market_data.get('lowestAsk', 'N/A')}")

monitor_prices(['product-id-1', 'product-id-2'])
```

### Brand Analysis

```python
# Analyze product distribution by brand
brands = ["Nike", "Jordan", "adidas", "New Balance", "Converse"]

for brand in brands:
    results = client.search_products(brand)
    print(f"{brand}: {results['count']:,} products")
```

### Popular Products

```python
# Find popular products in a category
def find_popular(query, limit=20):
    results = client.search_products(query, page_size=limit)
    
    for product in results['products']:
        print(f"- {product['title']}")
        print(f"  Brand: {product['brand']}")
        print(f"  Style: {product['style_id']}")
        print()

find_popular("basketball shoes")
```

## 📈 Next Steps

### Production Deployment

1. **Environment Variables**: Move credentials to environment variables
2. **Database**: Store tokens in secure database
3. **Logging**: Implement comprehensive logging
4. **Monitoring**: Add health checks and monitoring
5. **Error Handling**: Enhanced error handling and recovery

### Feature Extensions

- **Caching**: Implement response caching
- **Webhooks**: Real-time price updates
- **Analytics**: Data analysis and visualization
- **Mobile**: iOS/Android app integration

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes  
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is for educational purposes. Please comply with StockX's API Terms of Service.

---

**🎉 Happy coding!** If you have questions, check the troubleshooting section or review the code comments for detailed explanations. # Auto-deployment test
