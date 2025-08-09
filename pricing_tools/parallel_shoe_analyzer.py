#!/usr/bin/env python3
"""
🚀 Parallel Shoe Analyzer
Enhanced shoe analyzer with parallel execution and rate limit handling
"""

import sys
import os
import json
import time
import concurrent.futures
import threading
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable

# Add parent directory to path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from pricing_tools.advanced_shoe_analyzer import AdvancedShoeAnalyzer
    from pricing_tools.rate_limit_handler import RateLimitHandler, ConservativeThreadPool
except ImportError:
    # Fallback for direct execution
    sys.path.append(os.path.join(os.path.dirname(__file__)))
    from advanced_shoe_analyzer import AdvancedShoeAnalyzer
    from rate_limit_handler import RateLimitHandler, ConservativeThreadPool

class ParallelShoeAnalyzer(AdvancedShoeAnalyzer):
    """
    Enhanced shoe analyzer with parallel execution capabilities
    """
    
    def __init__(self, max_workers: int = 3, delay_between_requests: float = 2.0):
        """Initialize with parallel execution settings"""
        super().__init__()
        self.max_workers = max_workers
        self.delay_between_requests = delay_between_requests
        self.rate_limit_handler = RateLimitHandler()
        self.thread_pool = ConservativeThreadPool(max_workers, delay_between_requests)
        
        print(f"🚀 Parallel Shoe Analyzer initialized (max_workers={max_workers})")
    
    def _get_stockx_data_with_retry(self, shoe_query: str, size: str) -> Dict:
        """Get StockX data with retry logic"""
        return self.rate_limit_handler.api_call_with_retry(
            self._get_stockx_data, shoe_query, size
        )
    
    def _get_alias_data_with_retry(self, shoe_query: str, size: str) -> Dict:
        """Get Alias data with retry logic"""
        return self.rate_limit_handler.api_call_with_retry(
            self._get_alias_data, shoe_query, size
        )
    
    def _get_data_parallel(self, shoe_query: str, size: str) -> Tuple[Dict, Dict]:
        """Get StockX and Alias data in parallel"""
        print(f"🚀 Executing parallel API calls for: {shoe_query}")
        
        # Create tasks for parallel execution
        tasks = [
            {
                'func': self._get_stockx_data,
                'args': [shoe_query, size],
                'kwargs': {},
                'name': 'StockX'
            },
            {
                'func': self._get_alias_data,
                'args': [shoe_query, size],
                'kwargs': {},
                'name': 'Alias/GOAT'
            }
        ]
        
        # Execute in parallel
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            
            # Submit tasks
            for task in tasks:
                future = executor.submit(
                    self.rate_limit_handler.api_call_with_retry,
                    task['func'],
                    *task['args'],
                    **task['kwargs']
                )
                futures.append((future, task['name']))
            
            # Collect results
            results = {}
            for future, name in futures:
                try:
                    result = future.result()
                    results[name] = result
                    print(f"✅ {name} data retrieved successfully")
                except Exception as e:
                    results[name] = {'error': str(e)}
                    print(f"❌ {name} data retrieval failed: {str(e)}")
        
        # Extract StockX and Alias data
        stockx_data = results.get('StockX', {'error': 'StockX data not available'})
        alias_data = results.get('Alias/GOAT', {'error': 'Alias/GOAT data not available'})
        
        return stockx_data, alias_data
    
    def analyze_shoe_with_pricing_logic_parallel(self, shoe_query: str, size: str = "10") -> Dict:
        """
        Comprehensive analysis with parallel execution and detailed pricing logic
        """
        print(f"🎯 Parallel Analysis: {shoe_query} (Size: {size})")
        
        start_time = time.time()
        result = {
            'query': shoe_query,
            'size': size,
            'timestamp': datetime.now().isoformat(),
            'processing_time': 0,
            'success': False,
            'errors': [],
            'warnings': [],
            'sku_mismatch_warning': None,
            'calculations': {},
            'final_recommendation': {},
            'raw_data': {},
            'search_metadata': {},
            'parallel_execution': True,
            'performance_metrics': {}
        }

        try:
            # Step 1: Get data in parallel
            print("🚀 Step 1: Getting StockX and Alias data in parallel...")
            parallel_start = time.time()
            
            stockx_data, alias_data = self._get_data_parallel(shoe_query, size)
            
            parallel_time = time.time() - parallel_start
            result['performance_metrics']['parallel_execution_time'] = parallel_time
            print(f"✅ Parallel execution completed in {parallel_time:.2f}s")
            
            # Separate raw API data from search metadata
            stockx_raw = {k: v for k, v in stockx_data.items() if k not in ['search_query', 'search_size', 'success']}
            stockx_metadata = {k: v for k, v in stockx_data.items() if k in ['search_query', 'search_size', 'success']}
            
            alias_raw = {k: v for k, v in alias_data.items() if k not in ['search_query', 'search_size', 'success']}
            alias_metadata = {k: v for k, v in alias_data.items() if k in ['search_query', 'search_size', 'success']}
            
            result['raw_data']['stockx'] = stockx_raw
            result['raw_data']['alias'] = alias_raw
            result['search_metadata']['stockx'] = stockx_metadata
            result['search_metadata']['alias'] = alias_metadata
            
            # Step 2: Check for SKU mismatch
            print("🔍 Step 2: Checking for SKU mismatches...")
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
                    if sku_mismatch['worse_match'] == 'alias':
                        alias_raw = corresponding_match
                        result['raw_data']['alias'] = alias_raw
                    else:
                        stockx_raw = corresponding_match
                        result['raw_data']['stockx'] = stockx_raw
            
            # Step 3: Apply pricing logic
            print("🧮 Step 3: Applying pricing logic...")
            calculations = self._apply_pricing_logic(stockx_raw, alias_raw, stockx_metadata, alias_metadata, size)
            result['calculations'] = calculations
            
            # Step 4: Generate final recommendation
            print("🎯 Step 4: Generating final recommendation...")
            final_recommendation = self._generate_recommendation(calculations)
            result['final_recommendation'] = final_recommendation
            
            # Step 5: Calculate confidence
            confidence = self._calculate_confidence(calculations)
            result['confidence'] = confidence
            
            # Step 6: Save result
            print("💾 Step 5: Saving result...")
            result['processing_time'] = time.time() - start_time
            result['success'] = True
            
            # Save the result
            saved_path = self._save_result(result)
            result['saved_path'] = saved_path
            
            print(f"✅ Parallel analysis completed in {result['processing_time']:.2f}s")
            
            # Add performance comparison
            if hasattr(self, '_last_sequential_time'):
                improvement = ((self._last_sequential_time - result['processing_time']) / self._last_sequential_time) * 100
                result['performance_metrics']['improvement_percentage'] = improvement
                print(f"🚀 Performance improvement: {improvement:.1f}%")
            
            return result
            
        except Exception as e:
            error_msg = f"Parallel analysis failed: {str(e)}"
            print(f"❌ {error_msg}")
            result['errors'].append(error_msg)
            result['processing_time'] = time.time() - start_time
            return result
    
    def get_performance_metrics(self) -> Dict:
        """Get performance metrics from rate limit handler"""
        return self.rate_limit_handler.get_statistics() 