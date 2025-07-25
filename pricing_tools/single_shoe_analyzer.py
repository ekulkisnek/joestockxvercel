#!/usr/bin/env python3
"""
🔍 Single Shoe Comprehensive Analyzer
Combines inventory pricing and sales volume analysis for detailed shoe insights
"""

import sys
import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from inventory_stockx_analyzer import InventoryStockXAnalyzer, InventoryItem
from sales_volume_analyzer import SalesVolumeAnalyzer

class SingleShoeAnalyzer:
    def __init__(self):
        """Initialize with both analyzers"""
        # Load authentication
        self.auth_file = "../tokens_full_scope.json"
        self.stockx_analyzer = InventoryStockXAnalyzer()
        self.sales_analyzer = SalesVolumeAnalyzer()
        
        print("🔍 Single Shoe Analyzer initialized")

    def analyze_single_shoe(self, shoe_query: str) -> Dict:
        """Comprehensive analysis of a single shoe"""
        print(f"🔍 Analyzing: {shoe_query}")
        
        start_time = time.time()
        result = {
            'query': shoe_query,
            'timestamp': datetime.now().isoformat(),
            'processing_time': 0,
            'success': False,
            'errors': [],
            'warnings': []
        }

        try:
            # Step 1: StockX/Inventory Analysis
            print("📊 Step 1: Getting StockX pricing data...")
            inventory_data = self._get_inventory_analysis(shoe_query)
            
            # Step 2: Sales Volume Analysis
            print("📈 Step 2: Getting sales volume data...")
            volume_data = self._get_volume_analysis(shoe_query)
            
            # Step 3: Combine and organize results
            print("🔄 Step 3: Combining analysis results...")
            combined_data = self._combine_analyses(inventory_data, volume_data)
            
            result.update(combined_data)
            result['success'] = True
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            result['errors'].append(str(e))
        
        result['processing_time'] = round(time.time() - start_time, 2)
        return result

    def _get_inventory_analysis(self, shoe_query: str) -> Dict:
        """Get StockX pricing and Alias data"""
        try:
            # Create a temporary inventory item
            item = InventoryItem(shoe_name=shoe_query)
            
            # Search StockX
            stockx_data = self.stockx_analyzer.search_stockx_for_item(item)
            
            if not stockx_data:
                return {'error': 'No StockX match found'}
            
            # Get Alias pricing data
            alias_data = self.stockx_analyzer.get_alias_pricing_data(
                stockx_data.get('name', ''), 
                stockx_data.get('sku', '')
            )
            
            return {
                'stockx_data': stockx_data,
                'alias_data': alias_data,
                'success': True
            }
            
        except Exception as e:
            return {'error': str(e)}

    def _get_volume_analysis(self, shoe_query: str) -> Dict:
        """Get sales volume analysis"""
        try:
            # Search catalog
            search_terms = self.sales_analyzer._extract_search_terms(shoe_query)
            catalog_match = self.sales_analyzer.search_catalog_improved(search_terms)
            
            if not catalog_match:
                return {'error': 'No Alias catalog match found'}
            
            # Get size analysis
            analysis = self.sales_analyzer.get_corrected_size_analysis(
                catalog_match['catalog_id'], 
                shoe_query
            )
            
            return {
                'catalog_match': catalog_match,
                'size_analysis': analysis,
                'search_terms': search_terms,
                'success': True
            }
            
        except Exception as e:
            return {'error': str(e)}

    def _combine_analyses(self, inventory_data: Dict, volume_data: Dict) -> Dict:
        """Combine both analyses into organized result"""
        combined = {
            'shoe_identification': {},
            'market_summary': {},
            'sales_performance': {},
            'pricing_insights': {},
            'size_breakdown': {},
            'data_quality': {},
            'detailed_data': {}
        }
        
        # Shoe Identification
        if inventory_data.get('stockx_data'):
            stockx = inventory_data['stockx_data']
            combined['shoe_identification'] = {
                'name': stockx.get('name', 'Unknown'),
                'brand': stockx.get('brand', ''),
                'sku': stockx.get('sku', ''),
                'style_id': stockx.get('style_id', ''),
                'colorway': stockx.get('colorway', ''),
                'release_date': stockx.get('release_date', ''),
                'retail_price': stockx.get('retail_price', 0)
            }
        
        if volume_data.get('catalog_match'):
            catalog = volume_data['catalog_match']
            combined['shoe_identification'].update({
                'alias_brand': catalog.get('brand', ''),
                'alias_model': catalog.get('model', ''),
                'catalog_id': catalog.get('catalog_id', '')
            })

        # Market Summary (Most Important)
        combined['market_summary'] = self._build_market_summary(inventory_data, volume_data)
        
        # Sales Performance
        combined['sales_performance'] = self._build_sales_performance(volume_data)
        
        # Pricing Insights
        combined['pricing_insights'] = self._build_pricing_insights(inventory_data, volume_data)
        
        # Size Breakdown
        combined['size_breakdown'] = self._build_size_breakdown(inventory_data, volume_data)
        
        # Data Quality Assessment
        combined['data_quality'] = self._assess_data_quality(inventory_data, volume_data)
        
        # Store detailed raw data
        combined['detailed_data'] = {
            'inventory_analysis': inventory_data,
            'volume_analysis': volume_data
        }
        
        return combined

    def _build_market_summary(self, inventory_data: Dict, volume_data: Dict) -> Dict:
        """Build the most important market overview"""
        summary = {
            'current_market_price': 'N/A',
            'price_range': 'N/A',
            'sales_velocity': 'N/A',
            'market_activity': 'N/A',
            'recommended_action': 'N/A'
        }
        
        # Current pricing from StockX
        if inventory_data.get('stockx_data', {}).get('variants'):
            variants = inventory_data['stockx_data']['variants']
            bid_prices = [v.get('market_data', {}).get('highest_bid', 0) for v in variants if v.get('market_data', {}).get('highest_bid')]
            ask_prices = [v.get('market_data', {}).get('lowest_ask', 0) for v in variants if v.get('market_data', {}).get('lowest_ask')]
            
            if bid_prices and ask_prices:
                avg_bid = sum(bid_prices) / len(bid_prices)
                avg_ask = sum(ask_prices) / len(ask_prices)
                summary['current_market_price'] = f"${avg_bid:.0f} - ${avg_ask:.0f} (Bid-Ask)"
                summary['price_range'] = f"${min(bid_prices):.0f} - ${max(ask_prices):.0f}"
        
        # Sales velocity from volume analysis
        if volume_data.get('size_analysis', {}).get('overall_metrics'):
            metrics = volume_data['size_analysis']['overall_metrics']
            total_sales = metrics.get('total_sales_all_sizes', 0)
            period_days = metrics.get('analysis_period_days', 1)
            
            if total_sales > 0:
                velocity = total_sales / period_days
                summary['sales_velocity'] = f"{velocity:.1f} sales/day"
                
                # Market activity assessment
                if velocity >= 5:
                    summary['market_activity'] = "🔥 Very High Activity"
                elif velocity >= 2:
                    summary['market_activity'] = "📈 High Activity"
                elif velocity >= 0.5:
                    summary['market_activity'] = "📊 Moderate Activity"
                else:
                    summary['market_activity'] = "📉 Low Activity"
        
        # Generate recommendation
        summary['recommended_action'] = self._generate_recommendation(inventory_data, volume_data)
        
        return summary

    def _build_sales_performance(self, volume_data: Dict) -> Dict:
        """Build sales performance metrics"""
        performance = {
            'total_sales': 0,
            'active_sizes': 0,
            'analysis_period': 'N/A',
            'top_performing_sizes': [],
            'velocity_by_size': {},
            'reliability_flags': []
        }
        
        if not volume_data.get('size_analysis'):
            return performance
        
        overall = volume_data['size_analysis'].get('overall_metrics', {})
        size_data = volume_data['size_analysis'].get('size_data', {})
        
        performance['total_sales'] = overall.get('total_sales_all_sizes', 0)
        performance['active_sizes'] = overall.get('total_sizes_with_data', 0)
        
        # Analysis period
        period_days = overall.get('analysis_period_days', 0)
        if period_days > 0:
            performance['analysis_period'] = f"{period_days} days"
        
        # Top performing sizes
        size_performances = []
        for size, data in size_data.items():
            if data.get('reported_sales_count', 0) > 0:
                size_performances.append({
                    'size': size,
                    'sales': data['reported_sales_count'],
                    'velocity': data['reported_sales_velocity_per_day'],
                    'hit_limit': data.get('hit_api_limit', False)
                })
        
        # Sort by sales count
        size_performances.sort(key=lambda x: x['sales'], reverse=True)
        performance['top_performing_sizes'] = size_performances[:5]
        
        # Velocity by size
        for size_perf in size_performances:
            size = size_perf['size']
            velocity = size_perf['velocity']
            hit_limit = size_perf['hit_limit']
            performance['velocity_by_size'][size] = f"{'≥' if hit_limit else ''}{velocity:.2f}/day"
        
        # Reliability flags
        performance['reliability_flags'] = overall.get('data_reliability_issues', [])
        
        return performance

    def _build_pricing_insights(self, inventory_data: Dict, volume_data: Dict) -> Dict:
        """Build comprehensive pricing insights"""
        insights = {
            'alias_pricing': {},
            'stockx_pricing': {},
            'volume_pricing': {},
            'price_comparison': {}
        }
        
        # Alias pricing data
        if inventory_data.get('alias_data'):
            alias = inventory_data['alias_data']
            insights['alias_pricing'] = {
                'consignment_price': alias.get('consignment_price'),
                'ship_to_verify_price': alias.get('ship_to_verify_price'),
                'lowest_consigned': alias.get('lowest_consigned'),
                'last_consigned_price': alias.get('last_consigned_price'),
                'last_consigned_date': alias.get('last_consigned_date'),
                'lowest_with_you': alias.get('lowest_with_you'),
                'last_with_you_price': alias.get('last_with_you_price'),
                'last_with_you_date': alias.get('last_with_you_date')
            }
        
        # StockX pricing summary
        if inventory_data.get('stockx_data', {}).get('variants'):
            variants = inventory_data['stockx_data']['variants']
            bid_ask_data = []
            
            for variant in variants:
                market_data = variant.get('market_data', {})
                if market_data:
                    bid_ask_data.append({
                        'size': variant.get('size'),
                        'bid': market_data.get('highest_bid'),
                        'ask': market_data.get('lowest_ask')
                    })
            
            insights['stockx_pricing']['size_data'] = bid_ask_data
        
        # Volume-based pricing (from sales data)
        if volume_data.get('size_analysis', {}).get('size_data'):
            size_data = volume_data['size_analysis']['size_data']
            volume_pricing = {}
            
            for size, data in size_data.items():
                if data.get('average_price_cents', 0) > 0:
                    volume_pricing[size] = {
                        'avg_sale_price': data['average_price_cents'] / 100,
                        'min_sale_price': data['min_price_cents'] / 100,
                        'max_sale_price': data['max_price_cents'] / 100,
                        'price_range': data['price_range_cents'] / 100
                    }
            
            insights['volume_pricing'] = volume_pricing
        
        return insights

    def _build_size_breakdown(self, inventory_data: Dict, volume_data: Dict) -> Dict:
        """Build detailed size-by-size breakdown"""
        breakdown = {}
        
        # Get all sizes from both sources
        all_sizes = set()
        
        if inventory_data.get('stockx_data', {}).get('variants'):
            stockx_sizes = {v.get('size') for v in inventory_data['stockx_data']['variants']}
            all_sizes.update(stockx_sizes)
        
        if volume_data.get('size_analysis', {}).get('size_data'):
            volume_sizes = set(volume_data['size_analysis']['size_data'].keys())
            all_sizes.update(volume_sizes)
        
        # Build comprehensive size data
        for size in all_sizes:
            if size is None:
                continue
                
            size_info = {
                'size': size,
                'stockx_data': {},
                'volume_data': {},
                'combined_insights': {}
            }
            
            # StockX data for this size
            if inventory_data.get('stockx_data', {}).get('variants'):
                for variant in inventory_data['stockx_data']['variants']:
                    if variant.get('size') == size:
                        market_data = variant.get('market_data', {})
                        size_info['stockx_data'] = {
                            'highest_bid': market_data.get('highest_bid'),
                            'lowest_ask': market_data.get('lowest_ask'),
                            'last_sale': market_data.get('last_sale'),
                            'sales_last_72h': market_data.get('sales_last_72h', 0)
                        }
                        break
            
            # Volume data for this size
            if volume_data.get('size_analysis', {}).get('size_data', {}).get(size):
                vol_data = volume_data['size_analysis']['size_data'][size]
                size_info['volume_data'] = {
                    'sales_count': vol_data.get('reported_sales_count', 0),
                    'velocity_per_day': vol_data.get('reported_sales_velocity_per_day', 0),
                    'avg_sale_price': vol_data.get('average_price_cents', 0) / 100 if vol_data.get('average_price_cents') else 0,
                    'consigned_percentage': vol_data.get('consigned_percentage', 0),
                    'hit_api_limit': vol_data.get('hit_api_limit', False)
                }
            
            # Combined insights
            size_info['combined_insights'] = self._generate_size_insights(size_info)
            
            breakdown[size] = size_info
        
        return breakdown

    def _assess_data_quality(self, inventory_data: Dict, volume_data: Dict) -> Dict:
        """Assess overall data quality and reliability"""
        quality = {
            'overall_score': 'Good',
            'stockx_quality': 'Unknown',
            'alias_quality': 'Unknown',
            'volume_quality': 'Unknown',
            'warnings': [],
            'recommendations': []
        }
        
        warnings = []
        
        # StockX data quality
        if inventory_data.get('stockx_data'):
            quality['stockx_quality'] = 'Good'
            variants = inventory_data['stockx_data'].get('variants', [])
            if len(variants) == 0:
                warnings.append("No StockX size variants found")
                quality['stockx_quality'] = 'Poor'
        else:
            warnings.append("No StockX data available")
            quality['stockx_quality'] = 'Poor'
        
        # Alias data quality
        if inventory_data.get('alias_data'):
            quality['alias_quality'] = 'Good'
            if not inventory_data['alias_data'].get('consignment_price'):
                warnings.append("No Alias consignment pricing available")
        else:
            warnings.append("No Alias pricing data available")
            quality['alias_quality'] = 'Poor'
        
        # Volume data quality
        if volume_data.get('size_analysis'):
            overall_metrics = volume_data['size_analysis'].get('overall_metrics', {})
            reliability_issues = overall_metrics.get('data_reliability_issues', [])
            
            if not reliability_issues:
                quality['volume_quality'] = 'Good'
            elif len(reliability_issues) <= 2:
                quality['volume_quality'] = 'Fair'
                warnings.extend(reliability_issues)
            else:
                quality['volume_quality'] = 'Poor'
                warnings.extend(reliability_issues)
        else:
            warnings.append("No sales volume data available")
            quality['volume_quality'] = 'Poor'
        
        quality['warnings'] = warnings
        
        # Overall assessment
        poor_count = sum(1 for q in [quality['stockx_quality'], quality['alias_quality'], quality['volume_quality']] if q == 'Poor')
        
        if poor_count == 0:
            quality['overall_score'] = 'Excellent'
        elif poor_count == 1:
            quality['overall_score'] = 'Good'
        elif poor_count == 2:
            quality['overall_score'] = 'Fair'
        else:
            quality['overall_score'] = 'Poor'
        
        return quality

    def _generate_recommendation(self, inventory_data: Dict, volume_data: Dict) -> str:
        """Generate actionable recommendation"""
        # Get key metrics
        has_stockx = bool(inventory_data.get('stockx_data'))
        has_volume = bool(volume_data.get('size_analysis'))
        
        if not has_stockx and not has_volume:
            return "❌ Insufficient data for recommendations"
        
        # Sales velocity check
        velocity = 0
        if has_volume:
            metrics = volume_data['size_analysis'].get('overall_metrics', {})
            total_sales = metrics.get('total_sales_all_sizes', 0)
            period_days = metrics.get('analysis_period_days', 1)
            velocity = total_sales / period_days if period_days > 0 else 0
        
        # Price gap analysis
        price_gap = "unknown"
        if inventory_data.get('stockx_data', {}).get('variants'):
            variants = inventory_data['stockx_data']['variants']
            bid_prices = [v.get('market_data', {}).get('highest_bid', 0) for v in variants if v.get('market_data', {}).get('highest_bid')]
            ask_prices = [v.get('market_data', {}).get('lowest_ask', 0) for v in variants if v.get('market_data', {}).get('lowest_ask')]
            
            if bid_prices and ask_prices:
                avg_bid = sum(bid_prices) / len(bid_prices)
                avg_ask = sum(ask_prices) / len(ask_prices)
                gap_percent = ((avg_ask - avg_bid) / avg_bid) * 100 if avg_bid > 0 else 0
                
                if gap_percent < 5:
                    price_gap = "tight"
                elif gap_percent < 15:
                    price_gap = "moderate"
                else:
                    price_gap = "wide"
        
        # Generate recommendation
        if velocity >= 2 and price_gap == "tight":
            return "🔥 STRONG BUY - High sales velocity with tight bid-ask spread"
        elif velocity >= 2:
            return "📈 CONSIDER BUYING - High sales activity indicates strong demand"
        elif velocity >= 0.5 and price_gap == "tight":
            return "✅ GOOD OPPORTUNITY - Steady sales with efficient pricing"
        elif velocity >= 0.5:
            return "📊 MONITOR - Moderate activity, watch for price improvements"
        elif price_gap == "wide":
            return "⚠️  CAUTION - Low activity with wide price spreads"
        else:
            return "📉 AVOID - Low sales activity, limited market interest"

    def _generate_size_insights(self, size_info: Dict) -> Dict:
        """Generate insights for a specific size"""
        insights = {
            'recommendation': 'No data',
            'profit_potential': 'Unknown',
            'market_position': 'Unknown'
        }
        
        stockx = size_info.get('stockx_data', {})
        volume = size_info.get('volume_data', {})
        
        # Basic recommendation based on available data
        if stockx.get('highest_bid') and stockx.get('lowest_ask'):
            bid = stockx['highest_bid']
            ask = stockx['lowest_ask']
            spread = ask - bid
            spread_percent = (spread / bid) * 100 if bid > 0 else 0
            
            if spread_percent < 5:
                insights['market_position'] = "Liquid market"
            elif spread_percent < 15:
                insights['market_position'] = "Moderately liquid"
            else:
                insights['market_position'] = "Illiquid market"
        
        # Sales activity assessment
        velocity = volume.get('velocity_per_day', 0)
        if velocity >= 1:
            insights['recommendation'] = "Active size - good for trading"
        elif velocity >= 0.2:
            insights['recommendation'] = "Moderate activity"
        elif velocity > 0:
            insights['recommendation'] = "Low activity - patience required"
        else:
            insights['recommendation'] = "No recent sales data"
        
        return insights


def main():
    """Command line interface"""
    if len(sys.argv) < 2:
        print("🔍 Single Shoe Analyzer")
        print("Usage: python single_shoe_analyzer.py '<shoe_name>'")
        print("Example: python single_shoe_analyzer.py 'Jordan 1 Chicago'")
        return
    
    shoe_query = " ".join(sys.argv[1:])
    analyzer = SingleShoeAnalyzer()
    
    result = analyzer.analyze_single_shoe(shoe_query)
    
    # Print formatted results
    print("\n" + "="*80)
    print(f"🔍 COMPREHENSIVE ANALYSIS: {result['query']}")
    print("="*80)
    
    if result['success']:
        # Market Summary
        market = result.get('market_summary', {})
        print(f"\n💰 MARKET SUMMARY:")
        print(f"   Current Price: {market.get('current_market_price', 'N/A')}")
        print(f"   Sales Velocity: {market.get('sales_velocity', 'N/A')}")
        print(f"   Market Activity: {market.get('market_activity', 'N/A')}")
        print(f"   Recommendation: {market.get('recommended_action', 'N/A')}")
        
        # Top sizes by sales
        performance = result.get('sales_performance', {})
        if performance.get('top_performing_sizes'):
            print(f"\n📊 TOP PERFORMING SIZES:")
            for size_data in performance['top_performing_sizes'][:3]:
                size = size_data['size']
                sales = size_data['sales']
                velocity = size_data['velocity']
                limit_flag = "≥" if size_data['hit_limit'] else ""
                print(f"   Size {size}: {limit_flag}{sales} sales ({limit_flag}{velocity:.2f}/day)")
    
    else:
        print(f"\n❌ Analysis failed: {result.get('errors', ['Unknown error'])}")
    
    print(f"\n⏱️  Processing time: {result['processing_time']} seconds")


if __name__ == "__main__":
    main() 