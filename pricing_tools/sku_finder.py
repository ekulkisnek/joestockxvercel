#!/usr/bin/env python3
"""
🔍 SKU Finder - Find StockX SKUs for shoe names
Parses pasted shoe names and returns their corresponding StockX SKUs
"""

import sys
import os
import json
import time
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from smart_stockx_client import SmartStockXClient
import requests

class SKUFinder:
    def __init__(self):
        """Initialize SKU finder with StockX and Alias clients"""
        try:
            self.client = SmartStockXClient()
            print("✅ StockX client initialized successfully")
        except Exception as e:
            print(f"❌ Failed to initialize StockX client: {e}")
            self.client = None
            
        self.alias_api_key = "goatapi_167AEOZwPmcFAwZ2RbHv7AaGfSYpdF2wq1zdxzT"
        self.alias_base_url = "https://api.alias.org/api/v1"
        print("🔍 SKU Finder initialized with StockX + Alias integration")

    def parse_shoe_list(self, shoe_text: str) -> List[Dict]:
        """Parse pasted shoe text and extract shoe names"""
        print("📋 Parsing shoe list...")
        
        lines = shoe_text.strip().split('\n')
        shoes = []
        
        # Detect if this is a tabular format (has tabs or multiple columns)
        is_tabular = any('\t' in line for line in lines if line.strip())
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
                
            if is_tabular:
                # Handle tabular format
                shoe_info = self._extract_tabular_info(line)
            else:
                # Handle simple list format
                shoe_info = self._extract_shoe_info(line)
                
            if shoe_info:
                shoes.append({
                    'line_number': line_num,
                    'original_line': line,
                    'shoe_name': shoe_info['name'],
                    'price': shoe_info.get('price'),
                    'sizes': shoe_info.get('sizes', []),
                    'size_context': shoe_info.get('size_context', []),
                    'quantity': shoe_info.get('quantity'),
                    'sku': shoe_info.get('sku'),
                    'found_sku': None,
                    'found_name': None,
                    'search_success': False,
                    'error': None
                })
        
        print(f"📋 Parsed {len(shoes)} shoes from input")
        return shoes

    def _extract_shoe_info(self, line: str) -> Optional[Dict]:
        """Extract shoe name, price, and sizes from a line"""
        # Remove common prefixes/suffixes that aren't part of the shoe name
        cleaned_line = line.strip()
        
        # Extract price if present (in parentheses with $)
        price = None
        price_match = re.search(r'\(\$(\d+(?:\.\d{2})?)\)', cleaned_line)
        if price_match:
            price = float(price_match.group(1))
            # Remove price from line
            cleaned_line = re.sub(r'\(\$\d+(?:\.\d{2})?\)', '', cleaned_line)
        
        # Extract sizes if present
        sizes = []
        
        # First, look for explicit "size" mentions
        size_explicit = re.search(r'size\s+([^,\n]+)', cleaned_line, re.IGNORECASE)
        if size_explicit:
            size_text = size_explicit.group(1)
            # Extract individual sizes from the size text
            individual_sizes = re.findall(r'\b(\d+(?:\.\d+)?(?:x\d+)?(?:[wWyYcC])?)\b', size_text)
            sizes.extend(individual_sizes)
            # Remove the entire "size X" text
            cleaned_line = re.sub(r'size\s+[^,\n]+', '', cleaned_line, flags=re.IGNORECASE)
        
        # Look for size patterns with context (GS, PS, TD, Y, C, W)
        context_sizes = re.findall(r'\b(\d+(?:\.\d+)?)\s*(GS|PS|TD|Y|C|W)\b', cleaned_line, re.IGNORECASE)
        for size_num, context in context_sizes:
            try:
                size_float = float(size_num)
                if 1 <= size_float <= 20:
                    sizes.append(f"{size_num} {context}")
                    # Remove this specific size+context from the line
                    cleaned_line = re.sub(rf'\b{re.escape(size_num)}\s*{re.escape(context)}\b', '', cleaned_line, flags=re.IGNORECASE)
            except ValueError:
                pass
        
        # Then look for standalone size patterns (but be more conservative)
        # Only match sizes that are likely to be actual shoe sizes and are at the end of the line
        # This prevents matching numbers that are part of the shoe name
        standalone_sizes = re.findall(r'\b(\d{1,2}(?:\.\d)?)\s*$', cleaned_line)
        for size in standalone_sizes:
            # Only include if it looks like a reasonable shoe size (1-20 range)
            try:
                size_num = float(size)
                if 1 <= size_num <= 20:
                    sizes.append(size)
                    # Remove this specific size from the line
                    cleaned_line = re.sub(rf'\b{re.escape(size)}\s*$', '', cleaned_line)
            except ValueError:
                pass
        
        # Clean up the shoe name
        shoe_name = self._clean_shoe_name(cleaned_line)
        
        if not shoe_name:
            return None
            
        return {
            'name': shoe_name,
            'price': price,
            'sizes': sizes,
            'size_context': self._analyze_size_context(sizes)
        }

    def _extract_tabular_info(self, line: str) -> Optional[Dict]:
        """Extract information from tabular format"""
        # Split by tabs or multiple spaces
        parts = re.split(r'\t+|\s{2,}', line.strip())
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) < 1:
            return None
        
        # Extract shoe name (first column)
        shoe_name = parts[0]
        
        # Extract quantity (second column if it's a number)
        quantity = None
        if len(parts) > 1 and parts[1].isdigit():
            quantity = int(parts[1])
        
        # Extract SKU (look for pattern like DD1391-300 or 153265-057)
        sku = None
        for part in parts:
            if re.match(r'^[A-Z]{2}\d{3,4}-\d{3}$', part) or re.match(r'^\d{6}-\d{3}$', part):
                sku = part
                break
        
        # Extract sizes (last column or columns with size patterns)
        sizes = []
        size_context = []
        
        # Skip the first few columns (name, quantity, SKU) and focus on size columns
        for part in parts[2:]:  # Skip name and quantity columns
            # Skip if this looks like a SKU
            if re.match(r'^[A-Z]{2}\d{3,4}-\d{3}$', part) or re.match(r'^\d{6}-\d{3}$', part):
                continue
                
            # Look for size patterns with context (Y, C, W, GS, PS, TD)
            size_match = re.search(r'^(\d+(?:\.\d+)?)\s*(Y|C|W|GS|PS|TD)?$', part, re.IGNORECASE)
            if size_match:
                size_num = size_match.group(1)
                context = size_match.group(2) if size_match.group(2) else None
                
                # Only add if it's a reasonable shoe size (1-20 range)
                try:
                    size_float = float(size_num)
                    if 1 <= size_float <= 20:
                        sizes.append(size_num)
                        size_context.append(context)
                except ValueError:
                    pass
        
        # Clean up shoe name
        shoe_name = self._clean_shoe_name(shoe_name)
        
        if not shoe_name:
            return None
            
        return {
            'name': shoe_name,
            'quantity': quantity,
            'sku': sku,
            'sizes': sizes,
            'size_context': self._analyze_size_context(sizes, size_context)
        }

    def _analyze_size_context(self, sizes: List[str], contexts: List[str] = None) -> List[Dict]:
        """Analyze size context and provide intelligent suggestions"""
        if not contexts:
            contexts = [None] * len(sizes)
        
        size_analysis = []
        
        for i, size in enumerate(sizes):
            try:
                # Handle size with context suffix (e.g., "3.5 Y", "8.5 W")
                size_with_context = size.strip()
                context = contexts[i] if i < len(contexts) else None
                
                # Check if size already has context suffix
                context_match = re.search(r'^(\d+(?:\.\d+)?)\s*(Y|C|W|GS|PS|TD)$', size_with_context, re.IGNORECASE)
                if context_match:
                    size_num = float(context_match.group(1))
                    context = context_match.group(2).upper()
                else:
                    size_num = float(size)
                
                analysis = {
                    'size': size,
                    'numeric_size': size_num,
                    'detected_context': context,
                    'suggested_context': None,
                    'confidence': 'high',
                    'warning': None
                }
                
                # Intelligent context detection based on size ranges
                if context:
                    # Context already provided
                    analysis['suggested_context'] = context
                    analysis['confidence'] = 'high'
                else:
                    # No context provided, make intelligent guess
                    if size_num <= 3.5:
                        # Very small sizes - likely C (Child/PS) or Y (Youth/GS)
                        analysis['suggested_context'] = 'C'
                        analysis['confidence'] = 'medium'
                        analysis['warning'] = 'Small size detected - may be Child (C) or Youth (Y)'
                    elif size_num <= 7:
                        # Small sizes - could be Y, C, or W
                        analysis['suggested_context'] = 'Y'
                        analysis['confidence'] = 'low'
                        analysis['warning'] = 'Small size detected - may be Youth (Y), Child (C), or Women (W)'
                    elif size_num <= 13:
                        # Standard men's range
                        analysis['suggested_context'] = 'M'
                        analysis['confidence'] = 'high'
                    else:
                        # Large sizes - likely men's
                        analysis['suggested_context'] = 'M'
                        analysis['confidence'] = 'high'
                
                size_analysis.append(analysis)
                
            except ValueError:
                # Invalid size number
                size_analysis.append({
                    'size': size,
                    'numeric_size': None,
                    'detected_context': contexts[i] if i < len(contexts) else None,
                    'suggested_context': None,
                    'confidence': 'none',
                    'warning': 'Invalid size format'
                })
        
        return size_analysis

    def _clean_shoe_name(self, name: str) -> str:
        """Clean and standardize shoe name for searching"""
        # Remove common non-shoe words
        remove_words = [
            'size', 'sizes', 'x2', 'x3', 'x4', 'x5', 'x6', 'x7', 'x8', 'x9', 'x10',
            'new', 'used', 'ds', 'vnds', 'no box', 'with box', '-'
        ]
        
        cleaned = name.strip()
        for word in remove_words:
            cleaned = re.sub(rf'\b{re.escape(word)}\b', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra spaces and punctuation
        cleaned = re.sub(r'\s+', ' ', cleaned)
        cleaned = re.sub(r'[,\-]+$', '', cleaned)
        cleaned = re.sub(r'^\s*-\s*', '', cleaned)  # Remove leading dashes
        cleaned = cleaned.strip()
        
        return cleaned

    def find_skus(self, shoes: List[Dict]) -> List[Dict]:
        """Find SKUs for all shoes in the list with dual API verification"""
        print(f"🔍 Searching for SKUs for {len(shoes)} shoes...")
        print(f"📋 Input data includes: {sum(1 for s in shoes if s.get('quantity'))} items with quantities, {sum(1 for s in shoes if s.get('sizes'))} items with sizes")
        
        results = []
        successful_searches = 0
        failed_searches = 0
        
        for i, shoe in enumerate(shoes, 1):
            print(f"\n🔍 [{i}/{len(shoes)}] Processing: {shoe['shoe_name']}")
            print(f"   📊 Progress: {successful_searches} successful, {failed_searches} failed")
            
            # Show input data details
            if shoe.get('quantity'):
                print(f"   📦 Quantity: {shoe['quantity']}")
            if shoe.get('sizes'):
                size_str = ", ".join([f"{s}({c})" if c else s for s, c in zip(shoe['sizes'], shoe.get('size_context', []))])
                print(f"   👟 Sizes: {size_str}")
            if shoe.get('price'):
                print(f"   💰 Price: ${shoe['price']}")
            if shoe.get('sku'):
                print(f"   🏷️  Input SKU: {shoe['sku']}")
            
            try:
                # Check if StockX client is available
                if not self.client:
                    print(f"   ❌ StockX client not available - skipping StockX search")
                    stockx_sku = None
                    stockx_name = None
                    stockx_data = {}
                else:
                    # Search StockX for the shoe
                    print(f"   📊 Searching StockX API...")
                    try:
                        search_results = self.client.search_products(shoe['shoe_name'], page_size=5)
                        print(f"   ✅ StockX API call completed")
                    except Exception as stockx_error:
                        print(f"   ❌ StockX API error: {stockx_error}")
                        search_results = None
                
                stockx_sku = None
                stockx_name = None
                stockx_data = {}
                
                if search_results and search_results.get('products'):
                    # Get the best match (first result)
                    best_match = search_results['products'][0]
                    stockx_sku = best_match.get('style_id') or best_match.get('id')
                    stockx_name = best_match.get('title')
                    stockx_data = {
                        'brand': best_match.get('brand'),
                        'category': best_match.get('category'),
                        'release_date': best_match.get('release_date'),
                        'retail_price': best_match.get('retail_price'),
                        'colorway': best_match.get('colorway'),
                        'product_id': best_match.get('product_id')
                    }
                    
                    print(f"   ✅ StockX Found:")
                    print(f"      🏷️  SKU: {stockx_sku}")
                    print(f"      📝 Name: {stockx_name}")
                    if stockx_data.get('brand'):
                        print(f"      🏭 Brand: {stockx_data['brand']}")
                    if stockx_data.get('category'):
                        print(f"      📂 Category: {stockx_data['category']}")
                    if stockx_data.get('colorway'):
                        print(f"      🎨 Colorway: {stockx_data['colorway']}")
                    if stockx_data.get('retail_price'):
                        print(f"      💵 Retail: ${stockx_data['retail_price']}")
                    if stockx_data.get('release_date'):
                        print(f"      📅 Release: {stockx_data['release_date']}")
                else:
                    print(f"   ❌ No StockX matches found")
                
                # Search Alias for the shoe
                print(f"   🔍 Searching Alias API...")
                try:
                    alias_results = self.search_alias_for_sku(shoe['shoe_name'])
                    print(f"   ✅ Alias API call completed")
                except Exception as alias_error:
                    print(f"   ❌ Alias API error: {alias_error}")
                    alias_results = {'success': False, 'error': str(alias_error)}
                
                alias_sku = None
                alias_name = None
                alias_data = {}
                
                if alias_results.get('success'):
                    alias_sku = alias_results.get('sku')
                    alias_name = alias_results.get('name')
                    alias_data = {
                        'brand': alias_results.get('brand'),
                        'category': alias_results.get('category'),
                        'release_year': alias_results.get('release_year'),
                        'colorway': alias_results.get('colorway')
                    }
                    
                    print(f"   ✅ Alias Found:")
                    print(f"      🏷️  SKU: {alias_sku}")
                    print(f"      📝 Name: {alias_name}")
                    if alias_data.get('brand'):
                        print(f"      🏭 Brand: {alias_data['brand']}")
                    if alias_data.get('category'):
                        print(f"      📂 Category: {alias_data['category']}")
                    if alias_data.get('colorway'):
                        print(f"      🎨 Colorway: {alias_data['colorway']}")
                    if alias_data.get('release_year'):
                        print(f"      📅 Release Year: {alias_data['release_year']}")
                else:
                    print(f"   ❌ No Alias matches found: {alias_results.get('error')}")
                
                # Verify SKU match between platforms
                if stockx_sku or alias_sku:
                    verification = self.verify_sku_match(stockx_sku, alias_sku, stockx_name, alias_name)
                    shoe['sku_verification'] = verification
                    shoe['stockx_data'] = stockx_data
                    shoe['alias_data'] = alias_data
                    
                    print(f"   🔍 SKU Verification Results:")
                    if verification['skus_match']:
                        print(f"      🟢 SKUs MATCH: {stockx_sku} = {alias_sku}")
                        print(f"      ✅ High Confidence Match")
                    elif verification['names_similar']:
                        print(f"      🟡 Names SIMILAR but SKUs differ")
                        print(f"      📊 StockX: {stockx_sku} | Alias: {alias_sku}")
                        print(f"      ⚠️  Medium Confidence - Manual review recommended")
                    else:
                        print(f"      🔴 NO MATCH between platforms")
                        print(f"      📊 StockX: {stockx_sku} | Alias: {alias_sku}")
                        print(f"      ⚠️  Low Confidence - Manual review required")
                    
                    if verification['warnings']:
                        for warning in verification['warnings']:
                            print(f"      ⚠️  {warning}")
                    
                    # Use StockX SKU as primary, Alias as backup
                    shoe['found_sku'] = stockx_sku or alias_sku
                    shoe['found_name'] = stockx_name or alias_name
                    shoe['stockx_sku'] = stockx_sku
                    shoe['stockx_name'] = stockx_name
                    shoe['alias_sku'] = alias_sku
                    shoe['alias_name'] = alias_name
                    shoe['search_success'] = True
                    successful_searches += 1
                    
                    print(f"   ✅ Final Result:")
                    print(f"      🏷️  Final SKU: {shoe['found_sku']}")
                    print(f"      📝 Final Name: {shoe['found_name']}")
                    print(f"      📊 Source: {'StockX' if stockx_sku else 'Alias'}")
                    
                else:
                    shoe['error'] = 'No matches found on either platform'
                    failed_searches += 1
                    print(f"   ❌ No matches found on either platform")
                    print(f"   💡 Try: Check spelling, use more specific name, or verify shoe exists")
                
            except Exception as e:
                shoe['error'] = str(e)
                failed_searches += 1
                print(f"   ❌ Error searching for {shoe['shoe_name']}: {e}")
                print(f"   💡 Try: Check internet connection or API status")
            
            results.append(shoe)
            
            # Rate limiting - wait between requests
            if i < len(shoes):
                print(f"   ⏳ Waiting 2 seconds before next search...")
                time.sleep(2)
        
        # Final summary
        print(f"\n📊 SKU FINDER COMPLETED")
        print(f"   ✅ Successful searches: {successful_searches}")
        print(f"   ❌ Failed searches: {failed_searches}")
        print(f"   📈 Success rate: {(successful_searches/max(len(shoes), 1)*100):.1f}%")
        
        return results

    def search_alias_for_sku(self, shoe_name: str) -> Dict:
        """Search Alias API for shoe SKU with multiple strategies"""
        try:
            headers = {
                'Authorization': f'Bearer {self.alias_api_key}',
                'Content-Type': 'application/json'
            }
            
            # Strategy 1: Direct search with original name
            print(f"      🔍 Strategy 1: Direct search for '{shoe_name}'")
            search_data = self._try_alias_search(shoe_name, headers)
            
            if search_data and search_data.get('catalog_items'):
                catalog_item = search_data['catalog_items'][0]
                return self._extract_alias_data(catalog_item, "Direct search")
            
            # Strategy 2: Clean the shoe name and try again
            cleaned_name = self._clean_shoe_name_for_alias(shoe_name)
            if cleaned_name != shoe_name:
                print(f"      🔍 Strategy 2: Cleaned search for '{cleaned_name}'")
                search_data = self._try_alias_search(cleaned_name, headers)
                
                if search_data and search_data.get('catalog_items'):
                    catalog_item = search_data['catalog_items'][0]
                    return self._extract_alias_data(catalog_item, "Cleaned search")
            
            # Strategy 3: Try with common variations
            variations = self._generate_search_variations(shoe_name)
            for variation in variations:
                print(f"      🔍 Strategy 3: Variation search for '{variation}'")
                search_data = self._try_alias_search(variation, headers)
                
                if search_data and search_data.get('catalog_items'):
                    catalog_item = search_data['catalog_items'][0]
                    return self._extract_alias_data(catalog_item, f"Variation: {variation}")
            
            return {'success': False, 'error': 'No Alias match found after all strategies'}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def _try_alias_search(self, query: str, headers: Dict) -> Optional[Dict]:
        """Try to search Alias API with a given query"""
        try:
            # Try the catalog endpoint first (like inventory analyzer)
            search_response = requests.get(
                f"{self.alias_base_url}/catalog",
                headers=headers,
                params={'query': query, 'limit': 1},
                timeout=15
            )
            
            if search_response.status_code == 200:
                return search_response.json()
            
            # Fallback to catalog/search endpoint
            search_response = requests.get(
                f"{self.alias_base_url}/catalog/search",
                headers=headers,
                params={'q': query, 'limit': 1},
                timeout=15
            )
            
            if search_response.status_code == 200:
                return search_response.json()
            
            return None
                
        except Exception as e:
            print(f"      ⚠️ Alias search error for '{query}': {e}")
            return None
    
    def _clean_shoe_name_for_alias(self, shoe_name: str) -> str:
        """Clean shoe name for better Alias search results"""
        # Remove size information
        cleaned = re.sub(r'\s+\d+(?:\.\d+)?\s*(GS|PS|TD|Y|C|W)?\s*$', '', shoe_name, flags=re.IGNORECASE)
        
        # Remove common prefixes/suffixes
        cleaned = re.sub(r'\b(and below|size)\b', '', cleaned, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _generate_search_variations(self, shoe_name: str) -> List[str]:
        """Generate search variations for better Alias matching"""
        variations = []
        
        # Remove size info for variations
        base_name = re.sub(r'\s+\d+(?:\.\d+)?\s*(GS|PS|TD|Y|C|W)?\s*$', '', shoe_name, flags=re.IGNORECASE)
        
        # Common variations
        if 'jordan' in base_name.lower():
            variations.extend([
                f"Air Jordan {base_name.replace('Jordan', '').strip()}",
                f"Jordan {base_name.replace('Jordan', '').strip()}",
                base_name.replace('Jordan', 'Air Jordan')
            ])
        
        if 'dunk' in base_name.lower():
            variations.extend([
                f"Nike Dunk {base_name.replace('Dunk', '').strip()}",
                base_name.replace('Dunk', 'Nike Dunk')
            ])
        
        if 'yeezy' in base_name.lower():
            variations.extend([
                f"Adidas Yeezy {base_name.replace('Yeezy', '').strip()}",
                base_name.replace('Yeezy', 'Adidas Yeezy')
            ])
        
        # Add brand prefixes if missing
        if not any(brand in base_name.lower() for brand in ['nike', 'jordan', 'adidas', 'yeezy']):
            if 'dunk' in base_name.lower():
                variations.append(f"Nike {base_name}")
            elif 'jordan' in base_name.lower():
                variations.append(f"Air {base_name}")
        
        return variations[:3]  # Limit to 3 variations
    
    def _extract_alias_data(self, catalog_item: Dict, strategy: str) -> Dict:
        """Extract data from Alias catalog item"""
        # Try multiple fields for SKU extraction
        alias_sku = (catalog_item.get('sku') or 
                   catalog_item.get('style_id') or 
                   catalog_item.get('style_code') or 
                   catalog_item.get('product_id') or 
                   catalog_item.get('model_number') or 
                   '')
        
        # Extract additional data
        alias_data = {
            'brand': catalog_item.get('brand'),
            'category': catalog_item.get('category'),
            'release_year': catalog_item.get('release_year'),
            'colorway': catalog_item.get('colorway'),
            'catalog_id': catalog_item.get('catalog_id'),
            'model': catalog_item.get('model'),
            'subtitle': catalog_item.get('subtitle')
        }
        
        return {
            'sku': alias_sku,
            'name': catalog_item.get('name', 'Unknown'),
            'success': True,
            'strategy': strategy,
            **alias_data  # Include all the additional data
        }

    def verify_sku_match(self, stockx_sku: str, alias_sku: str, stockx_name: str, alias_name: str) -> Dict:
        """Verify if SKUs match between StockX and Alias"""
        match_result = {
            'skus_match': False,
            'names_similar': False,
            'confidence': 'low',
            'warnings': []
        }
        
        # Check if SKUs match exactly
        if stockx_sku and alias_sku:
            if stockx_sku.lower() == alias_sku.lower():
                match_result['skus_match'] = True
                match_result['confidence'] = 'high'
            else:
                match_result['warnings'].append(f"SKU mismatch: StockX={stockx_sku}, Alias={alias_sku}")
        
        # Check if names are similar
        if stockx_name and alias_name:
            # Simple similarity check (can be enhanced)
            stockx_words = set(stockx_name.lower().split())
            alias_words = set(alias_name.lower().split())
            common_words = stockx_words.intersection(alias_words)
            
            if len(common_words) >= 3:  # At least 3 common words
                match_result['names_similar'] = True
                if match_result['skus_match']:
                    match_result['confidence'] = 'high'
                else:
                    match_result['confidence'] = 'medium'
            else:
                match_result['warnings'].append(f"Name similarity low: StockX='{stockx_name}', Alias='{alias_name}'")
        
        return match_result

    def generate_report(self, results: List[Dict]) -> str:
        """Generate a formatted report of the SKU search results"""
        print("📊 Generating SKU finder report...")
        
        report_lines = []
        report_lines.append("🔍 SKU FINDER REPORT")
        report_lines.append("=" * 50)
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Total shoes processed: {len(results)}")
        report_lines.append("")
        
        # Summary statistics
        successful = sum(1 for r in results if r['search_success'])
        failed = len(results) - successful
        
        # Verification statistics
        sku_matches = sum(1 for r in results if r.get('sku_verification', {}).get('skus_match', False))
        similar_names = sum(1 for r in results if r.get('sku_verification', {}).get('names_similar', False) and not r.get('sku_verification', {}).get('skus_match', False))
        mismatches = sum(1 for r in results if r.get('sku_verification') and not r.get('sku_verification', {}).get('skus_match', False) and not r.get('sku_verification', {}).get('names_similar', False))
        
        report_lines.append("📊 SUMMARY:")
        report_lines.append(f"✅ Successful matches: {successful}")
        report_lines.append(f"❌ Failed matches: {failed}")
        report_lines.append(f"📈 Success rate: {(successful/len(results)*100):.1f}%")
        report_lines.append("")
        report_lines.append("🔍 SKU VERIFICATION:")
        report_lines.append(f"🟢 SKU Matches: {sku_matches}")
        report_lines.append(f"🟡 Similar Names: {similar_names}")
        report_lines.append(f"🔴 Mismatches: {mismatches}")
        report_lines.append(f"📊 Verification rate: {((sku_matches + similar_names)/max(successful, 1)*100):.1f}%")
        report_lines.append("")
        
        # Detailed results
        report_lines.append("📋 DETAILED RESULTS:")
        report_lines.append("-" * 50)
        
        for i, result in enumerate(results, 1):
            report_lines.append(f"\n{i}. {result['original_line']}")
            
            # Show size context information if available
            if result.get('size_context'):
                report_lines.append("   📏 Size Analysis:")
                for size_info in result['size_context']:
                    context_str = f"{size_info['size']}"
                    if size_info['detected_context']:
                        context_str += f" ({size_info['detected_context']})"
                    elif size_info['suggested_context']:
                        context_str += f" (suggested: {size_info['suggested_context']})"
                    
                    confidence_emoji = "🟢" if size_info['confidence'] == 'high' else "🟡" if size_info['confidence'] == 'medium' else "🔴"
                    report_lines.append(f"      {confidence_emoji} {context_str}")
                    
                    if size_info.get('warning'):
                        report_lines.append(f"         ⚠️ {size_info['warning']}")
            
            if result['search_success']:
                # Show StockX results
                if result.get('stockx_sku'):
                    report_lines.append(f"   📊 StockX: {result['stockx_name']} (SKU: {result['stockx_sku']})")
                    if result.get('stockx_data'):
                        data = result['stockx_data']
                        if data.get('brand'):
                            report_lines.append(f"      🏭 Brand: {data['brand']}")
                        if data.get('colorway'):
                            report_lines.append(f"      🎨 Colorway: {data['colorway']}")
                        if data.get('retail_price'):
                            report_lines.append(f"      💵 Retail: ${data['retail_price']}")
                        if data.get('release_date'):
                            report_lines.append(f"      📅 Release: {data['release_date']}")
                else:
                    report_lines.append(f"   ❌ StockX: No match found")
                
                # Show Alias results
                if result.get('alias_sku'):
                    report_lines.append(f"   🔍 Alias: {result['alias_name']} (SKU: {result['alias_sku']})")
                    if result.get('alias_data'):
                        data = result['alias_data']
                        if data.get('brand'):
                            report_lines.append(f"      🏭 Brand: {data['brand']}")
                        if data.get('colorway'):
                            report_lines.append(f"      🎨 Colorway: {data['colorway']}")
                        if data.get('release_year'):
                            report_lines.append(f"      📅 Release Year: {data['release_year']}")
                        if data.get('model'):
                            report_lines.append(f"      👟 Model: {data['model']}")
                else:
                    report_lines.append(f"   ❌ Alias: No match found")
                
                # Show verification status
                if result.get('sku_verification'):
                    verification = result['sku_verification']
                    if verification['skus_match']:
                        report_lines.append(f"   🟢 SKU Verification: MATCH (High Confidence)")
                    elif verification['names_similar']:
                        report_lines.append(f"   🟡 SKU Verification: SIMILAR NAMES (Medium Confidence)")
                    else:
                        report_lines.append(f"   🔴 SKU Verification: MISMATCH (Low Confidence)")
                    
                    if verification['warnings']:
                        for warning in verification['warnings']:
                            report_lines.append(f"      ⚠️ {warning}")
                
                # Show final result
                report_lines.append(f"   ✅ Final SKU: {result['found_sku']}")
                report_lines.append(f"   📝 Final Name: {result['found_name']}")
            else:
                report_lines.append(f"   ❌ Error: {result['error']}")
        
        # CSV format for easy copying
        report_lines.append("\n" + "=" * 50)
        report_lines.append("📋 CSV FORMAT (copy below):")
        report_lines.append("Original Name,StockX SKU,StockX Name,Alias SKU,Alias Name,Final SKU,Final Name,Verification Status,Size Context")
        
        for result in results:
            # Get verification status
            verification_status = "FAILED"
            if result.get('sku_verification'):
                verification = result['sku_verification']
                if verification['skus_match']:
                    verification_status = "MATCH"
                elif verification['names_similar']:
                    verification_status = "SIMILAR"
                else:
                    verification_status = "MISMATCH"
            
            # Get all SKU and name data
            stockx_sku = result.get('stockx_sku', '')
            stockx_name = result.get('stockx_name', '')
            alias_sku = result.get('alias_sku', '')
            alias_name = result.get('alias_name', '')
            final_sku = result.get('found_sku', '')
            final_name = result.get('found_name', '')
            
            # Build size context string
            size_context_str = ""
            if result.get('size_context'):
                context_parts = []
                for size_info in result['size_context']:
                    context_part = size_info['size']
                    if size_info['detected_context']:
                        context_part += f"({size_info['detected_context']})"
                    elif size_info['suggested_context']:
                        context_part += f"[{size_info['suggested_context']}]"
                    context_parts.append(context_part)
                size_context_str = "; ".join(context_parts)
            
            # Escape commas in CSV
            original = f'"{result["original_line"]}"'
            stockx_name_escaped = f'"{stockx_name}"' if stockx_name else ''
            alias_name_escaped = f'"{alias_name}"' if alias_name else ''
            final_name_escaped = f'"{final_name}"' if final_name else ''
            size_context_escaped = f'"{size_context_str}"' if size_context_str else ''
            
            report_lines.append(f"{original},{stockx_sku},{stockx_name_escaped},{alias_sku},{alias_name_escaped},{final_sku},{final_name_escaped},{verification_status},{size_context_escaped}")
        
        return "\n".join(report_lines)

    def generate_csv_report(self, results: List[Dict]) -> str:
        """Generate CSV report with StockX links"""
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            'Original Name',
            'StockX SKU', 
            'StockX Name',
            'StockX Link',
            'Alias SKU',
            'Alias Name',
            'Final SKU',
            'Final Name',
            'Verification Status',
            'Size Context',
            'Search Strategy'
        ])
        
        for result in results:
            # Get verification status
            verification_status = "FAILED"
            if result.get('sku_verification'):
                verification = result['sku_verification']
                if verification['skus_match']:
                    verification_status = "MATCH"
                elif verification['names_similar']:
                    verification_status = "SIMILAR"
                else:
                    verification_status = "MISMATCH"
            
            # Get all SKU and name data
            stockx_sku = result.get('stockx_sku', '')
            stockx_name = result.get('stockx_name', '')
            alias_sku = result.get('alias_sku', '')
            alias_name = result.get('alias_name', '')
            final_sku = result.get('found_sku', '')
            final_name = result.get('found_name', '')
            
            # Generate StockX link
            stockx_link = ""
            if stockx_sku:
                # Clean SKU for URL (remove spaces, use dashes)
                clean_sku = stockx_sku.replace(' ', '-')
                stockx_link = f"https://stockx.com/{clean_sku}"
            
            # Build size context string
            size_context_str = ""
            if result.get('size_context'):
                context_parts = []
                for size_info in result['size_context']:
                    context_part = size_info['size']
                    if size_info['detected_context']:
                        context_part += f"({size_info['detected_context']})"
                    elif size_info['suggested_context']:
                        context_part += f"[{size_info['suggested_context']}]"
                    context_parts.append(context_part)
                size_context_str = "; ".join(context_parts)
            
            # Get search strategy
            search_strategy = result.get('alias_data', {}).get('strategy', '') if result.get('alias_data') else ''
            
            writer.writerow([
                result["original_line"],
                stockx_sku,
                stockx_name,
                stockx_link,
                alias_sku,
                alias_name,
                final_sku,
                final_name,
                verification_status,
                size_context_str,
                search_strategy
            ])
        
        return output.getvalue()

def main():
    """Main function for command line usage"""
    if len(sys.argv) != 2:
        print("Usage: python3 sku_finder.py <input_file>")
        print("Or use the web interface")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    try:
        with open(input_file, 'r') as f:
            shoe_text = f.read()
        
        finder = SKUFinder()
        shoes = finder.parse_shoe_list(shoe_text)
        results = finder.find_skus(shoes)
        report = finder.generate_report(results)
        
        print("\n" + report)
        
        # Save report
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"sku_finder_report_{timestamp}.txt"
        
        with open(output_file, 'w') as f:
            f.write(report)
        
        print(f"\n📁 Report saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 