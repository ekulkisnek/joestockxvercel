#!/usr/bin/env python3
"""
🎯 Advanced Shoe Analyzer with Detailed Pricing Logic
Implements specific pricing strategy with all calculations and work shown
"""

import sys
import os
import json
import time
import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inventory_stockx_analyzer import InventoryStockXAnalyzer, InventoryItem
from sales_volume_analyzer import SalesVolumeAnalyzer

class AdvancedShoeAnalyzer:
    def __init__(self):
        """Initialize with both analyzers"""
        self.auth_file = "../tokens_full_scope.json"
        self.stockx_analyzer = InventoryStockXAnalyzer()
        self.sales_analyzer = SalesVolumeAnalyzer()
        
        # Results storage
        self.results_dir = "advanced_analysis_results"
        if not os.path.exists(self.results_dir):
            os.makedirs(self.results_dir)
        
        print("🎯 Advanced Shoe Analyzer initialized")

    def analyze_shoe_with_pricing_logic(self, shoe_query: str, size: str = "10") -> Dict:
        """
        Comprehensive analysis with detailed pricing logic and all work shown
        """
        print(f"🎯 Analyzing: {shoe_query} (Size: {size})")
        
        start_time = time.time()
        result = {
            'query': shoe_query,
            'size': size,
            'timestamp': datetime.now().isoformat(),
            'processing_time': 0,
            'success': False,
            'errors': [],
            'warnings': [],
            'sku_mismatch_warning': None,  # New field for prominent SKU mismatch warnings
            'calculations': {},
            'final_recommendation': {},
            'raw_data': {},
            'search_metadata': {}
        }

        try:
            # Step 1: Get StockX data
            print("📊 Step 1: Getting StockX data...")
            stockx_data = self._get_stockx_data(shoe_query, size)
            
            # Separate raw API data from search metadata
            stockx_raw = {k: v for k, v in stockx_data.items() if k not in ['search_query', 'search_size', 'success']}
            stockx_metadata = {k: v for k, v in stockx_data.items() if k in ['search_query', 'search_size', 'success']}
            
            result['raw_data']['stockx'] = stockx_raw
            result['search_metadata']['stockx'] = stockx_metadata
            
            # Step 2: Get Alias/GOAT data
            print("📈 Step 2: Getting Alias/GOAT data...")
            alias_data = self._get_alias_data(shoe_query, size)
            
            # Separate raw API data from search metadata
            alias_raw = {k: v for k, v in alias_data.items() if k not in ['search_query', 'search_size', 'success']}
            alias_metadata = {k: v for k, v in alias_data.items() if k in ['search_query', 'search_size', 'success']}
            
            result['raw_data']['alias'] = alias_raw
            result['search_metadata']['alias'] = alias_metadata
            
            # Check for SKU mismatch and create prominent warning
            sku_mismatch = self._check_sku_mismatch(stockx_raw, alias_raw)
            if sku_mismatch:
                result['sku_mismatch_warning'] = sku_mismatch
                print(f"🚨 CRITICAL SKU MISMATCH: {sku_mismatch['message']}")
                
                # Try to find corresponding match on the other platform
                print(f"   🔄 {sku_mismatch['recommendation']}")
                corresponding_match = self._find_corresponding_match(
                    sku_mismatch['better_sku'], 
                    sku_mismatch['better_name'], 
                    sku_mismatch['worse_match']
                )
                
                if corresponding_match:
                    print(f"   ✅ Found corresponding {sku_mismatch['worse_match']} match!")
                    # Update the data with the corresponding match
                    if sku_mismatch['worse_match'] == 'alias':
                        alias_raw = corresponding_match
                        result['raw_data']['alias'] = alias_raw
                        # Update metadata
                        alias_metadata = {
                            'search_query': sku_mismatch['better_sku'],
                            'search_size': size,
                            'success': True
                        }
                        result['search_metadata']['alias'] = alias_metadata
                    else:  # worse_match == 'stockx'
                        stockx_raw = corresponding_match
                        result['raw_data']['stockx'] = stockx_raw
                        # Update metadata
                        stockx_metadata = {
                            'search_query': sku_mismatch['better_sku'],
                            'search_size': size,
                            'success': True
                        }
                        result['search_metadata']['stockx'] = stockx_metadata
                    
                    # Clear the SKU mismatch warning since we found a match
                    result['sku_mismatch_warning'] = None
                    print(f"   ✅ SKU mismatch resolved! Using {sku_mismatch['better_match']} match on both platforms.")
                else:
                    print(f"   ❌ Could not find corresponding {sku_mismatch['worse_match']} match. Keeping alternatives.")
            
            # Step 3: Apply pricing logic with detailed calculations
            print("🧮 Step 3: Applying pricing logic...")
            pricing_logic = self._apply_pricing_logic(stockx_raw, alias_raw, stockx_metadata, alias_metadata, size)
            result['calculations'] = pricing_logic
            
            # Step 4: Generate final recommendation
            print("💡 Step 4: Generating recommendation...")
            recommendation = self._generate_recommendation(pricing_logic)
            result['final_recommendation'] = recommendation
            
            result['success'] = True
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            result['errors'].append(str(e))
        
        result['processing_time'] = round(time.time() - start_time, 2)
        
        # Check if we should automatically generate alternatives
        should_generate_alternatives = self._should_generate_alternatives(stockx_data, alias_data, shoe_query)
        
        if should_generate_alternatives:
            print("🔍 Auto-generating alternatives due to poor match quality...")
            alternatives = self._get_alternative_matches(shoe_query, size)
            result['alternatives'] = alternatives
        else:
            # Don't generate alternatives by default - only when requested
            result['alternatives'] = {'stockx_alternatives': [], 'alias_alternatives': [], 'search_query': shoe_query, 'size': size}
        
        # Save result
        self._save_result(result)
        
        return result

    def _get_stockx_data(self, shoe_query: str, size: str) -> Dict:
        """Get StockX market data for the shoe and size with optimal SKU matching"""
        try:
            # Create a temporary inventory item
            item = InventoryItem(shoe_name=shoe_query, size=size)
            
            # Check if this looks like a SKU search
            if self._looks_like_sku(shoe_query):
                item.is_sku_search = True
                print(f"🔍 Detected SKU search: {shoe_query}")
                
                # Apply optimal SKU normalization before search
                normalized_sku = self._normalize_sku_for_search(shoe_query)
                if normalized_sku != shoe_query:
                    print(f"🔧 Normalized SKU: {shoe_query} → {normalized_sku}")
                    item.shoe_name = normalized_sku
            
            # Search StockX
            success = self.stockx_analyzer.search_stockx_for_item(item)
            
            if not success:
                return {
                    'error': 'No StockX match found',
                    'search_query': shoe_query,
                    'search_size': size
                }
            
            # Extract the raw API data and search metadata
            return {
                'bid': item.stockx_bid,
                'ask': item.stockx_ask,
                'product_name': item.stockx_shoe_name,
                'sku': item.stockx_sku,
                'url': item.stockx_url,
                'search_query': shoe_query,
                'search_size': size,
                'success': True
            }
            
        except Exception as e:
            return {
                'error': str(e),
                'search_query': shoe_query,
                'search_size': size
            }

    def _get_alias_data(self, shoe_query: str, size: str) -> Dict:
        """Get Alias/GOAT data including sales volume and pricing"""
        try:
            # Get pricing data
            pricing_data = self.stockx_analyzer.get_alias_pricing_data(shoe_query, size)
            
            # Get sales volume data
            search_terms = self.sales_analyzer._extract_search_terms(shoe_query)
            catalog_match = self.sales_analyzer.search_catalog_improved(search_terms)
            
            if catalog_match:
                # Get size-specific sales data
                try:
                    size_float = float(size.replace('Y', '').replace('W', '').replace('C', ''))
                    sales_data = self.sales_analyzer._get_sales_for_size(
                        catalog_match['catalog_id'], 
                        size_float
                    )
                    
                    # Calculate weekly sales
                    weekly_sales = self._calculate_weekly_sales(sales_data)
                    
                except (ValueError, Exception) as e:
                    weekly_sales = {'sales_per_week': 0, 'error': str(e)}
            else:
                weekly_sales = {'sales_per_week': 0, 'error': 'No catalog match'}
            
            return {
                'pricing': pricing_data or {},
                'sales_volume': weekly_sales,
                'catalog_match': catalog_match,
                'search_query': shoe_query,
                'search_size': size,
                'success': True
            }
            
        except Exception as e:
            return {'error': str(e)}

    def _looks_like_sku(self, text: str) -> bool:
        """Check if text looks like a SKU"""
        import re
        
        # SKUs are typically short alphanumeric codes
        if not (4 <= len(text) <= 25):
            return False
            
        # Must be mostly alphanumeric with limited special chars
        if not re.match(r'^[A-Za-z0-9\s\-]+$', text):
            return False
            
        # Should have at least some letters and numbers
        has_letters = bool(re.search(r'[A-Za-z]', text))
        has_numbers = bool(re.search(r'\d', text))
        if not (has_letters and has_numbers):
            return False
            
        # If it contains many obvious shoe terms, it's probably not a SKU
        # But allow single short terms that might be in SKUs
        shoe_terms = ['jordan', 'nike', 'air force', 'dunk low', 'yeezy', 'adidas', 'retro', 'high og', 'low og']
        text_lower = text.lower()
        if any(term in text_lower for term in shoe_terms):
            return False
            
        # If it has descriptive words, it's probably not a SKU
        descriptive_words = ['travis', 'canary', 'royal', 'cement', 'fire', 'red', 'navy', 'champion', 'mauve']
        word_count = sum(1 for word in descriptive_words if word in text_lower)
        if word_count >= 2:  # Multiple descriptive words = not a SKU
            return False
            
        # If it has size indicators at the end, it's not a pure SKU
        if re.search(r'\s+\d+(?:\.\d+)?[mwcy]\s*$', text_lower):
            return False
            
        # If it has obvious condition terms, it's not a SKU
        condition_terms = ['ds', 'vnds', 'og all', 'nb', 'used']
        if any(term in text_lower for term in condition_terms):
            return False
            
        # If it's mostly just letters and numbers in a pattern, it's likely a SKU
        # Common SKU patterns: AB1234, AB1234-567, AB1234 567
        sku_patterns = [
            r'^[A-Z]{1,3}\d{4,6}$',           # AB1234
            r'^[A-Z]{1,3}\d{4,6}[\s\-]\d{2,4}$',  # AB1234-567 or AB1234 567
            r'^[A-Z0-9]{4,12}$',              # Mixed alphanumeric
        ]
        
        text_clean = text.replace(' ', '').replace('-', '')
        for pattern in sku_patterns:
            if re.match(pattern, text_clean, re.IGNORECASE):
                return True
        
        return False

    def _normalize_sku_for_search(self, sku: str) -> str:
        """Optimal SKU normalization based on breakthroughs from sku_finder.py"""
        import re
        
        if not sku:
            return sku
        
        # Convert to uppercase
        normalized = sku.upper().strip()
        
        # Remove extra spaces and normalize spacing
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Handle common SKU format variations (your breakthroughs)
        # Convert "DD1391 300" to "DD1391-300"
        if re.match(r'^[A-Z]{2}\d{3,4}\s+\d{3}$', normalized):
            normalized = normalized.replace(' ', '-')
        
        # Convert "153265 057" to "153265-057"
        if re.match(r'^\d{6}\s+\d{3}$', normalized):
            normalized = normalized.replace(' ', '-')
        
        # Handle SKUs with different separators
        normalized = re.sub(r'[_\s]+', '-', normalized)
        
        # Remove any trailing separators
        normalized = normalized.rstrip('-')
        
        return normalized

    def _get_alternative_matches(self, shoe_query: str, size: str) -> Dict:
        """Get alternative matches for correction interface"""
        alternatives = {
            'stockx_alternatives': [],
            'alias_alternatives': [],
            'search_query': shoe_query,
            'size': size
        }
        
        try:
            # Get StockX alternatives
            if self._looks_like_sku(shoe_query):
                # For SKU searches, try variations
                sku_variations = self._generate_sku_variations(shoe_query)
                for variation in sku_variations[:3]:  # Top 3 variations
                    item = InventoryItem(shoe_name=variation, size=size)
                    item.is_sku_search = True
                    if self.stockx_analyzer.search_stockx_for_item(item):
                        alternatives['stockx_alternatives'].append({
                            'sku': item.stockx_sku,
                            'name': item.stockx_shoe_name,
                            'url': item.stockx_url,
                            'variation': variation
                        })
            else:
                # For name searches, try different search terms
                name_variations = self._generate_name_variations(shoe_query)
                for variation in name_variations[:3]:  # Top 3 variations
                    item = InventoryItem(shoe_name=variation, size=size)
                    if self.stockx_analyzer.search_stockx_for_item(item):
                        alternatives['stockx_alternatives'].append({
                            'sku': item.stockx_sku,
                            'name': item.stockx_shoe_name,
                            'url': item.stockx_url,
                            'variation': variation
                        })
            
            # Get Alias alternatives
            search_terms = self.sales_analyzer._extract_search_terms(shoe_query)
            for term in search_terms[:3]:  # Top 3 search terms
                catalog_match = self.sales_analyzer.search_catalog_improved([term])
                if catalog_match:
                    alternatives['alias_alternatives'].append({
                        'sku': catalog_match.get('sku'),
                        'name': catalog_match.get('name'),
                        'catalog_id': catalog_match.get('catalog_id'),
                        'search_term': term
                    })
                    
        except Exception as e:
            print(f"⚠️ Error getting alternatives: {e}")
        
        return alternatives

    def _generate_sku_variations(self, sku: str) -> List[str]:
        """Generate SKU variations for better matching"""
        variations = [sku]
        
        # Try with/without dashes
        if '-' in sku:
            variations.append(sku.replace('-', ' '))
        elif ' ' in sku:
            variations.append(sku.replace(' ', '-'))
        
        # Try with/without spaces
        if ' ' in sku:
            variations.append(sku.replace(' ', ''))
        
        return list(set(variations))  # Remove duplicates

    def _generate_name_variations(self, name: str) -> List[str]:
        """Generate name variations for better matching"""
        variations = [name]
        
        # Common brand variations
        if 'jordan' in name.lower():
            variations.extend([
                name.replace('Jordan', 'Air Jordan'),
                name.replace('Air Jordan', 'Jordan')
            ])
        
        if 'dunk' in name.lower() and 'nike' not in name.lower():
            variations.append(f"Nike {name}")
        
        if 'yeezy' in name.lower() and 'adidas' not in name.lower():
            variations.append(f"Adidas {name}")
        
        return list(set(variations))  # Remove duplicates

    def _calculate_weekly_sales(self, sales_data: List[Dict]) -> Dict:
        """Calculate sales across multiple time periods from sales data"""
        if not sales_data:
            return {
                'sales_per_week': 0, 'sales_per_month': 0, 'sales_per_3months': 0, 
                'sales_per_6months': 0, 'sales_per_year': 0, 'total_sales': 0, 'period_days': 0
            }
        
        # Get current time (use UTC to match API timestamps)
        from datetime import timezone
        now = datetime.now(timezone.utc)
        one_week_ago = now - timedelta(days=7)
        one_month_ago = now - timedelta(days=30)
        three_months_ago = now - timedelta(days=90)
        six_months_ago = now - timedelta(days=180)
        one_year_ago = now - timedelta(days=365)
        
        # Filter sales from different time periods
        recent_sales_week = []
        recent_sales_month = []
        recent_sales_3months = []
        recent_sales_6months = []
        recent_sales_year = []
        all_dates = []
        
        for sale in sales_data:
            date_str = sale.get('purchased_at')
            if date_str:
                try:
                    # Handle ISO format
                    if 'T' in date_str:
                        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    else:
                        dt = datetime.fromisoformat(date_str)
                    
                    all_dates.append(dt)
                    
                    # Count sales from different periods
                    if dt >= one_week_ago:
                        recent_sales_week.append(sale)
                    if dt >= one_month_ago:
                        recent_sales_month.append(sale)
                    if dt >= three_months_ago:
                        recent_sales_3months.append(sale)
                    if dt >= six_months_ago:
                        recent_sales_6months.append(sale)
                    if dt >= one_year_ago:
                        recent_sales_year.append(sale)
                        
                except Exception as e:
                    continue
        
        # Calculate sales for each period
        sales_this_week = len(recent_sales_week)
        sales_this_month = len(recent_sales_month)
        sales_this_3months = len(recent_sales_3months)
        sales_this_6months = len(recent_sales_6months)
        sales_this_year = len(recent_sales_year)
        
        # Get the last 5 sales for detailed analysis
        sorted_sales = sorted(sales_data, key=lambda x: x.get('purchased_at', ''), reverse=True)
        last_5_sales = []
        for sale in sorted_sales[:5]:
            date_str = sale.get('purchased_at')
            price = sale.get('price_cents')
            if date_str and price:
                try:
                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                    price_dollars = float(price) / 100 if price else None
                    last_5_sales.append({
                        'date': dt.isoformat(),
                        'price': price_dollars,
                        'price_cents': price
                    })
                except Exception as e:
                    continue
        
        # Get overall date range for context
        if all_dates:
            earliest = min(all_dates)
            latest = max(all_dates)
            period_days = max(1, (latest - earliest).days)
        else:
            period_days = 0
            earliest = None
            latest = None
        
        return {
            'sales_per_week': round(sales_this_week, 2),
            'sales_per_month': round(sales_this_month, 2),
            'sales_per_3months': round(sales_this_3months, 2),
            'sales_per_6months': round(sales_this_6months, 2),
            'sales_per_year': round(sales_this_year, 2),
            'total_sales': len(sales_data),
            'sales_this_week': sales_this_week,
            'sales_this_month': sales_this_month,
            'sales_this_3months': sales_this_3months,
            'sales_this_6months': sales_this_6months,
            'sales_this_year': sales_this_year,
            'last_5_sales': last_5_sales,
            'period_days': period_days,
            'earliest_sale': earliest.isoformat() if earliest else None,
            'latest_sale': latest.isoformat() if latest else None
        }

    def _apply_pricing_logic(self, stockx_data: Dict, alias_data: Dict, stockx_metadata: Dict, alias_metadata: Dict, size: str) -> Dict:
        """
        Apply the specific pricing logic with all calculations shown
        """
        calculations = {
            'step_1_stockx_analysis': {},
            'step_2_volume_check': {},
            'step_3_ask_calculation': {},
            'step_4_bid_analysis': {},
            'step_5_alias_comparison': {},
            'step_6_final_decision': {}
        }
        
        # Step 1: StockX Analysis
        stockx_bid = stockx_data.get('bid')
        stockx_ask = stockx_data.get('ask')
        
        # Convert to float if they're strings (handle dollar signs)
        try:
            # Remove dollar signs and convert to float
            stockx_bid_clean = str(stockx_bid).replace('$', '').replace(',', '') if stockx_bid else None
            stockx_ask_clean = str(stockx_ask).replace('$', '').replace(',', '') if stockx_ask else None
            
            stockx_bid_float = float(stockx_bid_clean) if stockx_bid_clean else None
            stockx_ask_float = float(stockx_ask_clean) if stockx_ask_clean else None
            bid_ask_spread = stockx_ask_float - stockx_bid_float if stockx_bid_float and stockx_ask_float else None
        except (ValueError, TypeError):
            stockx_bid_float = None
            stockx_ask_float = None
            bid_ask_spread = None
        
        calculations['step_1_stockx_analysis'] = {
            'stockx_bid': stockx_bid_float,
            'stockx_ask': stockx_ask_float,
            'bid_ask_spread': bid_ask_spread,
            'stockx_product_name': stockx_data.get('product_name'),
            'stockx_sku': stockx_data.get('sku'),
            'stockx_url': stockx_data.get('url'),
            'search_query': stockx_metadata.get('search_query'),
            'search_size': stockx_metadata.get('search_size'),
            'notes': 'Retrieved current StockX bid and ask prices'
        }
        
        # Step 2: Volume Check
        weekly_sales = alias_data.get('sales_volume', {}).get('sales_per_week', 0)
        is_high_volume = weekly_sales >= 3
        
        calculations['step_2_volume_check'] = {
            'weekly_sales': weekly_sales,
            'is_high_volume': is_high_volume,
            'threshold': 3,
            'notes': f"High volume = 3+ sales per week. Current: {weekly_sales} sales last week"
        }
        
        # Step 3: Ask Calculation (for high volume)
        if is_high_volume and stockx_ask_float:
            # 20% less than ask, rounded to nearest tens
            ask_minus_20_percent = stockx_ask_float * 0.8
            rounded_ask = round(ask_minus_20_percent / 10) * 10
            
            calculations['step_3_ask_calculation'] = {
                'original_ask': stockx_ask_float,
                'ask_minus_20_percent': round(ask_minus_20_percent, 2),
                'calculation': f"{stockx_ask_float} × 0.8 = {ask_minus_20_percent}",
                'final_price': ask_minus_20_percent,
                'notes': f"High volume: Use 20% less than ask"
            }
        else:
            calculations['step_3_ask_calculation'] = {
                'applies': False,
                'reason': 'Low volume or no ask price available',
                'notes': 'Low volume: Skip ask calculation, go to bid analysis'
            }
        
        # Step 4: Bid Analysis
        if stockx_bid:
            calculations['step_4_bid_analysis'] = {
                'stockx_bid': stockx_bid,
                'notes': 'Current StockX bid price'
            }
        else:
            calculations['step_4_bid_analysis'] = {
                'error': 'No bid price available',
                'notes': 'Cannot proceed without bid price'
            }
        
        # Step 5: Alias/GOAT Comparison
        alias_pricing = alias_data.get('pricing', {})
        
        # Get prices, handling None values properly
        ship_price = alias_pricing.get('ship_to_verify_price')
        consignment_price = alias_pricing.get('consignment_price')
        
        # Filter out None values and find the minimum
        valid_prices = [p for p in [ship_price, consignment_price] if p is not None and p > 0]
        goat_absolute_lowest = min(valid_prices) if valid_prices else None
        
        calculations['step_5_alias_comparison'] = {
            'goat_ship_to_verify': alias_pricing.get('ship_to_verify_price'),
            'goat_consignment': alias_pricing.get('consignment_price'),
            'goat_absolute_lowest': goat_absolute_lowest,
            'alias_product_name': alias_data.get('catalog_match', {}).get('name'),
            'alias_sku': alias_data.get('catalog_match', {}).get('sku'),
            'alias_catalog_id': alias_data.get('catalog_match', {}).get('catalog_id'),
            'search_query': alias_metadata.get('search_query'),
            'search_size': alias_metadata.get('search_size'),
            'notes': 'Use lower of ship-to-verify or consignment price from GOAT/Alias'
        }
        
        # Step 6: Final Decision Logic
        final_price = None
        decision_reason = ""
        calculation_breakdown = ""
        
        if is_high_volume and stockx_ask_float:
            # High volume: Use 20% less than ask
            original_ask = stockx_ask_float
            ask_minus_20 = original_ask * 0.8
            final_price = ask_minus_20
            decision_reason = f"High volume ({weekly_sales} sales last week): StockX Ask (${original_ask}) - 20% = ${ask_minus_20:.1f}"
            calculation_breakdown = f"${original_ask} × 0.8 = ${ask_minus_20:.1f}"
        elif stockx_bid_float and goat_absolute_lowest and goat_absolute_lowest > 0:
            # Low volume: New logic - use 15% less than GOAT absolute lowest
            goat_lowest = goat_absolute_lowest
            bid_price = stockx_bid_float
            percent_diff = ((bid_price - goat_lowest) / goat_lowest) * 100
            
            # Calculate fair price as 15% less than GOAT absolute lowest
            fair_price = goat_lowest * 0.85
            
            final_price = fair_price
            decision_reason = f"Low volume ({weekly_sales} sales last week): StockX Bid (${bid_price}) is {percent_diff:+.1f}% vs GOAT/Alias absolute lowest (${goat_lowest})"
            calculation_breakdown = f"${goat_lowest} × 0.85 = ${fair_price:.1f}"
        elif stockx_bid_float:
            # Only StockX bid available - use 10% less than bid
            bid_price = stockx_bid_float
            fair_price = bid_price * 0.9
            
            final_price = fair_price
            decision_reason = f"Low volume ({weekly_sales} sales last week): Only StockX bid available (${bid_price})"
            calculation_breakdown = f"${bid_price} × 0.9 = ${fair_price:.1f}"
        else:
            # No pricing data available
            final_price = None
            decision_reason = f"Low volume ({weekly_sales} sales last week): No pricing data available - check alternative options"
            calculation_breakdown = "No data available"
        
        calculations['step_6_final_decision'] = {
            'final_price': final_price,
            'decision_reason': decision_reason,
            'calculation_breakdown': calculation_breakdown,
            'recommendation': self._get_recommendation_text(final_price, decision_reason, calculation_breakdown)
        }
        
        return calculations

    def _get_recommendation_text(self, final_price: Optional[float], reason: str, calculation: str) -> str:
        """Generate recommendation text with calculation breakdown"""
        if final_price is None:
            return f"❌ NOT FOUND: {reason} | {calculation}"
        else:
            return f"✅ BUY AT ${final_price:.1f}: {reason} | {calculation}"

    def _generate_recommendation(self, calculations: Dict) -> Dict:
        """Generate final recommendation summary"""
        final_decision = calculations.get('step_6_final_decision', {})
        
        return {
            'action': 'BUY' if final_decision.get('final_price') else 'NO PURCHASE',
            'price': final_decision.get('final_price'),
            'reason': final_decision.get('decision_reason'),
            'recommendation': final_decision.get('recommendation'),
            'confidence': self._calculate_confidence(calculations)
        }

    def _calculate_confidence(self, calculations: Dict) -> str:
        """Calculate confidence level based on data quality"""
        has_stockx = calculations.get('step_1_stockx_analysis', {}).get('stockx_bid') is not None
        has_alias = calculations.get('step_5_alias_comparison', {}).get('goat_absolute_lowest') is not None
        has_volume = calculations.get('step_2_volume_check', {}).get('weekly_sales', 0) > 0
        
        # Check SKU matching (normalized)
        stockx_sku = calculations.get('step_1_stockx_analysis', {}).get('stockx_sku', '')
        alias_sku = calculations.get('step_5_alias_comparison', {}).get('alias_sku', '')
        
        # Normalize SKUs for comparison
        stockx_sku_normalized = stockx_sku.replace('-', '').replace(' ', '') if stockx_sku else ''
        alias_sku_normalized = alias_sku.replace('-', '').replace(' ', '') if alias_sku else ''
        skus_match = stockx_sku_normalized == alias_sku_normalized and stockx_sku_normalized != ''
        
        if has_stockx and has_alias and has_volume:
            return "HIGH"  # High confidence if we have both platforms and volume data
        elif has_stockx and has_alias:
            return "HIGH"  # High confidence if we have both platforms (SKU normalization is expected)
        elif has_stockx:
            return "LOW"
        else:
            return "VERY LOW"

    def _save_result(self, result: Dict) -> str:
        """Save analysis result to file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"advanced_analysis_{timestamp}.json"
            filepath = os.path.join(self.results_dir, filename)
            
            with open(filepath, 'w') as f:
                json.dump(result, f, indent=2)
            
            print(f"💾 Result saved: {filepath}")
            return filepath
        except Exception as e:
            print(f"❌ Failed to save result: {e}")
            return ""

    def get_all_results(self) -> List[Dict]:
        """Get all saved analysis results"""
        results = []
        
        if not os.path.exists(self.results_dir):
            return results
        
        for filename in os.listdir(self.results_dir):
            if filename.startswith('advanced_analysis_') and filename.endswith('.json'):
                filepath = os.path.join(self.results_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        result = json.load(f)
                    results.append(result)
                except Exception as e:
                    print(f"❌ Error loading {filename}: {e}")
        
        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return results

    def delete_result(self, timestamp: str) -> bool:
        """Delete a specific analysis result"""
        try:
            filename = f"advanced_analysis_{timestamp}.json"
            filepath = os.path.join(self.results_dir, filename)
            
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🗑️ Deleted: {filepath}")
                return True
            else:
                print(f"❌ File not found: {filepath}")
                return False
        except Exception as e:
            print(f"❌ Error deleting result: {e}")
            return False

    def _find_corresponding_match(self, better_sku: str, better_name: str, worse_platform: str) -> Optional[Dict]:
        """Find the corresponding match on the other platform using the better SKU"""
        try:
            if worse_platform == 'alias':
                # Find corresponding Alias match using the better StockX SKU
                print(f"   🔍 Finding corresponding Alias match for: {better_sku}")
                
                # Try searching with the better SKU
                search_terms = self.sales_analyzer._extract_search_terms(better_sku)
                catalog_match = self.sales_analyzer.search_catalog_improved(search_terms)
                
                if catalog_match:
                    # Get pricing data for the new match
                    pricing_data = self.stockx_analyzer.get_alias_pricing_data(better_sku, "10")
                    
                    # Get sales volume data
                    try:
                        size_float = 10.0
                        sales_data = self.sales_analyzer._get_sales_for_size(
                            catalog_match['catalog_id'], 
                            size_float
                        )
                        weekly_sales = self._calculate_weekly_sales(sales_data)
                    except Exception as e:
                        weekly_sales = {'sales_per_week': 0, 'error': str(e)}
                    
                    return {
                        'pricing': pricing_data or {},
                        'sales_volume': weekly_sales,
                        'catalog_match': catalog_match
                    }
            
            elif worse_platform == 'stockx':
                # Find corresponding StockX match using the better Alias SKU
                print(f"   🔍 Finding corresponding StockX match for: {better_sku}")
                
                # Create a temporary inventory item
                item = InventoryItem(shoe_name=better_sku, size="10")
                item.is_sku_search = True
                
                # Apply SKU normalization
                normalized_sku = self._normalize_sku_for_search(better_sku)
                if normalized_sku != better_sku:
                    item.shoe_name = normalized_sku
                
                # Search StockX
                success = self.stockx_analyzer.search_stockx_for_item(item)
                
                if success:
                    return {
                        'bid': item.stockx_bid,
                        'ask': item.stockx_ask,
                        'product_name': item.stockx_shoe_name,
                        'sku': item.stockx_sku,
                        'url': item.stockx_url
                    }
            
            return None
            
        except Exception as e:
            print(f"   ❌ Error finding corresponding match: {e}")
            return None

    def _check_sku_mismatch(self, stockx_data: Dict, alias_data: Dict) -> Optional[Dict]:
        """Check for SKU mismatch between StockX and Alias data"""
        stockx_sku = stockx_data.get('sku', '')
        alias_sku = alias_data.get('catalog_match', {}).get('sku', '')
        
        if not stockx_sku or not alias_sku:
            return None
        
        # Normalize SKUs for comparison
        stockx_normalized = self._normalize_sku_for_search(stockx_sku)
        alias_normalized = self._normalize_sku_for_search(alias_sku)
        
        if stockx_normalized != alias_normalized:
            # Determine which match is better (closer to the search query)
            stockx_name = stockx_data.get('product_name', '')
            alias_name = alias_data.get('catalog_match', {}).get('name', '')
            
            # For now, prefer StockX match as it's usually more accurate for SKU searches
            # In the future, we could implement more sophisticated matching logic
            better_match = 'stockx'
            better_sku = stockx_sku
            better_name = stockx_name
            worse_match = 'alias'
            worse_sku = alias_sku
            worse_name = alias_name
            
            return {
                'type': 'SKU_MISMATCH',
                'severity': 'CRITICAL',
                'message': f'StockX and Alias found different shoes! Using StockX match: {stockx_sku} ({stockx_name})',
                'stockx_sku': stockx_sku,
                'stockx_name': stockx_name,
                'alias_sku': alias_sku,
                'alias_name': alias_name,
                'better_match': better_match,
                'better_sku': better_sku,
                'better_name': better_name,
                'worse_match': worse_match,
                'worse_sku': worse_sku,
                'worse_name': worse_name,
                'recommendation': f'Using {better_match.upper()} match. Finding corresponding {worse_match} match...'
            }
        
        return None

    def _should_generate_alternatives(self, stockx_data: Dict, alias_data: Dict, shoe_query: str) -> bool:
        """Determine if alternatives should be auto-generated based on match quality"""
        
        # Case 1: No StockX match found
        if stockx_data.get('error') == 'No StockX match found':
            return True
        
        # Case 2: No Alias match found
        if alias_data.get('error') or not alias_data.get('catalog_match'):
            return True
        
        # Case 3: SKU mismatch detected
        sku_mismatch = self._check_sku_mismatch(stockx_data, alias_data)
        if sku_mismatch:
            return True
        
        # Case 4: Poor quality matches (clothing when searching for shoes)
        stockx_name = stockx_data.get('product_name', '').lower()
        alias_name = alias_data.get('catalog_match', {}).get('name', '').lower()
        
        # Check if found clothing instead of shoes
        clothing_indicators = ['jersey', 'shirt', 'hoodie', 'jacket', 'pants', 'shorts', 'sweatshirt']
        if any(indicator in stockx_name for indicator in clothing_indicators):
            return True
        if any(indicator in alias_name for indicator in clothing_indicators):
            return True
        
        # Case 5: Very generic matches for specific queries
        if len(shoe_query.split()) > 2:  # Specific query like "Jordan 1 Chicago Lost and Found"
            # If we got a generic match, generate alternatives
            if 'jordan' in shoe_query.lower() and 'jordan' in stockx_name:
                if len(stockx_name.split()) < 5:  # Too generic
                    return True
        
        return False

    def generate_alternatives_for_result(self, timestamp: str) -> Dict:
        """Generate alternatives for a specific saved result"""
        try:
            # Load the saved result
            filename = f"advanced_analysis_{timestamp}.json"
            filepath = os.path.join(self.results_dir, filename)
            
            if not os.path.exists(filepath):
                return {'error': 'Result not found'}
            
            with open(filepath, 'r') as f:
                result = json.load(f)
            
            # Generate alternatives
            alternatives = self._get_alternative_matches(result['query'], result['size'])
            
            # Update the result with alternatives
            result['alternatives'] = alternatives
            
            # Save the updated result
            with open(filepath, 'w') as f:
                json.dump(result, f, indent=2)
            
            return alternatives
            
        except Exception as e:
            return {'error': str(e)}

def main():
    """Command line interface"""
    if len(sys.argv) < 2:
        print("🎯 Advanced Shoe Analyzer")
        print("Usage: python advanced_shoe_analyzer.py '<shoe_name>' [size]")
        print("Example: python advanced_shoe_analyzer.py 'Jordan 1 Chicago' 10.5")
        return
    
    shoe_query = " ".join(sys.argv[1:-1]) if len(sys.argv) > 2 else sys.argv[1]
    size = sys.argv[-1] if len(sys.argv) > 2 else "10"
    
    analyzer = AdvancedShoeAnalyzer()
    result = analyzer.analyze_shoe_with_pricing_logic(shoe_query, size)
    
    # Print formatted results
    print("\n" + "="*80)
    print(f"🎯 ADVANCED ANALYSIS: {result['query']} (Size: {result['size']})")
    print("="*80)
    
    if result['success']:
        # Show calculations
        calc = result.get('calculations', {})
        
        print(f"\n📊 STOCKX ANALYSIS:")
        stockx = calc.get('step_1_stockx_analysis', {})
        print(f"   Bid: ${stockx.get('stockx_bid', 'N/A')}")
        print(f"   Ask: ${stockx.get('stockx_ask', 'N/A')}")
        
        print(f"\n📈 VOLUME CHECK:")
        volume = calc.get('step_2_volume_check', {})
        print(f"   Weekly Sales: {volume.get('weekly_sales', 0)}")
        print(f"   High Volume: {volume.get('is_high_volume', False)}")
        
        print(f"\n🧮 PRICING CALCULATIONS:")
        ask_calc = calc.get('step_3_ask_calculation', {})
        if ask_calc.get('applies', True):
            print(f"   Ask - 20%: ${ask_calc.get('ask_minus_20_percent', 'N/A')}")
            print(f"   Final Price: ${ask_calc.get('final_price', 'N/A')}")
        
        print(f"\n💎 GOAT COMPARISON:")
        goat = calc.get('step_5_alias_comparison', {})
        print(f"   GOAT Ask: ${goat.get('goat_ask_used', 'N/A')}")
        
        print(f"\n🎯 FINAL RECOMMENDATION:")
        final = calc.get('step_6_final_decision', {})
        print(f"   {final.get('recommendation', 'No recommendation')}")
        
    else:
        print(f"\n❌ Analysis failed: {result.get('errors', ['Unknown error'])}")
    
    print(f"\n⏱️  Processing time: {result['processing_time']} seconds")

if __name__ == "__main__":
    main() 