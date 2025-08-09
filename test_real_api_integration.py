#!/usr/bin/env python3
"""
🧪 Real API Integration Test
Testing parallel execution with actual API calls from the existing codebase
"""

import asyncio
import time
import json
import concurrent.futures
import threading
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
import sys
import os

# Add the pricing_tools directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'pricing_tools'))

try:
    from advanced_shoe_analyzer import AdvancedShoeAnalyzer
    from inventory_stockx_analyzer import InventoryStockXAnalyzer
    from sales_volume_analyzer import SalesVolumeAnalyzer
except ImportError as e:
    print(f"⚠️ Could not import required modules: {e}")
    print("This test requires the actual codebase to be available.")
    sys.exit(1)

class RealAPITester:
    """Test suite for real API integration"""
    
    def __init__(self):
        self.analyzer = AdvancedShoeAnalyzer()
        self.test_shoes = [
            "Nike Air Jordan 1 Retro High OG",
            "Adidas Yeezy Boost 350 V2", 
            "Nike Air Force 1 Low"
        ]
        self.test_size = "10"
        self.results = {}
        
    def test_sequential_real_api(self) -> Dict:
        """Test sequential execution with real APIs"""
        print("\n🔍 Testing Sequential Execution (Real APIs)")
        print("-" * 40)
        
        start_time = time.time()
        results = []
        
        for i, shoe in enumerate(self.test_shoes, 1):
            print(f"Processing {i}/{len(self.test_shoes)}: {shoe[:30]}...")
            
            try:
                # Use the actual analyzer method
                result = self.analyzer.analyze_shoe_with_pricing_logic(shoe, self.test_size)
                results.append({
                    'shoe': shoe,
                    'result': result,
                    'success': 'error' not in result
                })
                
                # Add delay to avoid rate limiting
                time.sleep(2.0)
                
            except Exception as e:
                results.append({
                    'shoe': shoe,
                    'error': str(e),
                    'success': False
                })
        
        total_time = time.time() - start_time
        avg_time = total_time / len(self.test_shoes)
        
        self.results['sequential_real'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'results': results,
            'success_count': len([r for r in results if r['success']])
        }
        
        print(f"✅ Sequential execution completed in {total_time:.2f}s (avg: {avg_time:.2f}s per shoe)")
        return self.results['sequential_real']
    
    def test_parallel_real_api(self, max_workers: int = 3) -> Dict:
        """Test parallel execution with real APIs"""
        print(f"\n🚀 Testing Parallel Execution (Real APIs, max_workers={max_workers})")
        print("-" * 40)
        
        start_time = time.time()
        results = []
        
        def process_shoe(shoe: str) -> Dict:
            """Process a single shoe with real API calls"""
            print(f"Processing: {shoe[:30]}...")
            
            try:
                # Use the actual analyzer method
                result = self.analyzer.analyze_shoe_with_pricing_logic(shoe, self.test_size)
                return {
                    'shoe': shoe,
                    'result': result,
                    'success': 'error' not in result
                }
            except Exception as e:
                return {
                    'shoe': shoe,
                    'error': str(e),
                    'success': False
                }
        
        # Execute in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_shoe, shoe) for shoe in self.test_shoes]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({'error': str(e), 'success': False})
        
        total_time = time.time() - start_time
        avg_time = total_time / len(self.test_shoes)
        
        self.results['parallel_real'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'max_workers': max_workers,
            'results': results,
            'success_count': len([r for r in results if r['success']])
        }
        
        print(f"✅ Parallel execution completed in {total_time:.2f}s (avg: {avg_time:.2f}s per shoe)")
        return self.results['parallel_real']
    
    def test_rate_limit_handling(self) -> Dict:
        """Test rate limit handling with real APIs"""
        print("\n🔄 Testing Rate Limit Handling (Real APIs)")
        print("-" * 40)
        
        # Test rapid requests to see rate limiting behavior
        rapid_results = []
        start_time = time.time()
        
        for i in range(5):
            try:
                print(f"Rapid request {i+1}/5...")
                result = self.analyzer.analyze_shoe_with_pricing_logic(
                    self.test_shoes[0], self.test_size
                )
                rapid_results.append({
                    'request': i+1,
                    'result': result,
                    'success': 'error' not in result
                })
                
                # Small delay between requests
                time.sleep(1.0)
                
            except Exception as e:
                rapid_results.append({
                    'request': i+1,
                    'error': str(e),
                    'success': False
                })
        
        total_time = time.time() - start_time
        
        self.results['rate_limit_real'] = {
            'total_time': total_time,
            'results': rapid_results,
            'success_count': len([r for r in rapid_results if r['success']]),
            'success_rate': len([r for r in rapid_results if r['success']]) / len(rapid_results)
        }
        
        print(f"📊 Rate Limit Test Summary:")
        print(f"   Total Requests: {len(rapid_results)}")
        print(f"   Successful: {self.results['rate_limit_real']['success_count']}")
        print(f"   Success Rate: {self.results['rate_limit_real']['success_rate']:.1%}")
        
        return self.results['rate_limit_real']
    
    def test_progressive_loading_simulation(self) -> Dict:
        """Test progressive loading simulation with real APIs"""
        print("\n📊 Testing Progressive Loading Simulation (Real APIs)")
        print("-" * 40)
        
        def progress_callback(update: Dict):
            """Simulate progress callback"""
            print(f"   {update['step']}: {update['message']}")
        
        start_time = time.time()
        progress_updates = []
        
        # Simulate progressive loading with real API calls
        progress_updates.append({'step': '🔍', 'message': 'Searching StockX...'})
        
        try:
            # Get StockX data
            stockx_result = self.analyzer._get_stockx_data(self.test_shoes[0], self.test_size)
            if 'error' not in stockx_result:
                progress_updates.append({
                    'step': '✅', 
                    'message': f"StockX: ${stockx_result.get('bid', 'N/A')}/${stockx_result.get('ask', 'N/A')}"
                })
            else:
                progress_updates.append({'step': '❌', 'message': f"StockX: {stockx_result['error']}"})
        except Exception as e:
            progress_updates.append({'step': '❌', 'message': f"StockX: Error - {str(e)}"})
        
        progress_updates.append({'step': '🔍', 'message': 'Searching GOAT...'})
        
        try:
            # Get GOAT data
            goat_result = self.analyzer._get_alias_data(self.test_shoes[0], self.test_size)
            if 'error' not in goat_result:
                progress_updates.append({
                    'step': '✅', 
                    'message': f"GOAT: Data retrieved successfully"
                })
            else:
                progress_updates.append({'step': '❌', 'message': f"GOAT: {goat_result['error']}"})
        except Exception as e:
            progress_updates.append({'step': '❌', 'message': f"GOAT: Error - {str(e)}"})
        
        progress_updates.append({'step': '🧮', 'message': 'Final calculation...'})
        progress_updates.append({'step': '✅', 'message': 'Analysis complete'})
        
        total_time = time.time() - start_time
        
        self.results['progressive_loading_real'] = {
            'total_time': total_time,
            'progress_updates': progress_updates
        }
        
        print(f"✅ Progressive loading completed in {total_time:.2f}s")
        return self.results['progressive_loading_real']
    
    def generate_recommendations(self) -> Dict:
        """Generate optimization recommendations based on real API test results"""
        print("\n💡 Generating Optimization Recommendations")
        print("-" * 40)
        
        recommendations = {
            'parallel_execution': {},
            'rate_limiting': {},
            'progressive_loading': {},
            'implementation_priority': []
        }
        
        # Analyze parallel execution benefits
        if 'sequential_real' in self.results and 'parallel_real' in self.results:
            seq_time = self.results['sequential_real']['avg_time']
            parallel_time = self.results['parallel_real']['avg_time']
            
            improvement = ((seq_time - parallel_time) / seq_time) * 100
            recommendations['parallel_execution'] = {
                'current_sequential_time': seq_time,
                'parallel_time': parallel_time,
                'improvement_percentage': improvement,
                'recommendation': f'Implement threading for {improvement:.1f}% improvement'
            }
        
        # Rate limiting recommendations
        if 'rate_limit_real' in self.results:
            rate_data = self.results['rate_limit_real']
            recommendations['rate_limiting'] = {
                'safe_concurrent_requests': 3,
                'recommended_delay': '2 seconds between requests',
                'rate_limit_detection': 'Implement exponential backoff',
                'success_rate': rate_data['success_rate']
            }
        
        # Progressive loading recommendations
        if 'progressive_loading_real' in self.results:
            recommendations['progressive_loading'] = {
                'implementation': 'Add progress callback system',
                'user_experience': 'Dramatically improves perceived performance',
                'integration': 'Integrate with existing WebSocket system'
            }
        
        # Implementation priority
        recommendations['implementation_priority'] = [
            'Phase 1: Parallel Execution (HIGH PRIORITY)',
            'Phase 2: Progressive Loading (MEDIUM PRIORITY)',
            'Rate Limit Management (INTEGRATED)'
        ]
        
        return recommendations
    
    def run_all_tests(self) -> Dict:
        """Run all tests and generate comprehensive report"""
        print("🧪 Starting Real API Integration Test Suite")
        print("=" * 60)
        
        # Run all tests
        self.test_sequential_real_api()
        self.test_parallel_real_api(max_workers=3)
        self.test_rate_limit_handling()
        self.test_progressive_loading_simulation()
        
        # Generate recommendations
        recommendations = self.generate_recommendations()
        
        # Print summary
        print("\n📊 TEST SUMMARY")
        print("=" * 60)
        
        if 'sequential_real' in self.results and 'parallel_real' in self.results:
            seq_time = self.results['sequential_real']['total_time']
            parallel_time = self.results['parallel_real']['total_time']
            improvement = ((seq_time - parallel_time) / seq_time) * 100
            
            print(f"Sequential Execution: {seq_time:.2f}s")
            print(f"Parallel Execution: {parallel_time:.2f}s")
            print(f"Performance Improvement: {improvement:.1f}%")
        
        if 'rate_limit_real' in self.results:
            rate_data = self.results['rate_limit_real']
            print(f"Rate Limit Success Rate: {rate_data['success_rate']:.1%}")
        
        print(f"\n🎯 RECOMMENDATIONS:")
        for priority in recommendations['implementation_priority']:
            print(f"   • {priority}")
        
        return {
            'results': self.results,
            'recommendations': recommendations
        }

def main():
    """Main test execution"""
    tester = RealAPITester()
    results = tester.run_all_tests()
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"real_api_test_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Test results saved to: {filename}")
    print("\n✅ Real API test suite completed successfully!")

if __name__ == "__main__":
    main() 