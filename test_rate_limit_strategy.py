#!/usr/bin/env python3
"""
🔄 Rate Limit Strategy Test
Testing rate limit handling strategies before implementation
"""

import time
import json
import concurrent.futures
import threading
import random
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
import sys
import os

class RateLimitStrategyTester:
    """Test suite for rate limit handling strategies"""
    
    def __init__(self):
        self.request_count = 0
        self.rate_limit_hits = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
    def simulate_api_call(self, api_name: str, delay: float = 1.0) -> Dict:
        """Simulate an API call with potential rate limiting"""
        self.request_count += 1
        
        # Simulate network latency
        time.sleep(delay)
        
        # Simulate rate limiting (every 8-12 requests)
        rate_limit_threshold = random.randint(8, 12)
        if self.request_count % rate_limit_threshold == 0:
            self.rate_limit_hits += 1
            raise Exception(f"429 Rate limit exceeded - {api_name}")
        
        self.successful_requests += 1
        return {
            'success': True,
            'data': f'Mock data from {api_name}',
            'request_id': self.request_count
        }
    
    def test_exponential_backoff(self) -> Dict:
        """Test exponential backoff strategy"""
        print("\n🔄 Testing Exponential Backoff Strategy")
        print("-" * 40)
        
        def api_call_with_exponential_backoff(api_name: str, max_retries: int = 3) -> Dict:
            """Execute API call with exponential backoff"""
            base_delay = 2.0
            
            for attempt in range(max_retries):
                try:
                    return self.simulate_api_call(api_name, delay=1.0)
                except Exception as e:
                    if "429" in str(e) and attempt < max_retries - 1:
                        wait_time = base_delay * (2 ** attempt)
                        print(f"   ⚠️ Rate limited! Waiting {wait_time}s and retrying (attempt {attempt + 1}/{max_retries})...")
                        time.sleep(wait_time)
                    else:
                        self.failed_requests += 1
                        return {'error': str(e)}
            
            return {'error': 'Max retries exceeded'}
        
        start_time = time.time()
        results = []
        
        # Test multiple API calls
        for i in range(15):
            result = api_call_with_exponential_backoff(f"API_{i+1}")
            results.append(result)
        
        total_time = time.time() - start_time
        
        success_rate = len([r for r in results if 'error' not in r]) / len(results)
        
        test_results = {
            'strategy': 'exponential_backoff',
            'total_time': total_time,
            'total_requests': self.request_count,
            'rate_limit_hits': self.rate_limit_hits,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': success_rate,
            'results': results
        }
        
        print(f"✅ Exponential backoff completed in {total_time:.2f}s")
        print(f"   Success Rate: {success_rate:.1%}")
        print(f"   Rate Limit Hits: {self.rate_limit_hits}")
        
        return test_results
    
    def test_circuit_breaker(self) -> Dict:
        """Test circuit breaker pattern"""
        print("\n🔌 Testing Circuit Breaker Pattern")
        print("-" * 40)
        
        class CircuitBreaker:
            def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
                self.failure_threshold = failure_threshold
                self.recovery_timeout = recovery_timeout
                self.failure_count = 0
                self.last_failure_time = None
                self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
            
            def call(self, api_call: Callable, *args, **kwargs) -> Dict:
                """Execute API call with circuit breaker protection"""
                if self.state == 'OPEN':
                    if time.time() - self.last_failure_time > self.recovery_timeout:
                        self.state = 'HALF_OPEN'
                        print("   🔄 Circuit breaker transitioning to HALF_OPEN")
                    else:
                        return {'error': 'Circuit breaker is OPEN'}
                
                try:
                    result = api_call(*args, **kwargs)
                    if self.state == 'HALF_OPEN':
                        self.state = 'CLOSED'
                        self.failure_count = 0
                        print("   ✅ Circuit breaker reset to CLOSED")
                    return result
                except Exception as e:
                    self.failure_count += 1
                    self.last_failure_time = time.time()
                    
                    if self.failure_count >= self.failure_threshold:
                        self.state = 'OPEN'
                        print(f"   🔌 Circuit breaker opened after {self.failure_count} failures")
                    
                    return {'error': str(e)}
        
        circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10)
        
        start_time = time.time()
        results = []
        
        # Test multiple API calls with circuit breaker
        for i in range(20):
            result = circuit_breaker.call(self.simulate_api_call, f"API_{i+1}")
            results.append(result)
            
            # Small delay between requests
            time.sleep(0.5)
        
        total_time = time.time() - start_time
        
        success_rate = len([r for r in results if 'error' not in r]) / len(results)
        
        test_results = {
            'strategy': 'circuit_breaker',
            'total_time': total_time,
            'total_requests': self.request_count,
            'rate_limit_hits': self.rate_limit_hits,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': success_rate,
            'results': results
        }
        
        print(f"✅ Circuit breaker completed in {total_time:.2f}s")
        print(f"   Success Rate: {success_rate:.1%}")
        print(f"   Rate Limit Hits: {self.rate_limit_hits}")
        
        return test_results
    
    def test_conservative_threading(self) -> Dict:
        """Test conservative threading strategy"""
        print("\n🧵 Testing Conservative Threading Strategy")
        print("-" * 40)
        
        def api_call_with_delay(api_name: str) -> Dict:
            """Execute API call with built-in delay"""
            try:
                result = self.simulate_api_call(api_name, delay=1.0)
                time.sleep(2.0)  # Conservative delay between requests
                return result
            except Exception as e:
                self.failed_requests += 1
                return {'error': str(e)}
        
        start_time = time.time()
        results = []
        
        # Test parallel execution with conservative threading
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(api_call_with_delay, f"API_{i+1}") 
                for i in range(10)
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({'error': str(e)})
        
        total_time = time.time() - start_time
        
        success_rate = len([r for r in results if 'error' not in r]) / len(results)
        
        test_results = {
            'strategy': 'conservative_threading',
            'total_time': total_time,
            'total_requests': self.request_count,
            'rate_limit_hits': self.rate_limit_hits,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': success_rate,
            'results': results
        }
        
        print(f"✅ Conservative threading completed in {total_time:.2f}s")
        print(f"   Success Rate: {success_rate:.1%}")
        print(f"   Rate Limit Hits: {self.rate_limit_hits}")
        
        return test_results
    
    def test_combined_strategy(self) -> Dict:
        """Test combined strategy (exponential backoff + circuit breaker + conservative threading)"""
        print("\n🎯 Testing Combined Strategy")
        print("-" * 40)
        
        class CombinedRateLimitHandler:
            def __init__(self, max_retries: int = 3, failure_threshold: int = 5):
                self.max_retries = max_retries
                self.failure_threshold = failure_threshold
                self.failure_count = 0
                self.last_failure_time = None
                self.state = 'CLOSED'
            
            def call(self, api_call: Callable, *args, **kwargs) -> Dict:
                """Execute API call with combined protection"""
                if self.state == 'OPEN':
                    if time.time() - self.last_failure_time > 60:
                        self.state = 'CLOSED'
                        self.failure_count = 0
                    else:
                        return {'error': 'Circuit breaker is OPEN'}
                
                for attempt in range(self.max_retries):
                    try:
                        result = api_call(*args, **kwargs)
                        if attempt > 0:
                            self.failure_count = 0
                        return result
                    except Exception as e:
                        if "429" in str(e) and attempt < self.max_retries - 1:
                            wait_time = 2.0 * (2 ** attempt)
                            print(f"   ⚠️ Rate limited! Waiting {wait_time}s and retrying (attempt {attempt + 1}/{self.max_retries})...")
                            time.sleep(wait_time)
                        
                        self.failure_count += 1
                        self.last_failure_time = time.time()
                        
                        if self.failure_count >= self.failure_threshold:
                            self.state = 'OPEN'
                            print(f"   🔌 Circuit breaker opened after {self.failure_count} failures")
                        
                        if attempt == self.max_retries - 1:
                            return {'error': str(e)}
                
                return {'error': 'Max retries exceeded'}
        
        handler = CombinedRateLimitHandler()
        
        start_time = time.time()
        results = []
        
        # Test combined strategy
        for i in range(12):
            result = handler.call(self.simulate_api_call, f"API_{i+1}")
            results.append(result)
            time.sleep(1.0)  # Conservative delay
        
        total_time = time.time() - start_time
        
        success_rate = len([r for r in results if 'error' not in r]) / len(results)
        
        test_results = {
            'strategy': 'combined',
            'total_time': total_time,
            'total_requests': self.request_count,
            'rate_limit_hits': self.rate_limit_hits,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': success_rate,
            'results': results
        }
        
        print(f"✅ Combined strategy completed in {total_time:.2f}s")
        print(f"   Success Rate: {success_rate:.1%}")
        print(f"   Rate Limit Hits: {self.rate_limit_hits}")
        
        return test_results
    
    def run_all_tests(self) -> Dict:
        """Run all rate limit strategy tests"""
        print("🔄 Starting Rate Limit Strategy Test Suite")
        print("=" * 60)
        
        results = {}
        
        # Reset counters
        self.request_count = 0
        self.rate_limit_hits = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        # Run tests
        results['exponential_backoff'] = self.test_exponential_backoff()
        
        # Reset counters
        self.request_count = 0
        self.rate_limit_hits = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        results['circuit_breaker'] = self.test_circuit_breaker()
        
        # Reset counters
        self.request_count = 0
        self.rate_limit_hits = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        results['conservative_threading'] = self.test_conservative_threading()
        
        # Reset counters
        self.request_count = 0
        self.rate_limit_hits = 0
        self.successful_requests = 0
        self.failed_requests = 0
        
        results['combined'] = self.test_combined_strategy()
        
        # Generate recommendations
        recommendations = self.generate_recommendations(results)
        
        # Print summary
        self.print_summary(results, recommendations)
        
        return {
            'results': results,
            'recommendations': recommendations
        }
    
    def generate_recommendations(self, results: Dict) -> Dict:
        """Generate recommendations based on test results"""
        recommendations = {
            'best_strategy': None,
            'implementation_notes': [],
            'rate_limit_handling': {}
        }
        
        # Find best strategy based on success rate and performance
        best_strategy = None
        best_score = 0
        
        for strategy_name, strategy_results in results.items():
            success_rate = strategy_results['success_rate']
            total_time = strategy_results['total_time']
            
            # Score based on success rate and efficiency
            score = success_rate * (1.0 / total_time) * 1000
            
            if score > best_score:
                best_score = score
                best_strategy = strategy_name
        
        recommendations['best_strategy'] = best_strategy
        
        # Implementation notes
        recommendations['implementation_notes'] = [
            'Use exponential backoff for retry logic',
            'Implement circuit breaker for failure protection',
            'Use conservative threading (max_workers=3)',
            'Add 2-second delays between requests',
            'Monitor rate limit responses (429 status codes)'
        ]
        
        # Rate limit handling recommendations
        recommendations['rate_limit_handling'] = {
            'retry_strategy': 'exponential_backoff',
            'max_retries': 3,
            'base_delay': 2.0,
            'circuit_breaker_threshold': 5,
            'conservative_threading': True,
            'max_workers': 3
        }
        
        return recommendations
    
    def print_summary(self, results: Dict, recommendations: Dict):
        """Print test summary"""
        print("\n📊 RATE LIMIT STRATEGY SUMMARY")
        print("=" * 60)
        
        for strategy_name, strategy_results in results.items():
            print(f"{strategy_name.upper()}:")
            print(f"  Success Rate: {strategy_results['success_rate']:.1%}")
            print(f"  Total Time: {strategy_results['total_time']:.2f}s")
            print(f"  Rate Limit Hits: {strategy_results['rate_limit_hits']}")
            print()
        
        print(f"🎯 RECOMMENDED STRATEGY: {recommendations['best_strategy'].upper()}")
        print(f"\n💡 IMPLEMENTATION NOTES:")
        for note in recommendations['implementation_notes']:
            print(f"   • {note}")

def main():
    """Main test execution"""
    tester = RateLimitStrategyTester()
    results = tester.run_all_tests()
    
    # Save results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"rate_limit_strategy_test_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n💾 Test results saved to: {filename}")
    print("\n✅ Rate limit strategy test suite completed successfully!")

if __name__ == "__main__":
    main() 