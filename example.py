#!/usr/bin/env python3
"""
📊 StockX API Example
Simple examples of how to use the StockX API client
"""

from smart_stockx_client import SmartStockXClient

def basic_search_example():
    """Basic product search example"""
    print("🔍 Basic Search Example")
    print("-" * 30)
    
    client = SmartStockXClient()
    
    # Search for Jordan 1s
    results = client.search_products("Jordan 1", page_size=5)
    
    print(f"Found {results['count']:,} total Jordan 1 products")
    print(f"Showing top {len(results['products'])} results:")
    print()
    
    for i, product in enumerate(results['products'], 1):
        print(f"{i}. {product['title']}")
        print(f"   Brand: {product['brand']}")
        print(f"   Style: {product['style_id']}")
        print(f"   Type: {product['product_type']}")
        print()

def product_details_example():
    """Product details and market data example"""
    print("📊 Product Details Example")
    print("-" * 30)
    
    client = SmartStockXClient()
    
    # Search for a specific product
    results = client.search_products("Nike Dunk Low Panda", page_size=1)
    
    if results['products']:
        product = results['products'][0]
        product_id = product['id']
        
        print(f"Product: {product['title']}")
        print(f"ID: {product_id}")
        print()
        
        # Get detailed information
        details = client.get_product_details(product_id)
        print("📋 Product Details:")
        print(f"   Brand: {details.get('brand', 'N/A')}")
        print(f"   Style ID: {details.get('styleId', 'N/A')}")
        print(f"   Type: {details.get('productType', 'N/A')}")
        print()
        
        # Get market data
        try:
            market_data = client.get_market_data(product_id)
            print("💰 Market Data:")
            print(f"   Lowest Ask: ${market_data.get('lowestAsk', 'N/A')}")
            print(f"   Highest Bid: ${market_data.get('highestBid', 'N/A')}")
            print(f"   Last Sale: ${market_data.get('lastSale', 'N/A')}")
        except Exception as e:
            print(f"   Market data unavailable: {str(e)}")
        print()

def brand_comparison_example():
    """Compare product counts across different brands"""
    print("🏷️ Brand Comparison Example")
    print("-" * 30)
    
    client = SmartStockXClient()
    
    brands = ["Nike", "Jordan", "adidas", "New Balance", "Puma"]
    
    print("Product counts by brand:")
    for brand in brands:
        results = client.search_products(brand, page_size=1)
        count = results['count']
        print(f"   {brand:12}: {count:,} products")
    print()

def quick_search_example():
    """Quick search with built-in formatting"""
    print("⚡ Quick Search Example")
    print("-" * 30)
    
    client = SmartStockXClient()
    
    # Quick search automatically prints results
    products = client.quick_search("Yeezy 350", limit=3)
    print()

def main():
    """Run all examples"""
    print("🚀 StockX API Examples")
    print("=" * 50)
    print()
    
    try:
        basic_search_example()
        product_details_example()
        brand_comparison_example()
        quick_search_example()
        
        print("✅ All examples completed successfully!")
        
    except Exception as e:
        print(f"❌ Error running examples: {str(e)}")
        print("\nTip: Make sure you're authenticated by running:")
        print("python3 auto_auth_system.py")

if __name__ == "__main__":
    main() 