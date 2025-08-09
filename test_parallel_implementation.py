#!/usr/bin/env python3
"""
🧪 Comprehensive Test Suite for Parallel Implementation
Testing parallel execution strategies and rate limit handling
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

class RateLimitHandler:
    """Rate limit handler with exponential backoff and circuit breaker pattern"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.request_count = 0
        self.rate_limit_hits = 0
        self.circuit_breaker_failures = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_timeout = 60
        self.last_failure_time = None
        
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open"""
        if self.circuit_breaker_failures >= self.circuit_breaker_threshold:
            if self.last_failure_time:
                time_since_failure = time.time() - self.last_failure_time
                if time_since_failure < self.circuit_breaker_timeout:
                    return True
                else:
                    # Reset circuit breaker
                    self.circuit_breaker_failures = 0
                    self.last_failure_time = None
        return False
    
    def api_call_with_retry(self, api_call: Callable, *args, **kwargs) -> Dict:
        """Execute API call with retry logic and rate limit handling"""
        if self._is_circuit_breaker_open():
            return {'error': 'Circuit breaker open - too many failures'}
        
        for attempt in range(self.max_retries):
            try:
                self.request_count += 1
                result = api_call(*args, **kwargs)
                
                # Reset circuit breaker on success
                if attempt > 0:
                    self.circuit_breaker_failures = 0
                    self.last_failure_time = None
                
                return result
                
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_str or "rate limit" in error_str.lower():
                    self.rate_limit_hits += 1
                    self.circuit_breaker_failures += 1
                    self.last_failure_time = time.time()
                    
                    if attempt < self.max_retries - 1:
                        wait_time = self.base_delay * (2 ** attempt)
                        print(f"⚠️ Rate limited! Waiting {wait_time}s and retrying (attempt {attempt + 1}/{self.max_retries})...")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Max retries reached for rate limiting")
                        return {'error': f'Rate limit exceeded after {self.max_retries} attempts'}
                else:
                    # Non-rate limit error
                    self.circuit_breaker_failures += 1
                    self.last_failure_time = time.time()
                    return {'error': error_str}
        
        return {'error': 'Max retries exceeded'}

class MockAPIClient:
    """Mock API client to simulate real API behavior"""
    
    def __init__(self):
        self.request_count = 0
        self.rate_limit_hits = 0
        self.stockx_rate_limit_threshold = 10
        self.goat_rate_limit_threshold = 8
        
    def mock_stockx_search(self, shoe_name: str, size: str) -> Dict:
        """Simulate StockX search API call"""
        self.request_count += 1
        
        # Simulate network latency (1-3 seconds)
        time.sleep(random.uniform(1.0, 3.0))
        
        # Simulate rate limiting
        if self.request_count % self.stockx_rate_limit_threshold == 0:
            self.rate_limit_hits += 1
            raise Exception("429 Rate limit exceeded - StockX API")
        
        return {
            'bid': random.randint(100, 300),
            'ask': random.randint(150, 400),
            'product_name': f"{shoe_name} (StockX)",
            'sku': f"STOCKX_{random.randint(1000, 9999)}",
            'success': True
        }
    
    def mock_goat_catalog_search(self, shoe_name: str, size: str) -> Dict:
        """Simulate GOAT catalog search API call"""
        self.request_count += 1
        
        # Simulate network latency (1-2 seconds)
        time.sleep(random.uniform(1.0, 2.0))
        
        # Simulate rate limiting
        if self.request_count % self.goat_rate_limit_threshold == 0:
            self.rate_limit_hits += 1
            raise Exception("429 Rate limit exceeded - GOAT API")
        
        return {
            'catalog_id': f"GOAT_{random.randint(1000, 9999)}",
            'name': f"{shoe_name} (GOAT)",
            'pricing': {
                'lowest_price': random.randint(120, 350),
                'highest_price': random.randint(200, 500)
            },
            'success': True
        }
    
    def mock_sales_data(self, catalog_id: str, size: float) -> Dict:
        """Simulate sales data API call"""
        self.request_count += 1
        
        # Simulate network latency (0.5-1.5 seconds)
        time.sleep(random.uniform(0.5, 1.5))
        
        return {
            'sales_per_week': random.randint(1, 20),
            'total_sales': random.randint(50, 500),
            'success': True
        }

class ParallelExecutionTester:
    """Test suite for parallel execution strategies"""
    
    def __init__(self):
        self.api_client = MockAPIClient()
        self.rate_limit_handler = RateLimitHandler()
        self.test_shoes = [
            "Nike Air Jordan 1 Retro High OG",
            "Adidas Yeezy Boost 350 V2",
            "Nike Air Force 1 Low",
            "Converse Chuck Taylor All Star",
            "Vans Old Skool"
        ]
        self.test_size = "10"
        self.results = {}
        
    def test_sequential_execution(self) -> Dict:
        """Test sequential execution performance"""
        print("\n🔍 Testing Sequential Execution")
        print("-" * 40)
        
        start_time = time.time()
        results = []
        
        for i, shoe in enumerate(self.test_shoes, 1):
            print(f"Processing {i}/{len(self.test_shoes)}: {shoe[:30]}...")
            
            # Simulate sequential API calls
            stockx_data = self.rate_limit_handler.api_call_with_retry(
                self.api_client.mock_stockx_search, shoe, self.test_size
            )
            
            goat_data = self.rate_limit_handler.api_call_with_retry(
                self.api_client.mock_goat_catalog_search, shoe, self.test_size
            )
            
            if goat_data.get('success'):
                sales_data = self.rate_limit_handler.api_call_with_retry(
                    self.api_client.mock_sales_data, goat_data['catalog_id'], float(self.test_size)
                )
            else:
                sales_data = {'error': 'No catalog match'}
            
            results.append({
                'shoe': shoe,
                'stockx_data': stockx_data,
                'goat_data': goat_data,
                'sales_data': sales_data
            })
        
        total_time = time.time() - start_time
        avg_time = total_time / len(self.test_shoes)
        
        self.results['sequential'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'results': results,
            'request_count': self.api_client.request_count,
            'rate_limit_hits': self.api_client.rate_limit_hits
        }
        
        print(f"✅ Sequential execution completed in {total_time:.2f}s (avg: {avg_time:.2f}s per shoe)")
        return self.results['sequential']
    
    def test_parallel_execution(self, max_workers: int = 3) -> Dict:
        """Test parallel execution performance"""
        print(f"\n🚀 Testing Parallel Execution (max_workers={max_workers})")
        print("-" * 40)
        
        start_time = time.time()
        results = []
        
        def process_shoe(shoe: str) -> Dict:
            """Process a single shoe with all API calls"""
            print(f"Processing: {shoe[:30]}...")
            
            # Simulate parallel API calls
            stockx_data = self.rate_limit_handler.api_call_with_retry(
                self.api_client.mock_stockx_search, shoe, self.test_size
            )
            
            goat_data = self.rate_limit_handler.api_call_with_retry(
                self.api_client.mock_goat_catalog_search, shoe, self.test_size
            )
            
            if goat_data.get('success'):
                sales_data = self.rate_limit_handler.api_call_with_retry(
                    self.api_client.mock_sales_data, goat_data['catalog_id'], float(self.test_size)
                )
            else:
                sales_data = {'error': 'No catalog match'}
            
            return {
                'shoe': shoe,
                'stockx_data': stockx_data,
                'goat_data': goat_data,
                'sales_data': sales_data
            }
        
        # Execute in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_shoe, shoe) for shoe in self.test_shoes]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({'error': str(e)})
        
        total_time = time.time() - start_time
        avg_time = total_time / len(self.test_shoes)
        
        self.results['parallel'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'max_workers': max_workers,
            'results': results,
            'request_count': self.api_client.request_count,
            'rate_limit_hits': self.api_client.rate_limit_hits
        }
        
        print(f"✅ Parallel execution completed in {total_time:.2f}s (avg: {avg_time:.2f}s per shoe)")
        return self.results['parallel']
    
    def test_rate_limit_behavior(self) -> Dict:
        """Test rate limit behavior and handling"""
        print("\n🔄 Testing Rate Limit Behavior")
        print("-" * 40)
        
        # Reset counters
        self.api_client.request_count = 0
        self.api_client.rate_limit_hits = 0
        
        rapid_results = []
        for i in range(15):
            try:
                result = self.rate_limit_handler.api_call_with_retry(
                    self.api_client.mock_stockx_search, 
                    f"Test Shoe {i+1}", 
                    self.test_size
                )
                rapid_results.append(result)
                time.sleep(0.1)  # Small delay
            except Exception as e:
                rapid_results.append({'error': str(e)})
        
        self.results['rate_limits'] = {
            'total_requests': self.api_client.request_count,
            'rate_limit_hits': self.api_client.rate_limit_hits,
            'success_rate': len([r for r in rapid_results if 'error' not in r]) / len(rapid_results),
            'results': rapid_results
        }
        
        print(f"📊 Rate Limit Summary:")
        print(f"   Total Requests: {self.api_client.request_count}")
        print(f"   Rate Limit Hits: {self.api_client.rate_limit_hits}")
        print(f"   Success Rate: {self.results['rate_limits']['success_rate']:.1%}")
        
        return self.results['rate_limits']
    
    def test_progressive_loading(self) -> Dict:
        """Test progressive loading simulation"""
        print("\n📊 Testing Progressive Loading Simulation")
        print("-" * 40)
        
        def progress_callback(update: Dict):
            """Simulate progress callback"""
            print(f"   {update['step']}: {update['message']}")
        
        start_time = time.time()
        progress_updates = []
        
        # Simulate progressive loading
        progress_updates.append({'step': '🔍', 'message': 'Searching StockX...'})
        stockx_data = self.rate_limit_handler.api_call_with_retry(
            self.api_client.mock_stockx_search, self.test_shoes[0], self.test_size
        )
        progress_updates.append({'step': '✅', 'message': f'StockX: ${stockx_data.get('bid', 'N/A')}/${stockx_data.get('ask', 'N/A')}'})
        
        progress_updates.append({'step': '🔍', 'message': 'Searching GOAT...'})
        goat_data = self.rate_limit_handler.api_call_with_retry(
            self.api_client.mock_goat_catalog_search, self.test_shoes[0], self.test_size
        )
        progress_updates.append({'step': '✅', 'message': f'GOAT: ${goat_data.get('pricing', {}).get('lowest_price', 'N/A')} lowest'})
        
        progress_updates.append({'step': '📊', 'message': 'Calculating sales...'})
        if goat_data.get('success'):
            sales_data = self.rate_limit_handler.api_call_with_retry(
                self.api_client.mock_sales_data, goat_data['catalog_id'], float(self.test_size)
            )
            progress_updates.append({'step': '✅', 'message': f'{sales_data.get('sales_per_week', 0)} sales last week'})
        
        progress_updates.append({'step': '🧮', 'message': 'Final calculation...'})
        progress_updates.append({'step': '✅', 'message': 'BUY AT $143.70'})
        
        total_time = time.time() - start_time
        
        self.results['progressive_loading'] = {
            'total_time': total_time,
            'progress_updates': progress_updates,
            'final_result': {
                'stockx_data': stockx_data,
                'goat_data': goat_data,
                'recommendation': 'BUY AT $143.70'
            }
        }
        
        print(f"✅ Progressive loading completed in {total_time:.2f}s")
        return self.results['progressive_loading']
    
    def generate_recommendations(self) -> Dict:
        """Generate optimization recommendations based on test results"""
        print("\n💡 Generating Optimization Recommendations")
        print("-" * 40)
        
        recommendations = {
            'parallel_execution': {},
            'rate_limiting': {},
            'progressive_loading': {},
            'implementation_priority': []
        }
        
        # Analyze parallel execution benefits
        if 'sequential' in self.results and 'parallel' in self.results:
            seq_time = self.results['sequential']['avg_time']
            parallel_time = self.results['parallel']['avg_time']
            
            improvement = ((seq_time - parallel_time) / seq_time) * 100
            recommendations['parallel_execution'] = {
                'current_sequential_time': seq_time,
                'parallel_time': parallel_time,
                'improvement_percentage': improvement,
                'recommendation': f'Implement threading for {improvement:.1f}% improvement'
            }
        
        # Rate limiting recommendations
        if 'rate_limits' in self.results:
            rate_data = self.results['rate_limits']
            recommendations['rate_limiting'] = {
                'safe_concurrent_requests': 3,
                'recommended_delay': '2 seconds between requests',
                'rate_limit_detection': 'Implement exponential backoff',
                'success_rate': rate_data['success_rate']
            }
        
        # Progressive loading recommendations
        if 'progressive_loading' in self.results:
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
        print("🧪 Starting Comprehensive Test Suite")
        print("=" * 60)
        
        # Run all tests
        self.test_sequential_execution()
        self.test_parallel_execution(max_workers=3)
        self.test_rate_limit_behavior()
        self.test_progressive_loading()
        
        # Generate recommendations
        recommendations = self.generate_recommendations()
        
        # Print summary
        print("\n📊 TEST SUMMARY")
        print("=" * 60)
        
        if 'sequential' in self.results and 'parallel' in self.results:
            seq_time = self.results['sequential']['total_time']
            parallel_time = self.results['parallel']['total_time']
            improvement = ((seq_time - parallel_time) / seq_time) * 100
            
            print(f"Sequential Execution: {seq_time:.2f}s")
            print(f"Parallel Execution: {parallel_time:.2f}s")
            print(f"Performance Improvement: {improvement:.1f}%")
        
        if 'rate_limits' in self.results:
            rate_data = self.results['rate_limits']
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
    tester = ParallelExecutionTester()
    results = tester.run_all_tests()
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Test results saved to: {filename}")
    print("\n✅ Test suite completed successfully!")

if __name__ == "__main__":
    main() 