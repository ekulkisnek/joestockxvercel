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

# Configure immediate output flushing for real-time web interface progress
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

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
        # Alias pricing data
        self.lowest_consigned = None
        self.last_consigned_price = None
        self.last_consigned_date = None
        self.lowest_with_you = None
        self.last_with_you_price = None
        self.last_with_you_date = None
        self.consignment_price = None
        self.ship_to_verify_price = None
        # StockX metadata
        self.stockx_sku = None
        self.stockx_url = None
        self.stockx_size = None
        self.stockx_shoe_name = None

        # Profit calculations
        self.bid_profit = None
        self.ask_profit = None

class InventoryStockXAnalyzer:
    def __init__(self):
        """Initialize with StockX client"""
        # Initialize client without auto-authentication first
        self.client = SmartStockXClient(auto_authenticate=False)
        self.processed_count = 0
        self.matches_found = 0
        self.cache = {}
        
        # Set correct token file path - check if we're in pricing_tools directory
        if os.path.basename(os.getcwd()) == 'pricing_tools':
            self.client.token_file = '../tokens_full_scope.json'
        else:
            self.client.token_file = 'tokens_full_scope.json'
        
        # Now ensure authentication with correct path
        self.client._ensure_authentication()

    def parse_csv_flexible(self, csv_file: str) -> List[InventoryItem]:
        """Parse CSV file flexibly - handles multiple formats"""
        items = []

        # Read and parse as CSV
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

                item = InventoryItem(shoe_name, size, price, condition)
                items.append(item)

            # Format 2: Group header with sizes below
            elif self._looks_like_shoe_name(first_cell) and len(row) <= 2:
                current_shoe = first_cell
                # Check if there's additional data in the same row
                if len(row) > 1 and row[1].strip():
                    # This might be price info like "Nike Dunk Low Blueberry,60"
                    price_candidate = row[1].strip()
                    if self._looks_like_price(price_candidate):
                        # This row has shoe name and price, sizes will be below
                        continue

            # Format 3: Size row under group header  
            elif current_shoe and self._looks_like_size_row(row):
                for cell in row:
                    cell = cell.strip()
                    if self._looks_like_size(cell):
                        condition = ""
                        price = ""
                        
                        # Look for condition and price in the same row
                        for other_cell in row:
                            other_cell = other_cell.strip()
                            if other_cell != cell:  # Don't re-process the size cell
                                if self._looks_like_condition(other_cell) and not condition:
                                    condition = other_cell
                                elif self._looks_like_price(other_cell) and not price:
                                    price = other_cell

                        item = InventoryItem(current_shoe, cell, price, condition)
                        items.append(item)

            # Format 4: Standard CSV with headers
            elif i == 0 and self._looks_like_header_row(row):
                # This is a header row, skip it
                continue
            elif i > 0 and len(row) >= 2:
                # Standard CSV format: shoe_name, size, condition, price (flexible order)
                shoe_name = first_cell
                size = ""
                condition = ""
                price = ""

                for cell in row[1:]:  # Skip first cell (shoe name)
                    cell = cell.strip()
                    if not cell:
                        continue
                    
                    if self._looks_like_size(cell) and not size:
                        size = cell
                    elif self._looks_like_condition(cell) and not condition:
                        condition = cell
                    elif self._looks_like_price(cell) and not price:
                        price = cell

                if shoe_name:  # Only add if we have a shoe name
                    item = InventoryItem(shoe_name, size, price, condition)
                    items.append(item)

        return items

    def parse_pasted_list(self, text: str) -> List[InventoryItem]:
        """Parse pasted list format like 'Jordan 3 white cement 88 - size 11 ($460)'"""
        items = []
        
        # Split by lines and clean up
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        for line in lines:
            # Skip header lines or empty lines
            if not line or line.upper().startswith('SHOE LIST') or line.startswith('='):
                continue
            
            # Parse each line using regex
            # Pattern: shoe_name - size size_info (price) [optional notes]
            import re
            
            # First try to find the price in parentheses
            price_match = re.search(r'\(\$?(\d+(?:\.\d{2})?)\)', line)
            price = price_match.group(1) if price_match else ""
            
            # Remove price and any notes after it
            line_without_price = re.sub(r'\(\$?\d+(?:\.\d{2})?\).*$', '', line).strip()
            
            # Find size information - look for "size" or "- size"
            size_pattern = r'(?:-\s*)?size\s+(.*?)(?:\s*\(|$)'
            size_match = re.search(size_pattern, line_without_price, re.IGNORECASE)
            
            if not size_match:
                print(f"⚠️ Could not parse size from: {line}")
                continue
                
            size_info = size_match.group(1).strip()
            
            # Extract shoe name (everything before the size part)
            shoe_name = re.sub(size_pattern, '', line_without_price, flags=re.IGNORECASE).strip()
            # Clean up trailing dashes or spaces
            shoe_name = re.sub(r'\s*-\s*$', '', shoe_name).strip()
            
            # Parse sizes - handle complex formats like "11.5x2, 12" or "4.5x13, 5x9, 5.5x4"
            sizes = self._parse_size_list(size_info)
            
            # Create items for each size
            for size, quantity in sizes:
                # Determine condition based on context
                condition = "Brand New"  # Default for DS (deadstock)
                if "used" in line.lower():
                    condition = "Used"
                elif "vnds" in line.lower():
                    condition = "Very Near Deadstock"
                
                item = InventoryItem(
                    shoe_name=shoe_name,
                    size=size,
                    price=price,
                    condition=condition
                )
                items.append(item)
                
                # If quantity > 1, add multiple entries
                for _ in range(quantity - 1):
                    duplicate_item = InventoryItem(
                        shoe_name=shoe_name,
                        size=size,
                        price=price,
                        condition=condition
                    )
                    items.append(duplicate_item)
        
        return items
    
    def _parse_size_list(self, size_info: str) -> List[Tuple[str, int]]:
        """Parse size list like '11.5x2, 12' or '4.5x13, 5x9, 5.5x4' into (size, quantity) pairs"""
        sizes = []
        
        # Split by commas
        size_parts = [part.strip() for part in size_info.split(',')]
        
        for part in size_parts:
            # Handle formats like "11.5x2" or just "11"
            if 'x' in part:
                # Format: 11.5x2
                size_str, qty_str = part.split('x', 1)
                size = size_str.strip()
                try:
                    quantity = int(qty_str.strip())
                except ValueError:
                    quantity = 1
            else:
                # Just a size like "11" or "11.5"
                size = part.strip()
                quantity = 1
            
            sizes.append((size, quantity))
        
        return sizes

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
        """Find variant matching the target size"""
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

        # Try extended matching with size suffixes (no longer marked as uncertain)
        numeric_size = re.sub(r'[^0-9.]', '', target_size_clean)
        if numeric_size:
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
                        return variant, False

                    # Also check default conversion
                    size_chart = variant.get('sizeChart', {})
                    default_conversion = size_chart.get('defaultConversion')
                    if default_conversion:
                        default_size = str(default_conversion.get('size', '')).strip()
                        if default_size == attempt_size:
                            return variant, False

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



    def get_alias_pricing_data(self, shoe_name: str, size: str) -> Optional[Dict]:
        """Get pricing data from Alias API for the requested data points"""
        try:
            import requests
            
            # Alias API configuration
            api_key = "goatapi_167AEOZwPmcFAwZ2RbHv7AaGfSYpdF2wq1zdxzT"
            base_url = "https://api.alias.org/api/v1"
            
            headers = {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
            
            # Parse size to float
            try:
                size_float = float(size.replace('Y', '').replace('W', ''))
            except (ValueError, AttributeError):
                size_float = 10.0  # Default size if parsing fails
            
            # Step 1: Search for the shoe in Alias catalog
            print(f"   🔍 Searching Alias for: {shoe_name}")
            search_response = requests.get(
                f"{base_url}/catalog",
                headers=headers,
                params={'query': shoe_name, 'limit': 1},
                timeout=15
            )
            
            if search_response.status_code != 200:
                print(f"   ❌ Alias search failed: {search_response.status_code}")
                return None
                
            search_data = search_response.json()
            catalog_items = search_data.get('catalog_items', [])
            
            if not catalog_items:
                print(f"   ❌ No Alias catalog match found")
                return None
            
            catalog_id = catalog_items[0].get('catalog_id')
            if not catalog_id:
                print(f"   ❌ No catalog ID found")
                return None
            
            print(f"   ✅ Found Alias match: {catalog_items[0].get('name', 'Unknown')}")
            
            # Step 2: Get pricing data with all the requested parameters
            params = {
                'catalog_id': catalog_id,
                'size': size_float,
                'product_condition': 'PRODUCT_CONDITION_NEW',
                'packaging_condition': 'PACKAGING_CONDITION_GOOD_CONDITION'
            }
            
            # Get overall availability (ship to verify + lowest with you)
            overall_response = requests.get(
                f"{base_url}/pricing_insights/availability",
                headers=headers,
                params=params,
                timeout=15
            )
            
            # Get consigned availability (lowest consigned + consignment price)
            consigned_params = params.copy()
            consigned_params['consigned'] = True
            consigned_response = requests.get(
                f"{base_url}/pricing_insights/availability",
                headers=headers,
                params=consigned_params,
                timeout=15
            )
            
            # Get recent sales for last with you and last consigned
            sales_response = requests.get(
                f"{base_url}/pricing_insights/recent_sales",
                headers=headers,
                params={**params, 'limit': 10},
                timeout=15
            )
            
            # Get recent consigned sales
            consigned_sales_params = params.copy()
            consigned_sales_params.update({'consigned': True, 'limit': 10})
            consigned_sales_response = requests.get(
                f"{base_url}/pricing_insights/recent_sales",
                headers=headers,
                params=consigned_sales_params,
                timeout=15
            )
            
            # Process the responses
            overall_data = overall_response.json().get('availability', {}) if overall_response.status_code == 200 else {}
            consigned_data = consigned_response.json().get('availability', {}) if consigned_response.status_code == 200 else {}
            sales_data = sales_response.json().get('recent_sales', []) if sales_response.status_code == 200 else []
            consigned_sales_data = consigned_sales_response.json().get('recent_sales', []) if consigned_sales_response.status_code == 200 else []
            
            # Extract the specific data points you requested
            def cents_to_dollars(cents):
                if cents is None:
                    return None
                try:
                    return float(cents) / 100
                except (ValueError, TypeError):
                    return None
            
            # Get last sale data
            last_sale = sales_data[0] if sales_data else {}
            last_consigned = consigned_sales_data[0] if consigned_sales_data else {}
            
            result = {
                # Ship to verify price
                'ship_to_verify_price': cents_to_dollars(overall_data.get('lowest_listing_price_cents')),
                
                # Consignment price  
                'consignment_price': cents_to_dollars(consigned_data.get('lowest_listing_price_cents')),
                
                # Lowest with you (overall lowest)
                'lowest_with_you': cents_to_dollars(overall_data.get('lowest_listing_price_cents')),
                
                # Lowest consigned
                'lowest_consigned': cents_to_dollars(consigned_data.get('lowest_listing_price_cents')),
                
                # Last with you (most recent sale)
                'last_with_you_price': cents_to_dollars(last_sale.get('price_cents')),
                'last_with_you_date': last_sale.get('purchased_at'),
                
                # Last consigned
                'last_consigned_price': cents_to_dollars(last_consigned.get('price_cents')),
                'last_consigned_date': last_consigned.get('purchased_at'),
            }
            
            print(f"   💰 Alias data: Ship ${result['ship_to_verify_price'] or 'N/A'} | Consigned ${result['consignment_price'] or 'N/A'}")
            
            return result
            
        except Exception as e:
            print(f"   ❌ Alias API error: {str(e)}")
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
                # Add cached Alias data
                if cached_result.get('lowest_consigned'):
                    item.lowest_consigned = f"${cached_result['lowest_consigned']:.2f}"
                else:
                    item.lowest_consigned = None
                if cached_result.get('last_consigned_price'):
                    item.last_consigned_price = f"${cached_result['last_consigned_price']:.2f}"
                else:
                    item.last_consigned_price = None
                item.last_consigned_date = cached_result.get('last_consigned_date')
                if cached_result.get('lowest_with_you'):
                    item.lowest_with_you = f"${cached_result['lowest_with_you']:.2f}"
                else:
                    item.lowest_with_you = None
                if cached_result.get('last_with_you_price'):
                    item.last_with_you_price = f"${cached_result['last_with_you_price']:.2f}"
                else:
                    item.last_with_you_price = None
                item.last_with_you_date = cached_result.get('last_with_you_date')
                if cached_result.get('consignment_price'):
                    item.consignment_price = f"${cached_result['consignment_price']:.2f}"
                else:
                    item.consignment_price = None
                if cached_result.get('ship_to_verify_price'):
                    item.ship_to_verify_price = f"${cached_result['ship_to_verify_price']:.2f}"
                else:
                    item.ship_to_verify_price = None
                item.stockx_sku = cached_result.get('sku')
                item.stockx_url = cached_result.get('url')
                item.stockx_size = cached_result.get('size')
                item.stockx_shoe_name = cached_result.get('shoe_name')
                item.bid_profit = f"${cached_result['bid_profit']:.2f}" if cached_result.get('bid_profit') is not None else None
                item.ask_profit = f"${cached_result['ask_profit']:.2f}" if cached_result.get('ask_profit') is not None else None
                return True
            return False

        try:
            print(f"🔍 Searching: '{search_query}' (Size: {size_normalized} {size_category})", flush=True)

            search_results = self.client.search_products(search_query, page_size=10)

            if not search_results['products']:
                print("   ❌ No products found", flush=True)
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

            print(f"   ✅ Found: {best_product['title'][:50]}...", flush=True)

            # Get variants for the product
            variants = self.get_product_variants(best_product['id'])

            if not variants:
                print("   ❌ No variants found")
                self.cache[cache_key] = None
                return False

            # Find matching variant by size
            matching_variant, _ = self.find_variant_by_size(variants, size_normalized, size_category)

            if not matching_variant:
                print(f"   ❌ Size {size_normalized} not found", flush=True)
                # Debug: show available sizes
                available_sizes = [str(v.get('variantValue', '')) for v in variants[:10]]
                print(f"   📏 Available sizes: {', '.join(available_sizes)}", flush=True)
                self.cache[cache_key] = None
                return False

            variant_id = matching_variant['variantId']
            variant_size = matching_variant.get('variantValue', size_normalized)

            print(f"   🎯 Found variant: {variant_size} (ID: {variant_id[:8]}...)")

            # Get market data for the specific variant
            market_data = self.get_variant_market_data(best_product['id'], variant_id)

            if not market_data:
                print("   ❌ No market data available")
                self.cache[cache_key] = None
                return False
             
            # Get Alias pricing data for the requested data points
            # Try with original shoe name first, then StockX name if no match
            alias_data = self.get_alias_pricing_data(item.shoe_name, str(variant_size))
            if not alias_data:
                alias_data = self.get_alias_pricing_data(best_product['title'], str(variant_size))
            
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

            # Include Alias data in result
            result = {
                'bid': bid_amount,
                'ask': ask_amount,
                'lowest_consigned': alias_data.get('lowest_consigned') if alias_data else None,
                'last_consigned_price': alias_data.get('last_consigned_price') if alias_data else None,
                'last_consigned_date': alias_data.get('last_consigned_date') if alias_data else None,
                'lowest_with_you': alias_data.get('lowest_with_you') if alias_data else None,
                'last_with_you_price': alias_data.get('last_with_you_price') if alias_data else None,
                'last_with_you_date': alias_data.get('last_with_you_date') if alias_data else None,
                'consignment_price': alias_data.get('consignment_price') if alias_data else None,
                'ship_to_verify_price': alias_data.get('ship_to_verify_price') if alias_data else None,
                'sku': best_product.get('style_id', ''),
                'url': stockx_url,
                'size': str(variant_size),
                'shoe_name': best_product['title'],
                'bid_profit': bid_profit,
                'ask_profit': ask_profit
            }

            item.stockx_bid = f"${result['bid']}" if result['bid'] else None
            item.stockx_ask = f"${result['ask']}" if result['ask'] else None
            # Add Alias data to item
            if alias_data:
                item.lowest_consigned = f"${alias_data['lowest_consigned']:.2f}" if alias_data.get('lowest_consigned') else None
                item.last_consigned_price = f"${alias_data['last_consigned_price']:.2f}" if alias_data.get('last_consigned_price') else None
                item.last_consigned_date = alias_data.get('last_consigned_date')
                item.lowest_with_you = f"${alias_data['lowest_with_you']:.2f}" if alias_data.get('lowest_with_you') else None
                item.last_with_you_price = f"${alias_data['last_with_you_price']:.2f}" if alias_data.get('last_with_you_price') else None
                item.last_with_you_date = alias_data.get('last_with_you_date')
                item.consignment_price = f"${alias_data['consignment_price']:.2f}" if alias_data.get('consignment_price') else None
                item.ship_to_verify_price = f"${alias_data['ship_to_verify_price']:.2f}" if alias_data.get('ship_to_verify_price') else None
            else:
                item.lowest_consigned = None
                item.last_consigned_price = None
                item.last_consigned_date = None
                item.lowest_with_you = None
                item.last_with_you_price = None
                item.last_with_you_date = None
                item.consignment_price = None
                item.ship_to_verify_price = None
            item.stockx_sku = result['sku']
            item.stockx_url = result['url']
            item.stockx_size = result['size']
            item.stockx_shoe_name = result['shoe_name']
            item.bid_profit = f"${result['bid_profit']:.2f}" if result['bid_profit'] is not None else None
            item.ask_profit = f"${result['ask_profit']:.2f}" if result['ask_profit'] is not None else None

            self.cache[cache_key] = result

            print(f"   💰 Bid: ${result['bid'] or 'N/A'} | Ask: ${result['ask'] or 'N/A'} | Size: {result['size']}", flush=True)
            if alias_data:
                print(f"   📦 Alias: Ship ${alias_data['ship_to_verify_price'] or 'N/A'} | Consigned ${alias_data['consignment_price'] or 'N/A'}", flush=True)
            return True

        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
            # Check if this is a rate limiting error
            if "429" in str(e):
                return "RATE_LIMITED"
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
        """Process CSV inventory"""
        if not output_file:
            input_path = Path(csv_file)
            output_file = input_path.parent / f"stockx_enhanced_{input_path.name}"

        print(f"📊 Processing CSV inventory: {csv_file}", flush=True)
        print(f"💾 Output will be saved to: {output_file}", flush=True)
        print("=" * 80, flush=True)

        items = self.parse_csv_flexible(csv_file)

        if not items:
            print("❌ No inventory items found")
            return ""

        print(f"✅ Parsed {len(items)} inventory items", flush=True)
        
        # Use shared processing logic
        return self._process_items_and_save(items, output_file)

    def process_pasted_list(self, text_file: str, output_file: str = None) -> str:
        """Process pasted list format (separate from CSV processing)"""
        if not output_file:
            input_path = Path(text_file)
            output_file = input_path.parent / f"stockx_enhanced_{input_path.name}"

        print(f"📋 Processing pasted list: {text_file}", flush=True)
        print(f"💾 Output will be saved to: {output_file}", flush=True)
        print("=" * 80, flush=True)

        # Read as text and parse
        with open(text_file, 'r', encoding='utf-8') as file:
            content = file.read().strip()
        
        items = self.parse_pasted_list(content)

        if not items:
            print("❌ No inventory items found in pasted list")
            return ""

        print(f"✅ Parsed {len(items)} inventory items from pasted list", flush=True)
        
        # Continue with normal processing
        return self._process_items_and_save(items, output_file)
    
    def _process_items_and_save(self, items: List[InventoryItem], output_file: str) -> str:
        """Common processing logic for both CSV and pasted list"""
        print(f"\n🔍 Processing {len(items)} items...", flush=True)
        
        # Calculate estimated time (2 seconds per item)
        estimated_seconds = len(items) * 2
        estimated_minutes = estimated_seconds / 60
        print(f"⏱️  Estimated time: {estimated_minutes:.1f} minutes", flush=True)
        print(f"🔄 Processing at safe rate (30 items/minute) to avoid API limits", flush=True)
        print("=" * 80, flush=True)

        start_time = time.time()
        
        for i, item in enumerate(items, 1):
            print(f"\n[{i}/{len(items)}] {item.shoe_name} - Size {item.size}", flush=True)

            # Retry logic for rate limiting
            max_retries = 3
            retry_count = 0
            success = False
            
            while retry_count <= max_retries and not success:
                result = self.search_stockx_for_item(item)
                
                if result == "RATE_LIMITED":
                    retry_count += 1
                    if retry_count <= max_retries:
                        print(f"   ⏳ Rate limited! Waiting 2 seconds and retrying (attempt {retry_count}/{max_retries})...", flush=True)
                        time.sleep(2.0)  # Wait the normal interval
                    else:
                        print(f"   ❌ Max retries reached for rate limiting - skipping item", flush=True)
                        break
                elif result:
                    success = True
                    self.matches_found += 1
                    break
                else:
                    # Regular failure (not rate limited)
                    break

            self.processed_count += 1

            # Optimal rate limiting based on testing: 2 seconds = 30 requests/min
            # (only sleep if we didn't already sleep due to rate limiting)
            if not (result == "RATE_LIMITED" and retry_count > 0):
                time.sleep(2.0)

            # Progress update every 5 items with time estimation
            if i % 5 == 0:
                elapsed = time.time() - start_time
                remaining_items = len(items) - i
                remaining_time = (remaining_items * 2) / 60  # 2 seconds per item
                
                progress_percent = (i / len(items)) * 100
                print(f"   📊 Progress: {i}/{len(items)} ({progress_percent:.1f}%) - {self.matches_found} matches found", flush=True)
                print(f"   ⏱️  Estimated time remaining: {remaining_time:.1f} minutes", flush=True)

        self._write_enhanced_csv(items, output_file)

        print(f"\n" + "=" * 80, flush=True)
        print(f"📊 PROCESSING COMPLETE!", flush=True)
        print(f"✅ Processed: {self.processed_count} items", flush=True)
        print(f"🎯 Found StockX matches: {self.matches_found} items", flush=True)
        print(f"💾 Enhanced CSV saved: {output_file}", flush=True)

        return output_file

    def _write_enhanced_csv(self, items: List[InventoryItem], output_file: str):
        """Write enhanced CSV with reordered columns including Alias pricing data"""
        # Column order: basic info, then bid/ask prices, then Alias data, then everything else  
        all_columns = [
            'original_shoe_name', 'original_size', 'original_price', 'condition',
            'stockx_bid', 'stockx_ask',
            'bid_profit', 'ask_profit',
            'lowest_consigned', 'last_consigned_price', 'last_consigned_date', 
            'lowest_with_you', 'last_with_you_price', 'last_with_you_date',
            'consignment_price', 'ship_to_verify_price',
            'stockx_sku', 'stockx_url', 'stockx_size', 'stockx_shoe_name'
        ]

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
                    'lowest_consigned': item.lowest_consigned or '',
                    'last_consigned_price': item.last_consigned_price or '',
                    'last_consigned_date': item.last_consigned_date or '',
                    'lowest_with_you': item.lowest_with_you or '',
                    'last_with_you_price': item.last_with_you_price or '',
                    'last_with_you_date': item.last_with_you_date or '',
                    'consignment_price': item.consignment_price or '',
                    'ship_to_verify_price': item.ship_to_verify_price or '',
                    'stockx_sku': item.stockx_sku or '',
                    'stockx_url': item.stockx_url or '',
                    'stockx_size': item.stockx_size or '',
                    'stockx_shoe_name': item.stockx_shoe_name or ''
                }
                writer.writerow(row)

    def _looks_like_header_row(self, row: List[str]) -> bool:
        """Check if this row looks like a CSV header"""
        if not row:
            return False
        
        # Common header indicators
        header_words = ['shoe', 'name', 'size', 'price', 'condition', 'brand', 'style', 'sku', 'product']
        first_cell = row[0].lower().strip()
        
        # Check if first cell contains header-like words
        for word in header_words:
            if word in first_cell:
                return True
                
        # Check if row has typical header patterns
        if len(row) >= 2:
            for cell in row[:3]:  # Check first 3 cells
                cell_lower = cell.lower().strip()
                if any(word in cell_lower for word in header_words):
                    return True
                    
        return False

def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("📊 Inventory StockX Analyzer")
        print("=" * 40)
        print("Usage:")
        print("  python inventory_stockx_analyzer.py <csv_file>          # Process CSV file")
        print("  python inventory_stockx_analyzer.py --list <text_file>  # Process pasted list")
        print()
        print("Examples:")
        print("  python inventory_stockx_analyzer.py inventory.csv")
        print("  python inventory_stockx_analyzer.py --list my_shoes.txt")
        return

    # Check for pasted list flag
    if len(sys.argv) >= 3 and sys.argv[1] == '--list':
        input_file = sys.argv[2]
        if not Path(input_file).exists():
            print(f"❌ Error: File not found: {input_file}")
            return
            
        analyzer = InventoryStockXAnalyzer()
        try:
            output_file = analyzer.process_pasted_list(input_file)
            print(f"\n🎉 Pasted list analysis complete! Check {output_file} for results.")
        except Exception as e:
            print(f"❌ Error processing pasted list: {str(e)}")
            import traceback
            traceback.print_exc()
    else:
        # Regular CSV processing
        input_file = sys.argv[1]
        if not Path(input_file).exists():
            print(f"❌ Error: File not found: {input_file}")
            return

        analyzer = InventoryStockXAnalyzer()
        try:
            output_file = analyzer.process_inventory(input_file)
            print(f"\n🎉 CSV analysis complete! Check {output_file} for results.")
        except Exception as e:
            print(f"❌ Error processing CSV file: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()