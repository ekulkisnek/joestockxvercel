#!/usr/bin/env python3
"""
🚀 Parallel Implementation Example
Practical example of implementing parallel execution in the shoe analyzer
"""

import asyncio
import time
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

class ParallelShoeAnalyzer(AdvancedShoeAnalyzer):
    """
    Enhanced shoe analyzer with parallel execution capabilities
    """
    
    def __init__(self):
        super().__init__()
        self.max_workers = 3  # Conservative limit to avoid rate limits
        
    def analyze_shoe_with_pricing_logic_parallel(self, shoe_query: str, size: str = "10") -> Dict:
        """
        Parallel version of the analysis with concurrent API calls
        """
        print(f"🎯 Analyzing: {shoe_query} (Size: {size}) - PARALLEL EXECUTION")
        
        start_time = time.time()
        result = {
            'query': shoe_query,
            'size': size,
            'timestamp': datetime.now().isoformat(),
            'processing_time': 0,
            'success': False,
            'errors': [],
            'warnings': [],
            'execution_mode': 'parallel',
            'calculations': {},
            'final_recommendation': {},
            'raw_data': {},
            'search_metadata': {}
        }

        try:
            # Execute API calls in parallel
            stockx_data, alias_data = self._get_data_parallel(shoe_query, size)
            
            # Separate raw API data from search metadata
            stockx_raw = {k: v for k, v in stockx_data.items() if k not in ['search_query', 'search_size', 'success']}
            stockx_metadata = {k: v for k, v in stockx_data.items() if k in ['search_query', 'search_size', 'success']}
            
            alias_raw = {k: v for k, v in alias_data.items() if k not in ['search_query', 'search_size', 'success']}
            alias_metadata = {k: v for k, v in alias_data.items() if k in ['search_query', 'search_size', 'success']}
            
            result['raw_data']['stockx'] = stockx_raw
            result['raw_data']['alias'] = alias_raw
            result['search_metadata']['stockx'] = stockx_metadata
            result['search_metadata']['alias'] = alias_metadata
            
            # Apply pricing logic and generate recommendation
            pricing_logic = self._apply_pricing_logic(stockx_raw, alias_raw, stockx_metadata, alias_metadata, size)
            result['calculations'] = pricing_logic
            
            recommendation = self._generate_recommendation(pricing_logic)
            result['final_recommendation'] = recommendation
            
            result['success'] = True
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            result['errors'].append(str(e))
        
        result['processing_time'] = round(time.time() - start_time, 2)
        
        # Save result
        self._save_result(result)
        
        return result

    def _get_data_parallel(self, shoe_query: str, size: str) -> Tuple[Dict, Dict]:
        """
        Get StockX and Alias data in parallel
        """
        print("🚀 Executing API calls in parallel...")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit both API calls simultaneously
            stockx_future = executor.submit(self._get_stockx_data, shoe_query, size)
            alias_future = executor.submit(self._get_alias_data, shoe_query, size)
            
            # Wait for both to complete
            stockx_data = stockx_future.result()
            alias_data = alias_future.result()
            
            print("✅ All API calls completed")
            
        return stockx_data, alias_data

    def analyze_multiple_shoes_parallel(self, shoes: List[Tuple[str, str]]) -> List[Dict]:
        """
        Analyze multiple shoes in parallel
        """
        print(f"🚀 Analyzing {len(shoes)} shoes in parallel...")
        
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all analysis tasks
            future_to_shoe = {
                executor.submit(self.analyze_shoe_with_pricing_logic_parallel, shoe, size): (shoe, size)
                for shoe, size in shoes
            }
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_shoe):
                shoe, size = future_to_shoe[future]
                try:
                    result = future.result()
                    results.append(result)
                    print(f"✅ Completed: {shoe} ({result['processing_time']:.2f}s)")
                except Exception as e:
                    print(f"❌ Failed: {shoe} - {str(e)}")
                    results.append({
                        'query': shoe,
                        'size': size,
                        'success': False,
                        'error': str(e)
                    })
        
        return results

class ProgressiveLoadingAnalyzer(ParallelShoeAnalyzer):
    """
    Analyzer with progressive loading capabilities for real-time updates
    """
    
    def __init__(self, progress_callback=None):
        super().__init__()
        self.progress_callback = progress_callback
    
    def analyze_shoe_with_progressive_loading(self, shoe_query: str, size: str = "10") -> Dict:
        """
        Analyze with progressive loading updates
        """
        if self.progress_callback:
            self.progress_callback({
                'step': 'start',
                'message': f'Starting analysis of {shoe_query}',
                'progress': 0
            })
        
        start_time = time.time()
        result = {
            'query': shoe_query,
            'size': size,
            'timestamp': datetime.now().isoformat(),
            'processing_time': 0,
            'success': False,
            'errors': [],
            'warnings': [],
            'execution_mode': 'progressive',
            'calculations': {},
            'final_recommendation': {},
            'raw_data': {},
            'search_metadata': {}
        }

        try:
            # Step 1: StockX Search
            if self.progress_callback:
                self.progress_callback({
                    'step': 'stockx_search',
                    'message': 'Searching StockX...',
                    'progress': 25
                })
            
            stockx_data = self._get_stockx_data(shoe_query, size)
            
            if self.progress_callback:
                self.progress_callback({
                    'step': 'stockx_complete',
                    'message': f'StockX: ${stockx_data.get("bid", "N/A")}/${stockx_data.get("ask", "N/A")}',
                    'progress': 50,
                    'data': stockx_data
                })
            
            # Step 2: Alias/GOAT Search
            if self.progress_callback:
                self.progress_callback({
                    'step': 'alias_search',
                    'message': 'Searching GOAT/Alias...',
                    'progress': 75
                })
            
            alias_data = self._get_alias_data(shoe_query, size)
            
            if self.progress_callback:
                self.progress_callback({
                    'step': 'alias_complete',
                    'message': f'GOAT: {alias_data.get("sales_volume", {}).get("sales_per_week", 0)} sales/week',
                    'progress': 90,
                    'data': alias_data
                })
            
            # Step 3: Final calculations
            if self.progress_callback:
                self.progress_callback({
                    'step': 'calculations',
                    'message': 'Calculating final recommendation...',
                    'progress': 95
                })
            
            # Process data and generate recommendation
            stockx_raw = {k: v for k, v in stockx_data.items() if k not in ['search_query', 'search_size', 'success']}
            stockx_metadata = {k: v for k, v in stockx_data.items() if k in ['search_query', 'search_size', 'success']}
            
            alias_raw = {k: v for k, v in alias_data.items() if k not in ['search_query', 'search_size', 'success']}
            alias_metadata = {k: v for k, v in alias_data.items() if k in ['search_query', 'search_size', 'success']}
            
            result['raw_data']['stockx'] = stockx_raw
            result['raw_data']['alias'] = alias_raw
            result['search_metadata']['stockx'] = stockx_metadata
            result['search_metadata']['alias'] = alias_metadata
            
            pricing_logic = self._apply_pricing_logic(stockx_raw, alias_raw, stockx_metadata, alias_metadata, size)
            result['calculations'] = pricing_logic
            
            recommendation = self._generate_recommendation(pricing_logic)
            result['final_recommendation'] = recommendation
            
            result['success'] = True
            
            if self.progress_callback:
                self.progress_callback({
                    'step': 'complete',
                    'message': f'Analysis complete! Buy at ${recommendation.get("price", "N/A")}',
                    'progress': 100,
                    'result': result
                })
            
        except Exception as e:
            print(f"❌ Analysis error: {e}")
            result['errors'].append(str(e))
            
            if self.progress_callback:
                self.progress_callback({
                    'step': 'error',
                    'message': f'Error: {str(e)}',
                    'progress': 100,
                    'error': str(e)
                })
        
        result['processing_time'] = round(time.time() - start_time, 2)
        return result

def demo_parallel_execution():
    """Demonstrate parallel execution benefits"""
    print("🚀 Parallel Execution Demo")
    print("=" * 50)
    
    # Test data
    test_shoes = [
        ("Nike Air Jordan 1 Retro High OG", "10"),
        ("Adidas Yeezy Boost 350 V2", "10"),
        ("Nike Air Force 1 '07", "10"),
        ("Converse Chuck Taylor All Star", "10"),
        ("Nike Dunk Low", "10")
    ]
    
    # Test 1: Sequential execution
    print("\n📊 Testing Sequential Execution")
    sequential_analyzer = AdvancedShoeAnalyzer()
    
    start_time = time.time()
    sequential_results = []
    for shoe, size in test_shoes:
        result = sequential_analyzer.analyze_shoe_with_pricing_logic(shoe, size)
        sequential_results.append(result)
        print(f"   ✅ {shoe}: {result['processing_time']:.2f}s")
    
    sequential_total = time.time() - start_time
    print(f"   📈 Sequential Total: {sequential_total:.2f}s")
    
    # Test 2: Parallel execution
    print("\n🧵 Testing Parallel Execution")
    parallel_analyzer = ParallelShoeAnalyzer()
    
    start_time = time.time()
    parallel_results = parallel_analyzer.analyze_multiple_shoes_parallel(test_shoes)
    parallel_total = time.time() - start_time
    
    print(f"   📈 Parallel Total: {parallel_total:.2f}s")
    
    # Calculate improvement
    improvement = ((sequential_total - parallel_total) / sequential_total) * 100
    print(f"   🚀 Improvement: {improvement:.1f}% faster")
    
    return {
        'sequential_total': sequential_total,
        'parallel_total': parallel_total,
        'improvement': improvement
    }

def demo_progressive_loading():
    """Demonstrate progressive loading"""
    print("\n📡 Progressive Loading Demo")
    print("=" * 50)
    
    def progress_callback(update):
        print(f"   📡 {update['step']}: {update['message']} ({update['progress']}%)")
    
    progressive_analyzer = ProgressiveLoadingAnalyzer(progress_callback)
    
    result = progressive_analyzer.analyze_shoe_with_progressive_loading(
        "Nike Air Jordan 1 Retro High OG", "10"
    )
    
    print(f"   ✅ Final Result: {result['final_recommendation'].get('recommendation', 'N/A')}")
    
    return result

def implementation_guide():
    """Print implementation guide"""
    print("\n📋 IMPLEMENTATION GUIDE")
    print("=" * 50)
    
    print("""
🎯 Phase 1: Parallel Execution (HIGH PRIORITY)
==============================================

1. Create ParallelShoeAnalyzer class (shown above)
2. Replace sequential calls with parallel execution:
   - Use ThreadPoolExecutor for concurrent API calls
   - Limit max_workers to 3 to avoid rate limits
   - Expected improvement: 50-70% faster

2. Update the main analysis method:
   ```python
   def analyze_shoe_with_pricing_logic_parallel(self, shoe_query: str, size: str = "10"):
       # Execute API calls in parallel
       stockx_data, alias_data = self._get_data_parallel(shoe_query, size)
       # ... rest of the logic
   ```

🎯 Phase 2: Progressive Loading (MEDIUM PRIORITY)
=================================================

1. Create ProgressiveLoadingAnalyzer class (shown above)
2. Add progress callback system:
   - Real-time updates via WebSocket
   - Show each step as it completes
   - Dramatically improves perceived performance

3. Integrate with existing WebSocket system:
   ```python
   @socketio.on('analyze_shoe')
   def handle_analysis(data):
       def progress_callback(update):
           emit('progress', update)
       
       analyzer = ProgressiveLoadingAnalyzer(progress_callback)
       result = analyzer.analyze_shoe_with_progressive_loading(data['shoe'], data['size'])
       emit('result', result)
   ```

🎯 Phase 3: Smart Caching (MEDIUM PRIORITY)
===========================================

1. Implement caching layer:
   - Cache API responses for 15-30 minutes
   - Use Redis or in-memory cache
   - Reduce repeat API calls

2. Cache implementation:
   ```python
   def _get_cached_data(self, key: str) -> Optional[Dict]:
       return self.cache.get(key)
   
   def _cache_data(self, key: str, data: Dict, ttl: int = 1800):
       self.cache.setex(key, ttl, json.dumps(data))
   ```

🎯 Rate Limit Management
========================

1. Implement exponential backoff:
   ```python
   def _api_call_with_retry(self, api_call, max_retries=3):
       for attempt in range(max_retries):
           try:
               return api_call()
           except RateLimitError:
               wait_time = 2 ** attempt
               time.sleep(wait_time)
   ```

2. Monitor rate limits:
   - Track request counts
   - Implement circuit breaker pattern
   - Graceful degradation when limits hit

🎯 Expected Results
==================

Phase 1 (Parallel Execution):
- Execution time: 50-70% reduction
- Implementation time: 2-4 hours
- User experience: Significant improvement

Phase 2 (Progressive Loading):
- Perceived performance: Immediate feedback
- Implementation time: 4-6 hours
- User satisfaction: Dramatic improvement

Phase 3 (Caching):
- Repeat queries: Instant results
- Implementation time: 6-8 hours
- API pressure: Significant reduction
    """)

if __name__ == "__main__":
    print("🚀 Parallel Implementation Example")
    print("This demonstrates how to implement parallel execution in the shoe analyzer")
    
    # Run demos
    demo_parallel_execution()
    demo_progressive_loading()
    implementation_guide()
    
    print("\n✅ Demo completed!")
    print("\n🎯 Next Steps:")
    print("   1. Implement ParallelShoeAnalyzer in your codebase")
    print("   2. Add progressive loading for better UX")
    print("   3. Monitor rate limits and implement caching")
    print("   4. Test with real API calls to validate improvements") 