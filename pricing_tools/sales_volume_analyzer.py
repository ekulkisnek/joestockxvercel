#!/usr/bin/env python3
"""
📊 Sales Volume Analyzer
Flexible tool to analyze sales volume for any inventory CSV format using Alias API
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
from collections import defaultdict

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure immediate output flushing for real-time web interface progress
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None

class SalesVolumeAnalyzer:
    def __init__(self):
        """Initialize with Alias API configuration"""
        self.api_key = "goatapi_167AEOZwPmcFAwZ2RbHv7AaGfSYpdF2wq1zdxzT"
        self.base_url = "https://api.alias.org/api/v1"
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.api_key}',
            'User-Agent': 'Python-SalesVolumeAnalyzer/1.0'
        })
        self.API_LIMIT = 200  # Maximum results per API call
        self.processed_count = 0
        self.success_count = 0
        
        print("📊 Sales Volume Analyzer initialized")
        print(f"🔑 API configured for: {self.base_url}")

    def test_connection(self) -> bool:
        """Test API connection"""
        try:
            response = self.session.get(f"{self.base_url}/test", timeout=30)
            return response.status_code == 200
        except Exception as e:
            print(f"❌ Connection test failed: {e}")
            return False

    def parse_csv_flexible(self, csv_file: str) -> List[Dict]:
        """Parse CSV file flexibly to extract shoe information"""
        print(f"📋 Parsing CSV file: {csv_file}", flush=True)
        
        shoes = []
        
        # Read and parse as CSV
        with open(csv_file, 'r', encoding='utf-8') as file:
            lines = list(csv.reader(file))

        if not lines:
            print("❌ Empty CSV file")
            return shoes

        # Detect headers
        self.original_headers = lines[0] if lines else []
        self.has_headers = self._looks_like_header_row(self.original_headers)
        
        start_row = 1 if self.has_headers else 0
        
        # Try to detect which columns contain shoe information
        shoe_col = self._detect_shoe_column(lines)
        
        processed_names = set()  # Track duplicates
        
        for i in range(start_row, len(lines)):
            row = lines[i]
            if not row or all(not cell.strip() for cell in row):
                continue

            # Extract shoe name
            shoe_name = ""
            if shoe_col is not None and shoe_col < len(row):
                shoe_name = row[shoe_col].strip()
            elif len(row) > 0:
                # Fallback: use first non-empty cell
                for cell in row:
                    if cell and cell.strip():
                        shoe_name = cell.strip()
                        break

            if shoe_name and self._looks_like_shoe_name(shoe_name):
                # Skip duplicates
                if shoe_name not in processed_names:
                    search_terms = self._extract_search_terms(shoe_name)
                    
                    shoes.append({
                        'original_name': shoe_name,
                        'search_terms': search_terms,
                        'csv_row': i + 1
                    })
                    processed_names.add(shoe_name)

        print(f"✅ Found {len(shoes)} unique shoes for analysis", flush=True)
        return shoes

    def _looks_like_header_row(self, row: List[str]) -> bool:
        """Check if this row looks like a CSV header"""
        if not row:
            return False
        
        # Common header indicators
        header_words = ['shoe', 'name', 'size', 'price', 'brand', 'style', 'sku', 'product', 'model']
        first_few_cells = ' '.join(row[:3]).lower()
        
        return any(word in first_few_cells for word in header_words)

    def _detect_shoe_column(self, lines: List[List[str]]) -> Optional[int]:
        """Detect which column is most likely to contain shoe names"""
        if not lines:
            return None
            
        # Analyze first few data rows to find the column with shoe-like content
        sample_rows = lines[1:min(6, len(lines))] if self.has_headers else lines[:5]
        
        column_scores = defaultdict(int)
        
        for row in sample_rows:
            for i, cell in enumerate(row):
                if cell and self._looks_like_shoe_name(cell):
                    column_scores[i] += 1
        
        if column_scores:
            return max(column_scores, key=column_scores.get)
        
        return 0  # Default to first column

    def _looks_like_shoe_name(self, text: str) -> bool:
        """Check if text looks like a shoe name or SKU"""
        if not text or len(text) < 3:
            return False

        text_upper = text.upper()
        
        # Skip obvious non-shoe content
        skip_patterns = [
            'TOTAL', 'SIZE', 'QTY', 'QUANTITY', 'WS,', '#REF!', 
            'SUBTOTAL', 'GRAND TOTAL', r'^\d+$'  # Just numbers
        ]
        
        for pattern in skip_patterns:
            if re.match(pattern, text_upper) or pattern in text_upper:
                return False

        # Look for shoe indicators
        shoe_indicators = [
            'JORDAN', 'NIKE', 'ADIDAS', 'YEEZY', 'DUNK', 'AIR', 'SAMBA', 
            'HANDBALL', 'CAMPUS', 'GAZELLE', 'FORCE', 'BALANCE'
        ]
        
        # SKU patterns (letters + numbers)
        has_letters = bool(re.search(r'[A-Za-z]', text))
        has_numbers = bool(re.search(r'\d', text))
        
        # Check for shoe brand/model names or SKU-like patterns
        has_shoe_terms = any(term in text_upper for term in shoe_indicators)
        looks_like_sku = has_letters and has_numbers and len(text) >= 4
        
        return has_shoe_terms or looks_like_sku

    def _extract_search_terms(self, full_name: str) -> List[str]:
        """Extract clean search terms from shoe names - adapted from provided code"""
        # Extract SKU/model numbers
        sku_match = re.match(r'^([A-Z0-9\-\s]+)\s+(.+)', full_name)
        if sku_match:
            sku = sku_match.group(1).strip()
            clean_name = sku_match.group(2).strip()
        else:
            sku = ""
            clean_name = full_name

        search_terms = []

        # Add SKU-based searches (these often work best)
        if sku and len(sku) >= 4:
            search_terms.extend([
                sku,  # Just the SKU
                f"{sku} {clean_name}",  # SKU + name
                full_name  # Original full name
            ])

        # Remove parenthetical sizing info for broader search
        base_name = re.sub(r'\s*\([^)]*\).*$', '', clean_name)
        if base_name:
            search_terms.append(base_name)

        # Brand-specific variations
        upper_name = full_name.upper()

        if 'JORDAN' in upper_name:
            jordan_match = re.search(r'JORDAN\s+(\d+)', upper_name)
            if jordan_match:
                model_num = jordan_match.group(1)
                search_terms.extend([
                    f"Air Jordan {model_num}",
                    f"Jordan {model_num}",
                ])

                if 'MID' in upper_name:
                    search_terms.extend([f"Air Jordan {model_num} Mid"])
                elif 'LOW' in upper_name:
                    search_terms.extend([f"Air Jordan {model_num} Low"])

                if 'RARE AIR' in upper_name:
                    search_terms.extend([f"Jordan {model_num} Rare Air"])

        elif 'SAMBA' in upper_name:
            search_terms.extend(["Samba OG", "Adidas Samba"])
            if 'XLG' in upper_name:
                search_terms.extend(["Samba XLG"])
            elif 'SAMBAE' in upper_name:
                search_terms.extend(["Sambae"])

        elif 'HANDBALL' in upper_name and 'SPEZIAL' in upper_name:
            search_terms.extend(["Handball Spezial", "Adidas Handball Spezial"])

        elif 'CAMPUS' in upper_name:
            search_terms.extend(["Campus 00s", "Adidas Campus 00s"])

        elif 'GAZELLE' in upper_name:
            search_terms.extend(["Gazelle Indoor", "Adidas Gazelle"])

        elif 'DUNK' in upper_name:
            if 'LOW' in upper_name:
                search_terms.extend(["Dunk Low", "Nike Dunk Low"])

        elif '9060' in upper_name:
            search_terms.extend(["New Balance 9060", "9060"])

        # Add the original cleaned name as fallback
        search_terms.append(clean_name)

        # Remove duplicates and empty strings
        search_terms = list(set([term.strip() for term in search_terms if term.strip()]))

        return search_terms

    def search_catalog_improved(self, search_terms: List[str]) -> Optional[Dict]:
        """Improved catalog search using multiple search terms"""
        for term in search_terms:
            try:
                params = {'query': term, 'limit': 5}
                response = self.session.get(f"{self.base_url}/catalog", params=params, timeout=30)

                if response.status_code == 200:
                    results = response.json().get('catalog_items', [])
                    if results:
                        print(f"         ✅ Found match with query: '{term}'", flush=True)
                        return results[0]

                time.sleep(0.2)  # Small delay between search attempts

            except Exception as e:
                print(f"         ⚠️  Search error for '{term}': {e}", flush=True)
                continue

        return None

    def get_corrected_size_analysis(self, catalog_id: str, shoe_name: str) -> Dict:
        """Get size analysis with proper limit handling and reliability flags"""
        print(f"      📊 Getting size analysis for {shoe_name[:30]}...", flush=True)

        # Determine size range based on shoe type
        is_womens = any(word in shoe_name.lower() for word in ['women', 'wmns', 'w '])
        is_gs = 'gs' in shoe_name.lower() or 'grade school' in shoe_name.lower()

        if is_gs:
            sizes_to_check = [3.5, 4, 4.5, 5, 5.5, 6, 6.5, 7]
        elif is_womens:
            sizes_to_check = [5, 5.5, 6, 6.5, 7, 7.5, 8, 8.5, 9, 9.5, 10, 10.5]
        else:
            sizes_to_check = [7, 7.5, 8, 8.5, 9, 9.5, 10, 10.5, 11, 11.5, 12, 12.5]

        size_results = {}
        overall_stats = {
            'total_sales_all_sizes': 0,
            'total_sizes_with_data': 0,
            'analysis_period_days': 0,
            'earliest_sale': None,
            'latest_sale': None,
            'data_reliability_issues': []
        }

        for size in sizes_to_check:
            try:
                # Get sales data with maximum limit
                sales_data = self._get_sales_for_size(catalog_id, size)

                if sales_data:
                    # Calculate metrics with reliability flags
                    size_metrics = self._calculate_size_metrics(sales_data, size)
                    size_results[size] = size_metrics

                    # Update overall stats
                    if size_metrics['hit_api_limit']:
                        overall_stats['data_reliability_issues'].append(f"Size {size} hit API limit")

                    overall_stats['total_sales_all_sizes'] += size_metrics['reported_sales_count']
                    if size_metrics['reported_sales_count'] > 0:
                        overall_stats['total_sizes_with_data'] += 1

                    # Track time period
                    if size_metrics['earliest_sale']:
                        if not overall_stats['earliest_sale'] or size_metrics['earliest_sale'] < overall_stats['earliest_sale']:
                            overall_stats['earliest_sale'] = size_metrics['earliest_sale']

                    if size_metrics['latest_sale']:
                        if not overall_stats['latest_sale'] or size_metrics['latest_sale'] > overall_stats['latest_sale']:
                            overall_stats['latest_sale'] = size_metrics['latest_sale']
                else:
                    size_results[size] = self._empty_size_metrics()

                time.sleep(0.1)  # Rate limiting

            except Exception as e:
                print(f"         ⚠️  Error for size {size}: {e}", flush=True)
                size_results[size] = self._empty_size_metrics()

        # Calculate overall time period
        if overall_stats['earliest_sale'] and overall_stats['latest_sale']:
            try:
                earliest = datetime.fromisoformat(overall_stats['earliest_sale'].replace('Z', '+00:00'))
                latest = datetime.fromisoformat(overall_stats['latest_sale'].replace('Z', '+00:00'))
                overall_stats['analysis_period_days'] = max(1, (latest - earliest).days)
            except:
                overall_stats['analysis_period_days'] = 1

        # Add overall reliability warnings
        sizes_hitting_limit = len([s for s in size_results.values() if s.get('hit_api_limit')])
        if sizes_hitting_limit > 0:
            overall_stats['data_reliability_issues'].append(f"{sizes_hitting_limit} sizes hit API limit - actual sales/velocity higher")

        return {
            'size_data': size_results,
            'overall_metrics': overall_stats
        }

    def _get_sales_for_size(self, catalog_id: str, size: float) -> List[Dict]:
        """Get sales data for a specific size"""
        try:
            params = {
                'catalog_id': catalog_id,
                'size': size,
                'limit': self.API_LIMIT,
                'product_condition': 'PRODUCT_CONDITION_NEW',
                'packaging_condition': 'PACKAGING_CONDITION_GOOD_CONDITION'
            }

            response = self.session.get(f"{self.base_url}/pricing_insights/recent_sales",
                                      params=params, timeout=30)

            if response.status_code == 200:
                sales = response.json().get('recent_sales', [])
                return sales
            else:
                return []

        except Exception as e:
            return []

    def _calculate_size_metrics(self, sales_data: List[Dict], size: float) -> Dict:
        """Calculate metrics with proper limit handling"""
        if not sales_data:
            return self._empty_size_metrics()

        reported_sales_count = len(sales_data)
        hit_api_limit = (reported_sales_count == self.API_LIMIT)

        prices = []
        consigned_count = 0
        dates = []

        for sale in sales_data:
            # Price data
            if sale.get('price_cents'):
                try:
                    prices.append(int(sale['price_cents']))
                except:
                    pass

            # Consignment tracking
            if sale.get('consigned'):
                consigned_count += 1

            # Date tracking
            if sale.get('purchased_at'):
                dates.append(sale['purchased_at'])

        # Time period calculation
        earliest_sale = min(dates) if dates else None
        latest_sale = max(dates) if dates else None

        period_days = 1
        sales_velocity = reported_sales_count

        if earliest_sale and latest_sale:
            try:
                earliest_dt = datetime.fromisoformat(earliest_sale.replace('Z', '+00:00'))
                latest_dt = datetime.fromisoformat(latest_sale.replace('Z', '+00:00'))
                period_days = max(1, (latest_dt - earliest_dt).days)
                sales_velocity = reported_sales_count / period_days
            except:
                pass

        # Price calculations
        avg_price = sum(prices) // len(prices) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0
        price_range = max_price - min_price if len(prices) > 1 else 0

        return {
            'reported_sales_count': reported_sales_count,
            'hit_api_limit': hit_api_limit,
            'actual_sales_unknown': hit_api_limit,
            'period_days': period_days,
            'reported_sales_velocity_per_day': round(sales_velocity, 3),
            'velocity_is_minimum': hit_api_limit,
            'consigned_count': consigned_count,
            'consigned_percentage': round((consigned_count / reported_sales_count * 100), 1) if reported_sales_count > 0 else 0,
            'average_price_cents': avg_price,
            'price_based_on_recent_only': hit_api_limit,
            'min_price_cents': min_price,
            'max_price_cents': max_price,
            'price_range_cents': price_range,
            'earliest_sale': earliest_sale,
            'latest_sale': latest_sale
        }

    def _empty_size_metrics(self) -> Dict:
        """Return empty metrics for sizes with no data"""
        return {
            'reported_sales_count': 0,
            'hit_api_limit': False,
            'actual_sales_unknown': False,
            'period_days': 0,
            'reported_sales_velocity_per_day': 0,
            'velocity_is_minimum': False,
            'consigned_count': 0,
            'consigned_percentage': 0,
            'average_price_cents': 0,
            'price_based_on_recent_only': False,
            'min_price_cents': 0,
            'max_price_cents': 0,
            'price_range_cents': 0,
            'earliest_sale': None,
            'latest_sale': None
        }

    def analyze_all_shoes(self, csv_file: str) -> List[Dict]:
        """Analyze all shoes with proper limit handling"""
        shoes = self.parse_csv_flexible(csv_file)
        if not shoes:
            print("❌ No shoes found to analyze")
            return []

        results = []
        catalog_id_tracker = {}  # Track duplicate catalog IDs

        print(f"\n🔍 Processing {len(shoes)} shoes...", flush=True)
        print(f"⏱️  Estimated time: {len(shoes) * 0.5 / 60:.1f} minutes", flush=True)
        print("🔄 Processing with API rate limiting", flush=True)
        print("=" * 80, flush=True)

        start_time = time.time()

        for i, shoe in enumerate(shoes, 1):
            print(f"\n[{i}/{len(shoes)}] {shoe['original_name'][:50]}...", flush=True)

            try:
                # Search for catalog match
                catalog_match = self.search_catalog_improved(shoe['search_terms'])

                if catalog_match:
                    catalog_id = catalog_match.get('catalog_id')
                    print(f"      ✅ Found catalog ID: {catalog_id}", flush=True)

                    # Check if we've seen this catalog ID before
                    is_duplicate_catalog = catalog_id in catalog_id_tracker
                    if is_duplicate_catalog:
                        print(f"      ⚠️  WARNING: Duplicate catalog ID - data may be identical to {catalog_id_tracker[catalog_id]}", flush=True)
                    else:
                        catalog_id_tracker[catalog_id] = shoe['original_name']

                    # Get analysis
                    analysis = self.get_corrected_size_analysis(catalog_id, shoe['original_name'])

                    result = {
                        'shoe_info': shoe,
                        'catalog_match': catalog_match,
                        'analysis': analysis,
                        'is_duplicate_catalog': is_duplicate_catalog,
                        'duplicate_of': catalog_id_tracker.get(catalog_id) if is_duplicate_catalog else None,
                        'timestamp': datetime.now().isoformat()
                    }

                    self.success_count += 1

                else:
                    print(f"      ❌ No catalog match found", flush=True)
                    result = {
                        'shoe_info': shoe,
                        'catalog_match': None,
                        'error': 'No catalog match found',
                        'timestamp': datetime.now().isoformat()
                    }

                results.append(result)
                self.processed_count += 1

                # Progress update every 5 items
                if i % 5 == 0:
                    elapsed = time.time() - start_time
                    remaining_items = len(shoes) - i
                    remaining_time = (remaining_items * 0.5) / 60  # 0.5 seconds per item estimate

                    progress_percent = (i / len(shoes)) * 100
                    print(f"   📊 Progress: {i}/{len(shoes)} ({progress_percent:.1f}%) - {self.success_count} matches found", flush=True)
                    print(f"   ⏱️  Estimated time remaining: {remaining_time:.1f} minutes", flush=True)

                time.sleep(0.5)  # Delay between shoes

            except Exception as e:
                print(f"      ❌ Error: {e}", flush=True)
                results.append({
                    'shoe_info': shoe,
                    'error': str(e),
                    'timestamp': datetime.now().isoformat()
                })

        return results

    def save_results_csv(self, results: List[Dict], output_file: str) -> str:
        """Save results to CSV with proper limit handling and reliability flags"""
        print(f"\n💾 Saving sales volume analysis to {output_file}...", flush=True)

        fieldnames = [
            # Shoe identification
            'shoe_name', 'brand', 'model', 'catalog_id', 'size',

            # Data reliability flags
            'data_reliability_warning', 'is_duplicate_catalog_data', 'duplicate_of_shoe',

            # Time period info
            'analysis_period_days', 'data_date_range_start', 'data_date_range_end',

            # Sales metrics with reliability indicators
            'sales_count_display', 'sales_count_raw', 'hit_api_limit',
            'sales_velocity_display', 'sales_velocity_raw', 'velocity_is_minimum',
            'consigned_sales_this_size', 'consigned_percentage_this_size',

            # Overall shoe performance
            'total_sales_all_sizes', 'total_active_sizes',

            # Pricing data with reliability notes
            'avg_sale_price_this_size', 'price_based_on_recent_only',
            'min_sale_price_this_size', 'max_sale_price_this_size', 'price_range_this_size',

            # Analysis metadata
            'search_terms_used', 'error_message', 'analysis_timestamp'
        ]

        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for result in results:
                if result.get('catalog_match') and result.get('analysis'):
                    shoe_info = result['shoe_info']
                    catalog_match = result['catalog_match']
                    analysis = result['analysis']

                    overall_metrics = analysis['overall_metrics']

                    # Create a row for each size with data
                    for size, size_data in analysis['size_data'].items():
                        if size_data['reported_sales_count'] > 0:  # Only include sizes with actual sales

                            # Build reliability warning
                            warnings = []
                            if size_data['hit_api_limit']:
                                warnings.append("Sales capped at API limit")
                            if size_data['velocity_is_minimum']:
                                warnings.append("Velocity is minimum")
                            if size_data['price_based_on_recent_only']:
                                warnings.append("Prices from recent sales only")
                            if result.get('is_duplicate_catalog'):
                                warnings.append("Duplicate catalog data")

                            reliability_warning = "; ".join(warnings) if warnings else "Data appears complete"

                            row = {
                                # Shoe identification
                                'shoe_name': shoe_info['original_name'],
                                'brand': catalog_match.get('brand', ''),
                                'model': catalog_match.get('model', ''),
                                'catalog_id': catalog_match.get('catalog_id', ''),
                                'size': size,

                                # Data reliability
                                'data_reliability_warning': reliability_warning,
                                'is_duplicate_catalog_data': result.get('is_duplicate_catalog', False),
                                'duplicate_of_shoe': result.get('duplicate_of', ''),

                                # Time period
                                'analysis_period_days': overall_metrics['analysis_period_days'],
                                'data_date_range_start': overall_metrics['earliest_sale'],
                                'data_date_range_end': overall_metrics['latest_sale'],

                                # Sales metrics with proper display
                                'sales_count_display': f"≥{size_data['reported_sales_count']}" if size_data['hit_api_limit'] else str(size_data['reported_sales_count']),
                                'sales_count_raw': size_data['reported_sales_count'],
                                'hit_api_limit': size_data['hit_api_limit'],

                                'sales_velocity_display': f"≥{size_data['reported_sales_velocity_per_day']}" if size_data['velocity_is_minimum'] else str(size_data['reported_sales_velocity_per_day']),
                                'sales_velocity_raw': size_data['reported_sales_velocity_per_day'],
                                'velocity_is_minimum': size_data['velocity_is_minimum'],

                                'consigned_sales_this_size': size_data['consigned_count'],
                                'consigned_percentage_this_size': size_data['consigned_percentage'],

                                # Overall metrics
                                'total_sales_all_sizes': overall_metrics['total_sales_all_sizes'],
                                'total_active_sizes': overall_metrics['total_sizes_with_data'],

                                # Pricing
                                'avg_sale_price_this_size': round(size_data['average_price_cents'] / 100, 2) if size_data['average_price_cents'] else '',
                                'price_based_on_recent_only': size_data['price_based_on_recent_only'],
                                'min_sale_price_this_size': round(size_data['min_price_cents'] / 100, 2) if size_data['min_price_cents'] else '',
                                'max_sale_price_this_size': round(size_data['max_price_cents'] / 100, 2) if size_data['max_price_cents'] else '',
                                'price_range_this_size': round(size_data['price_range_cents'] / 100, 2) if size_data['price_range_cents'] else '',

                                # Metadata
                                'search_terms_used': '; '.join(shoe_info['search_terms']),
                                'error_message': '',
                                'analysis_timestamp': result.get('timestamp', '')
                            }

                            writer.writerow(row)

                else:
                    # Error row
                    row = {
                        'shoe_name': result['shoe_info']['original_name'],
                        'search_terms_used': '; '.join(result['shoe_info']['search_terms']),
                        'error_message': result.get('error', 'Unknown error'),
                        'analysis_timestamp': result.get('timestamp', '')
                    }
                    # Fill other fields with empty values
                    for field in fieldnames:
                        if field not in row:
                            row[field] = ''

                    writer.writerow(row)

        return output_file

    def process_sales_volume(self, csv_file: str, output_file: str = None) -> str:
        """Main processing function for sales volume analysis"""
        if not output_file:
            input_path = Path(csv_file)
            output_filename = f"sales_volume_analysis_{input_path.stem}.csv"
            output_file = input_path.parent / output_filename

        print(f"📊 Processing sales volume analysis: {csv_file}", flush=True)
        print(f"💾 Output will be saved to: {output_file}", flush=True)
        print("=" * 80, flush=True)

        # Test connection first
        print("🔗 Testing API connection...", flush=True)
        if not self.test_connection():
            print("❌ Failed to connect to Alias API")
            return ""

        print("✅ API connection successful!", flush=True)

        # Run analysis
        start_time = time.time()
        results = self.analyze_all_shoes(csv_file)

        if not results:
            print("❌ No results generated")
            return ""

        # Save results
        self.save_results_csv(results, output_file)

        # Print summary
        print(f"\n" + "=" * 80, flush=True)
        print(f"📊 SALES VOLUME ANALYSIS COMPLETE!", flush=True)
        print(f"✅ Processed: {self.processed_count} shoes", flush=True)
        print(f"🎯 Found matches: {self.success_count} shoes", flush=True)
        print(f"💾 Results saved: {output_file}", flush=True)

        # Show top performers
        successful = [r for r in results if r.get('catalog_match')]
        if successful:
            print(f"\n🏆 TOP SALES PERFORMERS:", flush=True)
            sorted_shoes = sorted(successful,
                                key=lambda x: x.get('analysis', {}).get('overall_metrics', {}).get('total_sales_all_sizes', 0),
                                reverse=True)

            for i, shoe in enumerate(sorted_shoes[:5], 1):
                overall = shoe.get('analysis', {}).get('overall_metrics', {})
                shoe_name = shoe['shoe_info']['original_name'][:40]
                total_sales = overall.get('total_sales_all_sizes', 0)
                period_days = overall.get('analysis_period_days', 0)
                velocity = total_sales / period_days if period_days > 0 else 0

                print(f"  {i}. {shoe_name:<40} | Sales: {total_sales:3d} | Velocity: {velocity:5.2f}/day", flush=True)

        elapsed_time = time.time() - start_time
        print(f"\n⏱️  Total processing time: {elapsed_time/60:.1f} minutes", flush=True)

        return str(output_file)


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("📊 Sales Volume Analyzer")
        print("=" * 40)
        print("Usage:")
        print("  python sales_volume_analyzer.py <csv_file>")
        print()
        print("Example:")
        print("  python sales_volume_analyzer.py inventory.csv")
        return

    input_file = sys.argv[1]
    if not Path(input_file).exists():
        print(f"❌ Error: File not found: {input_file}")
        return

    analyzer = SalesVolumeAnalyzer()
    try:
        output_file = analyzer.process_sales_volume(input_file)
        print(f"\n🎉 Sales volume analysis complete! Check {output_file} for results.")
    except Exception as e:
        print(f"❌ Error processing file: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 