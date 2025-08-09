#!/usr/bin/env python3
"""
📊 Progressive Loading Analyzer
Enhanced analyzer with real-time progress updates and WebSocket integration
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
    from pricing_tools.parallel_shoe_analyzer import ParallelShoeAnalyzer
    from pricing_tools.rate_limit_handler import RateLimitHandler
except ImportError:
    # Fallback for direct execution
    sys.path.append(os.path.join(os.path.dirname(__file__)))
    from parallel_shoe_analyzer import ParallelShoeAnalyzer
    from rate_limit_handler import RateLimitHandler

class ProgressiveLoadingAnalyzer(ParallelShoeAnalyzer):
    """
    Enhanced analyzer with progressive loading and real-time updates
    """
    
    def __init__(self, progress_callback: Optional[Callable] = None, max_workers: int = 3):
        """Initialize with progress callback"""
        super().__init__(max_workers=max_workers)
        self.progress_callback = progress_callback
        self.current_step = 0
        self.total_steps = 5
        
        print(f"📊 Progressive Loading Analyzer initialized")
    
    def _emit_progress(self, step: str, message: str, progress_percentage: Optional[int] = None):
        """Emit progress update"""
        if self.progress_callback:
            update = {
                'step': step,
                'message': message,
                'timestamp': datetime.now().isoformat(),
                'progress_percentage': progress_percentage or self.current_step
            }
            self.progress_callback(update)
            print(f"📊 Progress: {step} - {message}")
    
    def _get_stockx_data_progressive(self, shoe_query: str, size: str) -> Dict:
        """Get StockX data with progress updates"""
        self._emit_progress('🔍', f'Searching StockX for {shoe_query}...', 20)
        
        result = self._get_stockx_data_with_retry(shoe_query, size)
        
        if 'error' not in result:
            bid = result.get('bid', 'N/A')
            ask = result.get('ask', 'N/A')
            self._emit_progress('✅', f'StockX: ${bid}/${ask}', 40)
        else:
            self._emit_progress('❌', f'StockX: {result["error"]}', 40)
        
        return result
    
    def _get_alias_data_progressive(self, shoe_query: str, size: str) -> Dict:
        """Get Alias data with progress updates"""
        self._emit_progress('🔍', f'Searching GOAT for {shoe_query}...', 60)
        
        result = self._get_alias_data_with_retry(shoe_query, size)
        
        if 'error' not in result:
            pricing = result.get('pricing', {})
            lowest_price = pricing.get('lowest_price', 'N/A')
            self._emit_progress('✅', f'GOAT: ${lowest_price} lowest', 80)
        else:
            self._emit_progress('❌', f'GOAT: {result["error"]}', 80)
        
        return result
    
    def _get_data_parallel_progressive(self, shoe_query: str, size: str) -> Tuple[Dict, Dict]:
        """Get StockX and Alias data in parallel with progress updates"""
        self._emit_progress('🚀', f'Starting parallel analysis for {shoe_query}...', 10)
        
        # Create tasks for parallel execution
        tasks = [
            {
                'func': self._get_stockx_data_progressive,
                'args': [shoe_query, size],
                'kwargs': {},
                'name': 'StockX'
            },
            {
                'func': self._get_alias_data_progressive,
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
                future = executor.submit(task['func'], *task['args'], **task['kwargs'])
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
    
    def analyze_shoe_with_progressive_loading(self, shoe_query: str, size: str = "10") -> Dict:
        """
        Comprehensive analysis with progressive loading and real-time updates
        """
        print(f"📊 Progressive Analysis: {shoe_query} (Size: {size})")
        
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
            'progressive_loading': True,
            'performance_metrics': {}
        }

        try:
            # Step 1: Get data in parallel with progress updates
            self._emit_progress('🚀', f'Starting analysis for {shoe_query}...', 5)
            
            parallel_start = time.time()
            stockx_data, alias_data = self._get_data_parallel_progressive(shoe_query, size)
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
            self._emit_progress('🔍', 'Checking for SKU mismatches...', 85)
            sku_mismatch = self._check_sku_mismatch(stockx_raw, alias_raw)
            if sku_mismatch:
                result['sku_mismatch_warning'] = sku_mismatch
                self._emit_progress('⚠️', f'SKU mismatch detected: {sku_mismatch["message"]}', 87)
                
                # Try to find corresponding match on the other platform
                corresponding_match = self._find_corresponding_match(
                    sku_mismatch['better_sku'], 
                    sku_mismatch['better_name'], 
                    sku_mismatch['worse_match']
                )
                
                if corresponding_match:
                    self._emit_progress('✅', f'Found corresponding {sku_mismatch["worse_match"]} match!', 89)
                    if sku_mismatch['worse_match'] == 'alias':
                        alias_raw = corresponding_match
                        result['raw_data']['alias'] = alias_raw
                    else:
                        stockx_raw = corresponding_match
                        result['raw_data']['stockx'] = stockx_raw
            
            # Step 3: Apply pricing logic
            self._emit_progress('🧮', 'Applying pricing logic and calculations...', 90)
            calculations = self._apply_pricing_logic(stockx_raw, alias_raw, stockx_metadata, alias_metadata, size)
            result['calculations'] = calculations
            
            # Step 4: Generate final recommendation
            self._emit_progress('🎯', 'Generating final recommendation...', 95)
            final_recommendation = self._generate_recommendation(calculations)
            result['final_recommendation'] = final_recommendation
            
            # Step 5: Calculate confidence
            confidence = self._calculate_confidence(calculations)
            result['confidence'] = confidence
            
            # Step 6: Save result
            self._emit_progress('💾', 'Saving analysis result...', 98)
            result['processing_time'] = time.time() - start_time
            result['success'] = True
            
            # Save the result
            saved_path = self._save_result(result)
            result['saved_path'] = saved_path
            
            # Final success message
            self._emit_progress('✅', f'Analysis completed in {result["processing_time"]:.2f}s!', 100)
            
            print(f"✅ Progressive analysis completed in {result['processing_time']:.2f}s")
            
            # Add performance comparison
            if hasattr(self, '_last_sequential_time'):
                improvement = ((self._last_sequential_time - result['processing_time']) / self._last_sequential_time) * 100
                result['performance_metrics']['improvement_percentage'] = improvement
                print(f"🚀 Performance improvement: {improvement:.1f}%")
            
            return result
            
        except Exception as e:
            error_msg = f"Progressive analysis failed: {str(e)}"
            print(f"❌ {error_msg}")
            self._emit_progress('❌', error_msg, 100)
            result['errors'].append(error_msg)
            result['processing_time'] = time.time() - start_time
            return result 