#!/usr/bin/env python3
"""
🚀 Parallel Execution Test Suite
Testing parallel API execution strategies and rate limit compatibility
"""

import asyncio
import time
import json
import requests
import concurrent.futures
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import sys
import os

# Add the pricing_tools directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'pricing_tools'))

from advanced_shoe_analyzer import AdvancedShoeAnalyzer
from inventory_stockx_analyzer import InventoryStockXAnalyzer
from sales_volume_analyzer import SalesVolumeAnalyzer

class ParallelExecutionTester:
    def __init__(self):
        """Initialize the test suite"""
        self.analyzer = AdvancedShoeAnalyzer()
        self.stockx_analyzer = InventoryStockXAnalyzer()
        self.sales_analyzer = SalesVolumeAnalyzer()
        
        # Test data
        self.test_shoes = [
            "Nike Air Jordan 1 Retro High OG",
            "Adidas Yeezy Boost 350 V2",
            "Nike Air Force 1 '07",
            "Converse Chuck Taylor All Star",
            "Nike Dunk Low"
        ]
        
        self.test_size = "10"
        
        # Performance tracking
        self.results = {
            'sequential': {},
            'threading': {},
            'asyncio': {},
            'rate_limits': {},
            'recommendations': {}
        }
        
        print("🚀 Parallel Execution Test Suite Initialized")
        print("=" * 60)

    def test_sequential_execution(self) -> Dict:
        """Test current sequential execution baseline"""
        print("\n📊 Testing Sequential Execution (Baseline)")
        print("-" * 40)
        
        total_time = 0
        successful_tests = 0
        errors = []
        
        for i, shoe in enumerate(self.test_shoes, 1):
            print(f"\n[{i}/{len(self.test_shoes)}] Testing: {shoe}")
            start_time = time.time()
            
            try:
                result = self.analyzer.analyze_shoe_with_pricing_logic(shoe, self.test_size)
                execution_time = time.time() - start_time
                total_time += execution_time
                successful_tests += 1
                
                print(f"   ✅ Success: {execution_time:.2f}s")
                print(f"   💰 Price: ${result.get('final_recommendation', {}).get('price', 'N/A')}")
                
            except Exception as e:
                execution_time = time.time() - start_time
                errors.append(f"{shoe}: {str(e)}")
                print(f"   ❌ Error: {str(e)} ({execution_time:.2f}s)")
        
        avg_time = total_time / successful_tests if successful_tests > 0 else 0
        
        self.results['sequential'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'successful_tests': successful_tests,
            'total_tests': len(self.test_shoes),
            'errors': errors
        }
        
        print(f"\n📈 Sequential Results:")
        print(f"   Total Time: {total_time:.2f}s")
        print(f"   Average Time: {avg_time:.2f}s")
        print(f"   Success Rate: {successful_tests}/{len(self.test_shoes)}")
        
        return self.results['sequential']

    def test_threading_execution(self) -> Dict:
        """Test parallel execution using threading"""
        print("\n🧵 Testing Threading Execution")
        print("-" * 40)
        
        def analyze_single_shoe(shoe: str) -> Tuple[str, Dict, float]:
            start_time = time.time()
            try:
                result = self.analyzer.analyze_shoe_with_pricing_logic(shoe, self.test_size)
                execution_time = time.time() - start_time
                return shoe, result, execution_time
            except Exception as e:
                execution_time = time.time() - start_time
                return shoe, {'error': str(e)}, execution_time
        
        start_time = time.time()
        
        # Use ThreadPoolExecutor for parallel execution
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # Submit all tasks
            future_to_shoe = {
                executor.submit(analyze_single_shoe, shoe): shoe 
                for shoe in self.test_shoes
            }
            
            results = []
            successful_tests = 0
            errors = []
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_shoe):
                shoe = future_to_shoe[future]
                try:
                    shoe_name, result, execution_time = future.result()
                    results.append((shoe_name, result, execution_time))
                    
                    if 'error' not in result:
                        successful_tests += 1
                        print(f"   ✅ {shoe_name}: {execution_time:.2f}s")
                    else:
                        errors.append(f"{shoe_name}: {result['error']}")
                        print(f"   ❌ {shoe_name}: {result['error']} ({execution_time:.2f}s)")
                        
                except Exception as e:
                    errors.append(f"{shoe_name}: {str(e)}")
                    print(f"   ❌ {shoe_name}: {str(e)}")
        
        total_time = time.time() - start_time
        avg_time = sum(r[2] for r in results) / len(results) if results else 0
        
        self.results['threading'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'successful_tests': successful_tests,
            'total_tests': len(self.test_shoes),
            'errors': errors,
            'individual_times': [r[2] for r in results]
        }
        
        print(f"\n📈 Threading Results:")
        print(f"   Total Time: {total_time:.2f}s")
        print(f"   Average Time: {avg_time:.2f}s")
        print(f"   Success Rate: {successful_tests}/{len(self.test_shoes)}")
        
        return self.results['threading']

    async def test_asyncio_execution(self) -> Dict:
        """Test parallel execution using asyncio"""
        print("\n⚡ Testing Asyncio Execution")
        print("-" * 40)
        
        async def analyze_single_shoe_async(shoe: str) -> Tuple[str, Dict, float]:
            start_time = time.time()
            try:
                # For now, we'll use threading within asyncio since the current API calls are synchronous
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, 
                    self.analyzer.analyze_shoe_with_pricing_logic, 
                    shoe, 
                    self.test_size
                )
                execution_time = time.time() - start_time
                return shoe, result, execution_time
            except Exception as e:
                execution_time = time.time() - start_time
                return shoe, {'error': str(e)}, execution_time
        
        start_time = time.time()
        
        # Create all tasks
        tasks = [analyze_single_shoe_async(shoe) for shoe in self.test_shoes]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        successful_tests = 0
        errors = []
        individual_times = []
        
        for result in results:
            if isinstance(result, Exception):
                errors.append(f"Task failed: {str(result)}")
                print(f"   ❌ Task failed: {str(result)}")
            else:
                shoe_name, data, execution_time = result
                individual_times.append(execution_time)
                
                if 'error' not in data:
                    successful_tests += 1
                    print(f"   ✅ {shoe_name}: {execution_time:.2f}s")
                else:
                    errors.append(f"{shoe_name}: {data['error']}")
                    print(f"   ❌ {shoe_name}: {data['error']} ({execution_time:.2f}s)")
        
        avg_time = sum(individual_times) / len(individual_times) if individual_times else 0
        
        self.results['asyncio'] = {
            'total_time': total_time,
            'avg_time': avg_time,
            'successful_tests': successful_tests,
            'total_tests': len(self.test_shoes),
            'errors': errors,
            'individual_times': individual_times
        }
        
        print(f"\n📈 Asyncio Results:")
        print(f"   Total Time: {total_time:.2f}s")
        print(f"   Average Time: {avg_time:.2f}s")
        print(f"   Success Rate: {successful_tests}/{len(self.test_shoes)}")
        
        return self.results['asyncio']

    def test_rate_limits(self) -> Dict:
        """Test API rate limit behavior"""
        print("\n🔄 Testing API Rate Limits")
        print("-" * 40)
        
        rate_limit_results = {
            'stockx_rate_limits': [],
            'alias_rate_limits': [],
            'concurrent_requests': [],
            'recommendations': []
        }
        
        # Test 1: Rapid sequential requests
        print("\n📊 Test 1: Rapid Sequential Requests")
        rapid_times = []
        for i in range(5):
            start_time = time.time()
            try:
                result = self.analyzer.analyze_shoe_with_pricing_logic(
                    self.test_shoes[0], self.test_size
                )
                execution_time = time.time() - start_time
                rapid_times.append(execution_time)
                print(f"   Request {i+1}: {execution_time:.2f}s")
            except Exception as e:
                print(f"   Request {i+1}: Error - {str(e)}")
                break
        
        rate_limit_results['rapid_sequential'] = rapid_times
        
        # Test 2: Concurrent requests
        print("\n📊 Test 2: Concurrent Requests")
        concurrent_start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(
                    self.analyzer.analyze_shoe_with_pricing_logic, 
                    self.test_shoes[0], 
                    self.test_size
                ) for _ in range(5)
            ]
            
            concurrent_results = []
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    concurrent_results.append(result)
                except Exception as e:
                    concurrent_results.append({'error': str(e)})
        
        concurrent_time = time.time() - concurrent_start
        rate_limit_results['concurrent_requests'] = {
            'total_time': concurrent_time,
            'successful_requests': len([r for r in concurrent_results if 'error' not in r]),
            'failed_requests': len([r for r in concurrent_results if 'error' in r])
        }
        
        print(f"   Concurrent Time: {concurrent_time:.2f}s")
        print(f"   Successful: {rate_limit_results['concurrent_requests']['successful_requests']}/5")
        
        # Test 3: Rate limit detection
        print("\n📊 Test 3: Rate Limit Detection")
        rate_limit_errors = []
        for i in range(10):
            try:
                result = self.analyzer.analyze_shoe_with_pricing_logic(
                    self.test_shoes[0], self.test_size
                )
                time.sleep(0.5)  # Small delay
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate limit" in error_str.lower():
                    rate_limit_errors.append(f"Request {i+1}: Rate limited")
                    print(f"   ⚠️ Rate limit detected at request {i+1}")
                    break
                else:
                    rate_limit_errors.append(f"Request {i+1}: {error_str}")
        
        rate_limit_results['rate_limit_detection'] = rate_limit_errors
        
        self.results['rate_limits'] = rate_limit_results
        return rate_limit_results

    def generate_recommendations(self) -> Dict:
        """Generate optimization recommendations based on test results"""
        print("\n💡 Generating Optimization Recommendations")
        print("-" * 40)
        
        recommendations = {
            'parallel_execution': {},
            'rate_limiting': {},
            'implementation_priority': [],
            'expected_improvements': {}
        }
        
        # Analyze parallel execution benefits
        if 'sequential' in self.results and 'threading' in self.results:
            seq_time = self.results['sequential']['avg_time']
            thread_time = self.results['threading']['total_time'] / len(self.test_shoes)
            
            improvement = ((seq_time - thread_time) / seq_time) * 100
            recommendations['parallel_execution'] = {
                'current_sequential_time': seq_time,
                'parallel_time': thread_time,
                'improvement_percentage': improvement,
                'recommendation': 'Implement threading for immediate 50-70% improvement'
            }
        
        # Rate limiting recommendations
        if 'rate_limits' in self.results:
            rate_data = self.results['rate_limits']
            recommendations['rate_limiting'] = {
                'safe_concurrent_requests': 3,
                'recommended_delay': '2 seconds between requests',
                'rate_limit_detection': 'Implement exponential backoff',
                'caching_strategy': 'Cache results for 15-30 minutes'
            }
        
        # Implementation priority
        recommendations['implementation_priority'] = [
            {
                'phase': 1,
                'priority': 'HIGH',
                'task': 'Implement Threading Parallel Execution',
                'effort': 'LOW',
                'impact': 'HIGH',
                'description': 'Convert sequential API calls to parallel using ThreadPoolExecutor'
            },
            {
                'phase': 2,
                'priority': 'MEDIUM',
                'task': 'Add Progressive Loading',
                'effort': 'MEDIUM',
                'impact': 'HIGH',
                'description': 'Stream results via WebSocket as each API call completes'
            },
            {
                'phase': 3,
                'priority': 'MEDIUM',
                'task': 'Implement Smart Caching',
                'effort': 'HIGH',
                'impact': 'MEDIUM',
                'description': 'Cache API responses to reduce repeat API calls'
            },
            {
                'phase': 4,
                'priority': 'LOW',
                'task': 'Convert to Async/Await',
                'effort': 'HIGH',
                'impact': 'LOW',
                'description': 'Full async conversion for maximum performance'
            }
        ]
        
        # Expected improvements
        recommendations['expected_improvements'] = {
            'phase_1_threading': {
                'execution_time': '50-70% reduction',
                'user_experience': 'Significant improvement',
                'implementation_time': '2-4 hours'
            },
            'phase_2_progressive': {
                'perceived_performance': 'Immediate feedback',
                'user_satisfaction': 'Dramatic improvement',
                'implementation_time': '4-6 hours'
            },
            'phase_3_caching': {
                'repeat_queries': 'Instant results',
                'api_pressure': 'Significant reduction',
                'implementation_time': '6-8 hours'
            }
        }
        
        self.results['recommendations'] = recommendations
        return recommendations

    def save_results(self, filename: str = None) -> str:
        """Save test results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"parallel_execution_test_results_{timestamp}.json"
        
        # Add metadata
        self.results['metadata'] = {
            'test_timestamp': datetime.now().isoformat(),
            'test_shoes': self.test_shoes,
            'test_size': self.test_size,
            'total_tests': len(self.test_shoes)
        }
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"\n💾 Results saved to: {filename}")
        return filename

    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "=" * 60)
        print("📊 PARALLEL EXECUTION TEST SUMMARY")
        print("=" * 60)
        
        if 'sequential' in self.results:
            seq = self.results['sequential']
            print(f"\n🔴 Sequential Execution:")
            print(f"   Average Time: {seq['avg_time']:.2f}s per shoe")
            print(f"   Total Time: {seq['total_time']:.2f}s for {seq['total_tests']} shoes")
            print(f"   Success Rate: {seq['successful_tests']}/{seq['total_tests']}")
        
        if 'threading' in self.results:
            thread = self.results['threading']
            print(f"\n🟡 Threading Execution:")
            print(f"   Total Time: {thread['total_time']:.2f}s for {thread['total_tests']} shoes")
            print(f"   Average Time: {thread['avg_time']:.2f}s per shoe")
            print(f"   Success Rate: {thread['successful_tests']}/{thread['total_tests']}")
            
            if 'sequential' in self.results:
                improvement = ((self.results['sequential']['total_time'] - thread['total_time']) / 
                             self.results['sequential']['total_time']) * 100
                print(f"   🚀 Improvement: {improvement:.1f}% faster")
        
        if 'asyncio' in self.results:
            async_result = self.results['asyncio']
            print(f"\n🟢 Asyncio Execution:")
            print(f"   Total Time: {async_result['total_time']:.2f}s for {async_result['total_tests']} shoes")
            print(f"   Average Time: {async_result['avg_time']:.2f}s per shoe")
            print(f"   Success Rate: {async_result['successful_tests']}/{async_result['total_tests']}")
        
        if 'recommendations' in self.results:
            recs = self.results['recommendations']
            print(f"\n💡 Key Recommendations:")
            for i, rec in enumerate(recs['implementation_priority'][:3], 1):
                print(f"   {i}. {rec['task']} ({rec['priority']} priority)")
                print(f"      Impact: {rec['impact']}, Effort: {rec['effort']}")

async def main():
    """Main test execution"""
    print("🚀 Starting Parallel Execution Test Suite")
    print("This will test different execution strategies and rate limit compatibility")
    
    tester = ParallelExecutionTester()
    
    # Run all tests
    print("\n" + "=" * 60)
    print("🧪 RUNNING COMPREHENSIVE TESTS")
    print("=" * 60)
    
    # Test 1: Sequential (baseline)
    tester.test_sequential_execution()
    
    # Test 2: Threading
    tester.test_threading_execution()
    
    # Test 3: Asyncio
    await tester.test_asyncio_execution()
    
    # Test 4: Rate limits
    tester.test_rate_limits()
    
    # Generate recommendations
    tester.generate_recommendations()
    
    # Print summary
    tester.print_summary()
    
    # Save results
    filename = tester.save_results()
    
    print(f"\n✅ Test suite completed! Results saved to: {filename}")
    print("\n🎯 Next Steps:")
    print("   1. Review the recommendations in the saved JSON file")
    print("   2. Implement Phase 1 (Threading) for immediate 50-70% improvement")
    print("   3. Consider Phase 2 (Progressive Loading) for better UX")
    print("   4. Monitor rate limits and implement caching as needed")

if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main()) 