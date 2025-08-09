#!/usr/bin/env python3
"""
🔄 Rate Limit Handler
Handles API rate limiting with exponential backoff and circuit breaker pattern
"""

import time
import threading
from typing import Dict, Callable, Optional, Any
from datetime import datetime

class RateLimitHandler:
    """Rate limit handler with exponential backoff and circuit breaker pattern"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 2.0, 
                 failure_threshold: int = 5, recovery_timeout: int = 60):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        
        # Circuit breaker state
        self.failure_count = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Statistics
        self.request_count = 0
        self.rate_limit_hits = 0
        self.successful_requests = 0
        self.failed_requests = 0
    
    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open"""
        with self._lock:
            if self.failure_count >= self.failure_threshold:
                if self.last_failure_time:
                    time_since_failure = time.time() - self.last_failure_time
                    if time_since_failure < self.recovery_timeout:
                        return True
                    else:
                        # Reset circuit breaker
                        self.failure_count = 0
                        self.last_failure_time = None
                        self.state = 'CLOSED'
        return False
    
    def _record_failure(self):
        """Record a failure for circuit breaker"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            self.failed_requests += 1
            
            if self.failure_count >= self.failure_threshold:
                self.state = 'OPEN'
    
    def _record_success(self):
        """Record a success for circuit breaker"""
        with self._lock:
            if self.failure_count > 0:
                self.failure_count = 0
                self.last_failure_time = None
                self.state = 'CLOSED'
            self.successful_requests += 1
    
    def api_call_with_retry(self, api_call: Callable, *args, **kwargs) -> Dict:
        """Execute API call with retry logic and rate limit handling"""
        if self._is_circuit_breaker_open():
            return {'error': 'Circuit breaker open - too many failures'}
        
        self.request_count += 1
        
        for attempt in range(self.max_retries):
            try:
                result = api_call(*args, **kwargs)
                
                # Reset circuit breaker on success
                if attempt > 0:
                    self._record_success()
                
                return result
                
            except Exception as e:
                error_str = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_str or "rate limit" in error_str.lower():
                    self.rate_limit_hits += 1
                    self._record_failure()
                    
                    if attempt < self.max_retries - 1:
                        wait_time = self.base_delay * (2 ** attempt)
                        print(f"⚠️ Rate limited! Waiting {wait_time}s and retrying (attempt {attempt + 1}/{self.max_retries})...")
                        time.sleep(wait_time)
                    else:
                        print(f"❌ Max retries reached for rate limiting")
                        return {'error': f'Rate limit exceeded after {self.max_retries} attempts'}
                else:
                    # Non-rate limit error
                    self._record_failure()
                    return {'error': error_str}
        
        return {'error': 'Max retries exceeded'}
    
    def get_statistics(self) -> Dict:
        """Get current statistics"""
        with self._lock:
            return {
                'request_count': self.request_count,
                'rate_limit_hits': self.rate_limit_hits,
                'successful_requests': self.successful_requests,
                'failed_requests': self.failed_requests,
                'circuit_breaker_state': self.state,
                'failure_count': self.failure_count
            }

class ConservativeThreadPool:
    """Conservative thread pool for API calls"""
    
    def __init__(self, max_workers: int = 3, delay_between_requests: float = 2.0):
        self.max_workers = max_workers
        self.delay_between_requests = delay_between_requests
        self.rate_limit_handler = RateLimitHandler()
    
    def execute_parallel(self, tasks: list) -> list:
        """Execute tasks in parallel with conservative threading"""
        import concurrent.futures
        
        def execute_task(task):
            """Execute a single task with rate limit handling"""
            try:
                result = self.rate_limit_handler.api_call_with_retry(task['func'], *task.get('args', []), **task.get('kwargs', {}))
                time.sleep(self.delay_between_requests)  # Conservative delay
                return result
            except Exception as e:
                return {'error': str(e)}
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(execute_task, task) for task in tasks]
            results = []
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append({'error': str(e)})
        
        return results 