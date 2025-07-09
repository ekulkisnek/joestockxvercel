#!/usr/bin/env python3
"""
📊 Inventory StockX Analyzer
Flexible tool to analyze any inventory CSV format and get StockX pricing data
"""

import csv
import json
import re
import time
import sys
import os
import requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our existing StockX client
from smart_stockx_client import SmartStockXClient

class InventoryItem:
    """Represents a single inventory item"""
    def __init__(self, shoe_name: str, size: str = None, price: str = None, condition: str = None):
        self.shoe_name = shoe_name.strip() if shoe_name else ""
        self.size = size.strip() if size else ""
        self.price = price.strip() if price else ""
        self.condition = condition.strip() if condition else ""

        # StockX data
        self.stockx_bid = None
        self.stockx_ask = None
        self.stockx_sku = None
        self.stockx_url = None
        self.stockx_size = None
        self.stockx_shoe_name = None
        self.size_match_uncertain = False  # Flag for uncertain matches

        # Profit calculations
        self.bid_profit = None
        self.ask_profit = None

class InventoryStockXAnalyzer:
    def __init__(self):
        """Initialize with StockX client"""
        self.client = SmartStockXClient()
        self.processed_count = 0
        self.matches_found = 0
        self.cache = {}
        
        # Set correct token file path - check if we're in pricing_tools directory
        if os.path.basename(os.getcwd()) == 'pricing_tools':
            self.client.token_file = '../tokens_full_scope.json'
        else:
            self.client.token_file = 'tokens_full_scope.json'

    def parse_csv_flexible(self, csv_file: str) -> List[InventoryItem]:
        """Parse CSV file flexibly - handles multiple formats"""
        items = []

        with open(csv_file, 'r', encoding='utf-8') as file:
            lines = list(csv.reader(file))

        current_shoe = None

        for i, row in enumerate(lines):
            if not row or all(not cell.strip() for cell in row):
                continue

            first_cell = row[0].strip() if row[0] else ""

            # Format 1: Complete row format like "Nike Dunk Reverse Panda,M10,Brand New,,60,"
            if self._is_complete_item_row(row):
                shoe_name = first_cell
                size = ""
                condition = ""
                price = ""

                # Parse remaining columns
                for j in range(1, len(row)):
                    cell = row[j].strip() if row[j] else ""
                    if not cell:
                        continue

                    if self._looks_like_size(cell) and not size:
                        size = cell
                    elif self._looks_like_condition(cell) and not condition:
                        condition = cell
                    elif self._looks_like_price(cell) and not price:
                        price = cell

                if shoe_name:  # Only add if we have a shoe name
                    items.append(InventoryItem(
                        shoe_name=shoe_name,
                        size=size,
                        price=price,
                        condition=condition
                    ))

            # Format 2: Traditional format - shoe name in one row, sizes/prices below
            elif self._looks_like_shoe_name(first_cell):
                current_shoe = first_cell

                # Check if this row also contains size and price
                if len(row) > 1:
                    size = ""
                    price = ""

                    for j in range(1, len(row)):
                        cell = row[j].strip() if row[j] else ""
                        if self._looks_like_size(cell) and not size:
                            size = cell
                        elif self._looks_like_price(cell) and not price:
                            price = cell

                    if size:  # If we found size in the same row
                        items.append(InventoryItem(
                            shoe_name=current_shoe,
                            size=size,
                            price=price
                        ))

            # Format 2 continued: Size/price rows under shoe name
            elif self._looks_like_size(first_cell) and current_shoe:
                size = first_cell
                price = ""

                # Look for price in this row
                for j in range(1, len(row)):
                    cell = row[j].strip() if row[j] else ""
                    if self._looks_like_price(cell):
                        price = cell
                        break

                items.append(InventoryItem(
                    shoe_name=current_shoe,
                    size=size,
                    price=price
                ))

        print(f"✅ Parsed {len(items)} inventory items")
        return items

    def _is_complete_item_row(self, row: List[str]) -> bool:
        """Check if this row contains a complete item (Format 1)"""
        if len(row) < 2:
            return False

        first_cell = row[0].strip() if row[0] else ""
        if not self._looks_like_shoe_name(first_cell):
            return False

        # Look for size in second column (like M10, 5Y, W11, etc.)
        second_cell = row[1].strip() if len(row) > 1 and row[1] else ""
        if self._looks_like_size(second_cell):
            return True

        # Look for size anywhere in first few columns
        for j in range(1, min(4, len(row))):
            cell = row[j].strip() if row[j] else ""
            if self._looks_like_size(cell):
                return True

        return False

    def _looks_like_condition(self, text: str) -> bool:
        """Check if text looks like a condition"""
        if not text:
            return False

        condition_keywords = [
            'brand new', 'used', 'vnds', 'og all', 'no box', 'damaged box', 
            'rep box', 'no lid', 'special box', 'missing'
        ]

        text_lower = text.lower()
        return any(keyword in text_lower for keyword in condition_keywords)

    def _looks_like_shoe_name(self, text: str) -> bool:
        """Check if text looks like a shoe name"""
        if not text or len(text) < 3:
            return False

        brands = ['jordan', 'nike', 'adidas', 'yeezy', 'dunk', 'air', 'sb']
        text_lower = text.lower()

        return any(brand in text_lower for brand in brands)

    def _looks_like_size(self, text: str) -> bool:
        """Check if text looks like a shoe size"""
        if not text:
            return False

        text_clean = text.strip().upper()

        size_patterns = [
            r'^\d+\.?\d*[YCW]?$',           # 10, 10.5, 10Y, 10C, 10W
            r'^[MW]\d+\.?\d*$',             # M10, W10, M10.5
            r'^\d+\.?\d*\s*-\s*\d+$',       # 10 - 12, size ranges
            r'^\d+Y$',                      # 5Y (youth)
            r'^\d+C$',                      # 10C (child)
            r'^\d+W$',                      # 10W (women)
        ]

        for pattern in size_patterns:
            if re.match(pattern, text_clean):
                return True

        return False

    def _looks_like_price(self, text: str) -> bool:
        """Check if text looks like a price"""
        if not text:
            return False

        cleaned = re.sub(r'[$,]', '', text.strip())

        try:
            price = float(cleaned)
            return 10 <= price <= 10000
        except ValueError:
            return False

    def _parse_price(self, price_str: str) -> Optional[float]:
        """Parse price string to float"""
        if not price_str:
            return None

        try:
            # Remove currency symbols and whitespace
            clean_price = re.sub(r'[$,]', '', price_str.strip())
            return float(clean_price)
        except (ValueError, AttributeError):
            return None

    def normalize_size(self, size: str) -> Tuple[str, str]:
        """Normalize size format and determine category"""
        if not size:
            return "", "men"

        size_clean = size.strip().upper()

        # Handle size ranges
        if ' - ' in size_clean:
            size_clean = size_clean.split(' - ')[0].strip()

        # Handle different size formats
        if size_clean.endswith('Y'):
            return size_clean, "gs"  # Grade School
        elif size_clean.endswith('C'):
            return size_clean, "ps"  # Preschool
        elif size_clean.endswith('W') or size_clean.startswith('W'):
            numeric_size = re.sub(r'[WM]', '', size_clean)
            return numeric_size, "women"
        elif size_clean.startswith('M'):
            numeric_size = re.sub(r'[WM]', '', size_clean)
            return numeric_size, "men"
        else:
            return size_clean, "men"

    def clean_shoe_name_for_search(self, shoe_name: str) -> str:
        """Clean shoe name for StockX search"""
        cleaned = shoe_name.strip()

        suffixes_to_remove = [
            r'\s*\([^)]*\)$',
            r'\s*-\s*[A-Z0-9]+$',
        ]

        for suffix in suffixes_to_remove:
            cleaned = re.sub(suffix, '', cleaned)

        replacements = {
            'OG': '',
            'RETRO': '',
            '1 85': '1',
        }

        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)

        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        return cleaned[:60]

    def get_product_variants(self, product_id: str) -> List[Dict]:
        """Get all variants for a product"""
        try:
            headers = self.client._get_headers()
            response = requests.get(
                f'{self.client.base_url}/catalog/products/{product_id}/variants',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"   ❌ Error getting variants: {response.status_code}")
                return []

        except Exception as e:
            print(f"   ❌ Error getting variants: {str(e)}")
            return []

    def find_variant_by_size(self, variants: List[Dict], target_size: str, size_category: str) -> Tuple[Optional[Dict], bool]:
        """Find variant matching the target size, return (variant, is_uncertain)"""
        target_size_clean = target_size.replace('.0', '').strip()

        # First try exact matches
        for variant in variants:
            # Check variantValue first (most direct)
            variant_value = str(variant.get('variantValue', '')).strip()
            if variant_value == target_size or variant_value == target_size_clean:
                return variant, False

            # Check default conversion
            size_chart = variant.get('sizeChart', {})
            default_conversion = size_chart.get('defaultConversion')
            if default_conversion:
                default_size = str(default_conversion.get('size', '')).strip()
                if default_size == target_size or default_size == target_size_clean:
                    return variant, False

        # If no exact match, try uncertain matches with size suffixes
        return self._try_uncertain_size_match(variants, target_size_clean)

    def _try_uncertain_size_match(self, variants: List[Dict], target_size: str) -> Tuple[Optional[Dict], bool]:
        """Try uncertain size matching with different suffixes"""

        # Extract numeric part from target size
        numeric_size = re.sub(r'[^0-9.]', '', target_size)
        if not numeric_size:
            return None, False

        # Try different size suffixes that might match
        size_attempts = [
            f"{numeric_size}Y",    # Youth/GS
            f"{numeric_size}C",    # Child/PS  
            f"{numeric_size}W",    # Women's
            numeric_size,          # Plain numeric
        ]

        for attempt_size in size_attempts:
            for variant in variants:
                variant_value = str(variant.get('variantValue', '')).strip()

                if variant_value == attempt_size:
                    return variant, True  # Found but uncertain

                # Also check default conversion
                size_chart = variant.get('sizeChart', {})
                default_conversion = size_chart.get('defaultConversion')
                if default_conversion:
                    default_size = str(default_conversion.get('size', '')).strip()
                    if default_size == attempt_size:
                        return variant, True  # Found but uncertain

        return None, False

    def get_variant_market_data(self, product_id: str, variant_id: str) -> Optional[Dict]:
        """Get market data for specific variant"""
        try:
            headers = self.client._get_headers()
            response = requests.get(
                f'{self.client.base_url}/catalog/products/{product_id}/variants/{variant_id}/market-data',
                headers=headers,
                timeout=15
            )

            if response.status_code == 200:
                return response.json()
            else:
                print(f"   ❌ Market data error: {response.status_code}")
                return None

        except Exception as e:
            print(f"   ❌ Market data error: {str(e)}")
            return None

    def search_stockx_for_item(self, item: InventoryItem) -> bool:
        """Search StockX for inventory item"""
        search_query = self.clean_shoe_name_for_search(item.shoe_name)
        size_normalized, size_category = self.normalize_size(item.size)

        cache_key = f"{search_query}_{size_normalized}_{size_category}"

        if cache_key in self.cache:
            cached_result = self.cache[cache_key]
            if cached_result:
                item.stockx_bid = f"${cached_result['bid']}" if cached_result['bid'] else None
                item.stockx_ask = f"${cached_result['ask']}" if cached_result['ask'] else None
                item.stockx_sku = cached_result.get('sku')
                item.stockx_url = cached_result.get('url')
                item.stockx_size = cached_result.get('size')
                item.stockx_shoe_name = cached_result.get('shoe_name')
                item.bid_profit = f"${cached_result['bid_profit']:.2f}" if cached_result.get('bid_profit') is not None else None
                item.ask_profit = f"${cached_result['ask_profit']:.2f}" if cached_result.get('ask_profit') is not None else None
                return True
            return False

        try:
            print(f"🔍 Searching: '{search_query}' (Size: {size_normalized} {size_category})")

            search_results = self.client.search_products(search_query, page_size=10)

            if not search_results['products']:
                print("   ❌ No products found")
                self.cache[cache_key] = None
                return False

            best_product = self._find_best_product_match(
                search_results['products'], 
                search_query, 
                size_category
            )

            if not best_product:
                print("   ❌ No suitable product match")
                self.cache[cache_key] = None
                return False

            print(f"   ✅ Found: {best_product['title'][:50]}...")

            # Get variants for the product
            variants = self.get_product_variants(best_product['id'])

            if not variants:
                print("   ❌ No variants found")
                self.cache[cache_key] = None
                return False

            # Find matching variant by size
            matching_variant, is_uncertain = self.find_variant_by_size(variants, size_normalized, size_category)

            if not matching_variant:
                print(f"   ❌ Size {size_normalized} not found")
                # Debug: show available sizes
                available_sizes = [str(v.get('variantValue', '')) for v in variants[:10]]
                print(f"   📏 Available sizes: {', '.join(available_sizes)}")
                self.cache[cache_key] = None
                return False

            variant_id = matching_variant['variantId']
            variant_size = matching_variant.get('variantValue', size_normalized)

            if is_uncertain:
                print(f"   🎯 Found variant: {variant_size} (ID: {variant_id[:8]}...) ⚠️ UNCERTAIN MATCH")
                item.size_match_uncertain = True
            else:
                print(f"   🎯 Found variant: {variant_size} (ID: {variant_id[:8]}...)")

            # Get market data for the specific variant
            market_data = self.get_variant_market_data(best_product['id'], variant_id)

            if not market_data:
                print("   ❌ No market data available")
                self.cache[cache_key] = None
                return False

            # Extract pricing data
            bid_amount = market_data.get('highestBidAmount')
            ask_amount = market_data.get('lowestAskAmount')

            # Calculate profit margins
            original_price = self._parse_price(item.price)
            bid_profit = None
            ask_profit = None

            if original_price and bid_amount:
                bid_profit = float(bid_amount) - original_price

            if original_price and ask_amount:
                ask_profit = float(ask_amount) - original_price

            # Construct StockX URL using urlKey
            stockx_url = None
            url_key = best_product.get('url_key')
            if url_key:
                stockx_url = f"https://stockx.com/{url_key}"

            result = {
                'bid': bid_amount,
                'ask': ask_amount,
                'sku': best_product.get('style_id', ''),
                'url': stockx_url,
                'size': str(variant_size),
                'shoe_name': best_product['title'],
                'bid_profit': bid_profit,
                'ask_profit': ask_profit
            }

            item.stockx_bid = f"${result['bid']}" if result['bid'] else None
            item.stockx_ask = f"${result['ask']}" if result['ask'] else None
            item.stockx_sku = result['sku']
            item.stockx_url = result['url']
            item.stockx_size = result['size']
            item.stockx_shoe_name = result['shoe_name']
            item.bid_profit = f"${result['bid_profit']:.2f}" if result['bid_profit'] is not None else None
            item.ask_profit = f"${result['ask_profit']:.2f}" if result['ask_profit'] is not None else None

            self.cache[cache_key] = result

            print(f"   💰 Bid: ${result['bid'] or 'N/A'} | Ask: ${result['ask'] or 'N/A'} | Size: {result['size']}")
            return True

        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            self.cache[cache_key] = None
            return False

    def _find_best_product_match(self, products: List[Dict], search_query: str, size_category: str) -> Optional[Dict]:
        """Find best matching product"""
        search_lower = search_query.lower()

        scored_products = []

        for product in products:
            title_lower = product['title'].lower()

            score = 0
            search_words = search_lower.split()
            title_words = title_lower.split()

            for word in search_words:
                if word in title_words:
                    score += 2
                elif any(word in title_word for title_word in title_words):
                    score += 1

            if 'jordan 1' in search_lower and 'jordan 1' in title_lower:
                score += 5
            elif 'jordan 4' in search_lower and 'jordan 4' in title_lower:
                score += 5
            elif 'dunk' in search_lower and 'dunk' in title_lower:
                score += 3
            elif 'yeezy' in search_lower and 'yeezy' in title_lower:
                score += 3

            if size_category == "gs" and ('gs' in title_lower or 'grade school' in title_lower):
                score += 3
            elif size_category == "ps" and ('ps' in title_lower or 'preschool' in title_lower):
                score += 3
            elif size_category == "women" and ("women" in title_lower or " w " in title_lower):
                score += 2

            scored_products.append((score, product))

        scored_products.sort(key=lambda x: x[0], reverse=True)

        if scored_products and scored_products[0][0] > 0:
            return scored_products[0][1]

        return None

    def process_inventory(self, csv_file: str, output_file: str = None) -> str:
        """Process entire inventory"""
        if not output_file:
            input_path = Path(csv_file)
            output_file = input_path.parent / f"stockx_enhanced_{input_path.name}"

        print(f"📊 Processing inventory: {csv_file}")
        print(f"💾 Output will be saved to: {output_file}")
        print("=" * 80)

        items = self.parse_csv_flexible(csv_file)

        if not items:
            print("❌ No inventory items found")
            return ""

        print(f"\n🔍 Processing {len(items)} items...")

        for i, item in enumerate(items, 1):
            print(f"\n[{i}/{len(items)}] {item.shoe_name} - Size {item.size}")

            success = self.search_stockx_for_item(item)
            if success:
                self.matches_found += 1

            self.processed_count += 1

            # Optimal rate limiting based on testing: 2 seconds = 30 requests/min
            time.sleep(2.0)

            # Progress update every 15 items
            if i % 15 == 0:
                print(f"   📊 Progress: {i}/{len(items)} items processed ({self.matches_found} matches found)")

        self._write_enhanced_csv(items, output_file)

        print(f"\n" + "=" * 80)
        print(f"📊 PROCESSING COMPLETE!")
        print(f"✅ Processed: {self.processed_count} items")
        print(f"🎯 Found StockX matches: {self.matches_found} items")
        print(f"💾 Enhanced CSV saved: {output_file}")

        return output_file

    def _write_enhanced_csv(self, items: List[InventoryItem], output_file: str):
        """Write enhanced CSV"""
        base_columns = ['original_shoe_name', 'original_size', 'original_price', 'condition']
        profit_columns = ['bid_profit', 'ask_profit']
        stockx_columns = ['stockx_bid', 'stockx_ask', 'stockx_sku', 'stockx_url', 
                         'stockx_size', 'size_match_uncertain', 'stockx_shoe_name']

        all_columns = base_columns + profit_columns + stockx_columns

        with open(output_file, 'w', newline='', encoding='utf-8') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=all_columns)
            writer.writeheader()

            for item in items:
                row = {
                    'original_shoe_name': item.shoe_name,
                    'original_size': item.size,
                    'original_price': item.price,
                    'condition': item.condition,
                    'bid_profit': item.bid_profit or '',
                    'ask_profit': item.ask_profit or '',
                    'stockx_bid': item.stockx_bid or '',
                    'stockx_ask': item.stockx_ask or '',
                    'stockx_sku': item.stockx_sku or '',
                    'stockx_url': item.stockx_url or '',
                    'stockx_size': item.stockx_size or '',
                    'size_match_uncertain': 'YES' if item.size_match_uncertain else '',
                    'stockx_shoe_name': item.stockx_shoe_name or ''
                }
                writer.writerow(row)

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("📊 Inventory StockX Analyzer")
        print("=" * 40)
        print("Usage: python inventory_stockx_analyzer.py <csv_file>")
        return

    input_file = sys.argv[1]

    if not Path(input_file).exists():
        print(f"❌ Error: File not found: {input_file}")
        return

    analyzer = InventoryStockXAnalyzer()

    try:
        output_file = analyzer.process_inventory(input_file)
        print(f"\n🎉 Analysis complete! Check {output_file} for results.")

    except Exception as e:
        print(f"❌ Error processing file: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()