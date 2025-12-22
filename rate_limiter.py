import time
from collections import defaultdict
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[int, list] = defaultdict(list)
        self._lock = {}
    
    def is_allowed(self, user_id: int) -> Tuple[bool, int]:
        current_time = time.time()
        
        if user_id in self.requests:
            self.requests[user_id] = [
                req_time for req_time in self.requests[user_id]
                if current_time - req_time < self.window_seconds
            ]
        
        if len(self.requests[user_id]) >= self.max_requests:
            oldest_request = min(self.requests[user_id])
            wait_time = int(self.window_seconds - (current_time - oldest_request)) + 1
            return False, wait_time
        
        self.requests[user_id].append(current_time)
        return True, 0
    
    def reset(self, user_id: int):
        if user_id in self.requests:
            del self.requests[user_id]
    
    def get_stats(self, user_id: int) -> Dict:
        current_time = time.time()
        if user_id in self.requests:
            recent_requests = [
                req_time for req_time in self.requests[user_id]
                if current_time - req_time < self.window_seconds
            ]
            return {
                'requests_count': len(recent_requests),
                'max_requests': self.max_requests,
                'window_seconds': self.window_seconds
            }
        return {
            'requests_count': 0,
            'max_requests': self.max_requests,
            'window_seconds': self.window_seconds
        }

message_rate_limiter = RateLimiter(max_requests=20, window_seconds=60)
service_rate_limiter = RateLimiter(max_requests=10, window_seconds=60)
payment_rate_limiter = RateLimiter(max_requests=5, window_seconds=300)


