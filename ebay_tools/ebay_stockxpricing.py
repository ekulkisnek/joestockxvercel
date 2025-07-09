#!/usr/bin/env python3
"""
💰 eBay-StockX Price Comparison Tool
Analyzes eBay auction data and compares with StockX market prices
"""

import csv
import json
import re
import time
import sys
import os
from datetime import datetime
from pathlib import Path

# Add parent directory to path to import SmartStockXClient
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smart_stockx_client import SmartStockXClient

class EbayStockXPricer:
    def __init__(self):
        """Initialize the pricing tool with StockX client"""
        self.client = SmartStockXClient()
        self.processed_count = 0
        self.matches_found = 0
        self.cache = {}  # Cache to avoid duplicate searches
        
    def clean_shoe_name(self, title):
        """Clean and standardize shoe names for better matching"""
        original_title = title.lower()
        
        # Extract Jordan model number first
        jordan_match = re.search(r'jordan\s*(\d+)', original_title)
        if jordan_match:
            model = jordan_match.group(1)
            
            # Look for colorway terms in the original title
            colorway_terms = []
            
            # Common Jordan colorways - check original title
            colorway_patterns = [
                ('yellow toe', 'yellow toe'),
                ('bred', 'bred'),
                ('chicago', 'chicago'), 
                ('royal', 'royal'),
                ('shadow', 'shadow'),
                ('black toe', 'black toe'),
                ('court purple', 'court purple'),
                ('obsidian', 'obsidian'),
                ('unc', 'unc'),
                ('pine green', 'pine green'),
                ('gym red', 'gym red'),
                ('banned', 'banned'),
                ('shattered', 'shattered'),
                ('fragment', 'fragment'),
                ('travis scott', 'travis scott'),
                ('off white', 'off white'),
                ('union', 'union'),
                ('dior', 'dior'),
                ('true blue', 'true blue'),
                ('pollen', 'pollen'),
                ('taxi', 'taxi'),
                ('heritage', 'heritage'),
                ('stage haze', 'stage haze'),
                ('marina blue', 'marina blue'),
                ('metallic silver', 'metallic silver')
            ]
            
            for pattern, term in colorway_patterns:
                if pattern in original_title:
                    colorway_terms.append(term)
            
            # Also look for "high" or "low" or "mid"
            cut_type = ""
            if ' high ' in original_title or 'retro high' in original_title:
                cut_type = " high"
            elif ' low ' in original_title or 'retro low' in original_title:
                cut_type = " low"
            elif ' mid ' in original_title:
                cut_type = " mid"
            
            # Build search query
            search_query = f"jordan {model}{cut_type}"
            if colorway_terms:
                search_query += " " + " ".join(colorway_terms)
            
            return search_query
        
        # If no Jordan number found, clean generically
        cleaned = re.sub(r'\b(size|new|with|box|nib|ds|deadstock|vnds|authentic)\b', '', original_title)
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned[:50]
    
    def extract_size_from_title(self, title):
        """Extract shoe size from title"""
        # Look for size patterns
        size_patterns = [
            r'size\s*(\d+\.?\d*)',
            r'(\d+\.?\d*)\s*(?:us|m|w)?(?:\s|$)',
            r'sz\s*(\d+\.?\d*)'
        ]
        
        for pattern in size_patterns:
            match = re.search(pattern, title.lower())
            if match:
                size = match.group(1)
                try:
                    # Validate size range
                    size_float = float(size)
                    if 3.0 <= size_float <= 20.0:
                        return size
                except ValueError:
                    continue
        
        return None
    
    def search_stockx_product(self, shoe_name, size=None):
        """Search StockX for a specific shoe"""
        cache_key = f"{shoe_name}_{size}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            # Search for the shoe
            search_results = self.client.search_products(shoe_name, page_size=10)
            
            if not search_results['products']:
                self.cache[cache_key] = None
                return None
            
            # Try to find the best match
            best_match = None
            exact_match = False
            
            for product in search_results['products']:
                product_title = product['title'].lower()
                search_lower = shoe_name.lower()
                
                # Check for exact or very close match
                if size:
                    # For size-specific searches, prioritize exact title matches
                    title_similarity = self.calculate_similarity(search_lower, product_title)
                    if title_similarity > 0.7:
                        best_match = product
                        exact_match = title_similarity > 0.9
                        break
                else:
                    # For general searches, take the first reasonable match
                    if any(term in product_title for term in search_lower.split()):
                        best_match = product
                        break
            
            if not best_match:
                best_match = search_results['products'][0]  # Fallback to first result
            
            result = {
                'product': best_match,
                'exact_match': exact_match,
                'total_found': search_results['count']
            }
            
            self.cache[cache_key] = result
            return result
            
        except Exception as e:
            print(f"Error searching for '{shoe_name}': {str(e)}")
            self.cache[cache_key] = None
            return None
    
    def calculate_similarity(self, str1, str2):
        """Simple similarity calculation"""
        words1 = set(str1.split())
        words2 = set(str2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def get_market_data(self, product_id):
        """Get market data for a product"""
        try:
            market_data = self.client.get_market_data(product_id)
            return market_data
        except Exception as e:
            print(f"Error getting market data for {product_id}: {str(e)}")
            return None
    
    def calculate_profit_metrics(self, ebay_price, stockx_bid, stockx_ask):
        """Calculate profit margins and price differences"""
        metrics = {
            'ask_over_ebay': None,
            'bid_over_ebay': None,
            'ask_profit_pct': None,
            'bid_profit_pct': None
        }
        
        try:
            ebay_price_float = float(ebay_price) if ebay_price else 0
            
            if stockx_ask and ebay_price_float > 0:
                ask_float = float(stockx_ask)
                metrics['ask_over_ebay'] = round(ask_float - ebay_price_float, 2)
                metrics['ask_profit_pct'] = round(((ask_float - ebay_price_float) / ebay_price_float) * 100, 2)
            
            if stockx_bid and ebay_price_float > 0:
                bid_float = float(stockx_bid)
                metrics['bid_over_ebay'] = round(bid_float - ebay_price_float, 2)
                metrics['bid_profit_pct'] = round(((bid_float - ebay_price_float) / ebay_price_float) * 100, 2)
                
        except (ValueError, TypeError):
            pass
        
        return metrics
    
    def process_csv(self, input_file, output_file=None):
        """Process eBay CSV and add StockX pricing data"""
        if not output_file:
            input_path = Path(input_file)
            output_file = input_path.parent / f"stockx_enhanced_{input_path.name}"
        
        print(f"📊 Processing eBay auction data: {input_file}")
        print(f"💾 Output will be saved to: {output_file}")
        print("=" * 60)
        
        # New columns to add (at the beginning)
        new_columns = [
            'ask_profit_pct',
            'bid_profit_pct', 
            'ask_over_ebay',
            'bid_over_ebay',
            'stockx_lowest_ask',
            'stockx_highest_bid',
            'stockx_last_sale',
            'stockx_last_sale_date',
            'stockx_product_title',
            'stockx_product_id',
            'stockx_match_confidence',
            'stockx_total_found'
        ]
        
        processed_rows = []
        
        with open(input_file, 'r', encoding='utf-8') as infile:
            reader = csv.DictReader(infile)
            original_columns = reader.fieldnames
            
            # New fieldnames with StockX data first
            fieldnames = new_columns + list(original_columns)
            
            for row_num, row in enumerate(reader, 1):
                print(f"\n🔍 Processing row {row_num}: ", end="")
                
                # Extract shoe information
                title = row.get('title', '')
                shoe_name = row.get('shoe_name', '') or title
                size = row.get('size', '') or self.extract_size_from_title(title)
                ebay_price = row.get('listing_price', '') or row.get('current_bid', '')
                
                print(f"{title[:50]}...")
                
                # Clean shoe name for searching
                search_query = self.clean_shoe_name(shoe_name or title)
                
                if not search_query.strip():
                    print("❌ Could not extract shoe name")
                    # Add empty StockX columns
                    for col in new_columns:
                        row[col] = ''
                    processed_rows.append(row)
                    continue
                
                print(f"   🔎 Searching StockX for: '{search_query}' (Size: {size or 'Any'})")
                
                # Search StockX
                search_result = self.search_stockx_product(search_query, size)
                
                if not search_result:
                    print("   ❌ No StockX matches found")
                    for col in new_columns:
                        row[col] = ''
                    processed_rows.append(row)
                    continue
                
                product = search_result['product']
                product_id = product['id']
                
                print(f"   ✅ Found: {product['title'][:50]}...")
                
                # Get market data
                market_data = self.get_market_data(product_id)
                
                stockx_bid = None
                stockx_ask = None
                stockx_last_sale = None
                stockx_last_sale_date = None
                
                if market_data:
                    # Market data is an array of VariantMarketData objects (one per size/variant)
                    if isinstance(market_data, list) and market_data:
                        # Find the best matching variant based on size if available
                        target_variant = None
                        
                        if size:
                            # Try to find variant matching the size
                            for variant in market_data:
                                # For now, just take the first variant with pricing data
                                if variant.get('lowestAskAmount') or variant.get('highestBidAmount'):
                                    target_variant = variant
                                    break
                        
                        # If no size match or no size specified, take first variant with data
                        if not target_variant:
                            for variant in market_data:
                                if variant.get('lowestAskAmount') or variant.get('highestBidAmount'):
                                    target_variant = variant
                                    break
                        
                        if not target_variant and market_data:
                            target_variant = market_data[0]  # Fallback to first variant
                        
                        market_info = target_variant or {}
                    elif isinstance(market_data, dict):
                        market_info = market_data
                    else:
                        market_info = {}
                    
                    # Use correct StockX API field names
                    stockx_ask = market_info.get('lowestAskAmount')
                    stockx_bid = market_info.get('highestBidAmount')
                    stockx_last_sale = None  # Not available in this endpoint
                    stockx_last_sale_date = None  # Not available in this endpoint
                    
                    print(f"   💰 Ask: ${stockx_ask or 'N/A'} | Bid: ${stockx_bid or 'N/A'} | Last: ${stockx_last_sale or 'N/A'}")
                
                # Calculate profit metrics
                profit_metrics = self.calculate_profit_metrics(ebay_price, stockx_bid, stockx_ask)
                
                # Add StockX data to row
                row['stockx_product_title'] = product['title']
                row['stockx_product_id'] = product_id
                row['stockx_lowest_ask'] = stockx_ask or ''
                row['stockx_highest_bid'] = stockx_bid or ''
                row['stockx_last_sale'] = stockx_last_sale or ''
                row['stockx_last_sale_date'] = stockx_last_sale_date or ''
                row['stockx_match_confidence'] = 'High' if search_result.get('exact_match') else 'Medium'
                row['stockx_total_found'] = search_result.get('total_found', 0)
                
                # Add profit calculations
                row['ask_over_ebay'] = profit_metrics['ask_over_ebay'] or ''
                row['bid_over_ebay'] = profit_metrics['bid_over_ebay'] or ''
                row['ask_profit_pct'] = profit_metrics['ask_profit_pct'] or ''
                row['bid_profit_pct'] = profit_metrics['bid_profit_pct'] or ''
                
                processed_rows.append(row)
                self.processed_count += 1
                
                if stockx_ask or stockx_bid:
                    self.matches_found += 1
                
                # Rate limiting
                time.sleep(0.5)  # Be nice to the API
        
        # Write enhanced CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(processed_rows)
        
        # Summary
        print(f"\n" + "=" * 60)
        print(f"📊 PROCESSING COMPLETE!")
        print(f"✅ Processed: {self.processed_count} items")
        print(f"🎯 Found StockX matches: {self.matches_found} items")
        print(f"💾 Enhanced CSV saved: {output_file}")
        print(f"🔥 Ready for profit analysis!")
        
        return output_file
    
    def analyze_profits(self, csv_file):
        """Analyze profit opportunities from the enhanced CSV"""
        print(f"\n📈 PROFIT ANALYSIS")
        print("=" * 40)
        
        profitable_items = []
        
        with open(csv_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                ask_profit = row.get('ask_profit_pct', '')
                bid_profit = row.get('bid_profit_pct', '')
                
                try:
                    ask_profit_float = float(ask_profit) if ask_profit else None
                    bid_profit_float = float(bid_profit) if bid_profit else None
                    
                    if ask_profit_float and ask_profit_float > 10:  # 10% profit threshold
                        profitable_items.append({
                            'title': row.get('title', ''),
                            'ebay_price': row.get('listing_price', ''),
                            'stockx_ask': row.get('stockx_lowest_ask', ''),
                            'profit_pct': ask_profit_float
                        })
                        
                except (ValueError, TypeError):
                    continue
        
        # Sort by profit percentage
        profitable_items.sort(key=lambda x: x['profit_pct'], reverse=True)
        
        print(f"🚀 Found {len(profitable_items)} profitable opportunities (>10% margin):")
        print()
        
        for i, item in enumerate(profitable_items[:10], 1):  # Top 10
            print(f"{i:2d}. {item['title'][:50]}...")
            print(f"    eBay: ${item['ebay_price']} → StockX: ${item['stockx_ask']} ({item['profit_pct']:.1f}% profit)")
            print()

def main():
    """Main function to run the eBay-StockX pricing tool"""
    import sys
    
    if len(sys.argv) < 2:
        print("📊 eBay-StockX Price Comparison Tool")
        print("=" * 40)
        print("Usage: python ebay_stockxpricing.py <csv_file>")
        print()
        print("Example:")
        print("python ebay_stockxpricing.py csv_inputs/jordan1_auctions_3h_20250630_150158.csv")
        return
    
    input_file = sys.argv[1]
    
    if not Path(input_file).exists():
        print(f"❌ Error: File not found: {input_file}")
        return
    
    # Process the CSV
    pricer = EbayStockXPricer()
    
    try:
        output_file = pricer.process_csv(input_file)
        pricer.analyze_profits(output_file)
        
    except Exception as e:
        print(f"❌ Error processing file: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 