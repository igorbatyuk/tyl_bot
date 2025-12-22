import asyncio
from typing import Dict, Set
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class UserRequestLock:
    
    def __init__(self):
        self.active_requests: Set[int] = set()
        self.locks: Dict[int, asyncio.Lock] = {}
    
    async def acquire(self, user_id: int) -> bool:
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        
        if user_id in self.active_requests:
            return False
        
        async with self.locks[user_id]:
            if user_id in self.active_requests:
                return False
            self.active_requests.add(user_id)
            return True
    
    def release(self, user_id: int):
        self.active_requests.discard(user_id)

user_request_lock = UserRequestLock()

class BalanceCache:
    
    def __init__(self, ttl_seconds: int = 30):
        self.cache: Dict[int, tuple[float, int]] = {}
        self.ttl = ttl_seconds
    
    def get(self, user_id: int) -> int | None:
        if user_id in self.cache:
            timestamp, balance = self.cache[user_id]
            if (datetime.now().timestamp() - timestamp) < self.ttl:
                return balance
            else:
                del self.cache[user_id]
        return None
    
    def set(self, user_id: int, balance: int):
        self.cache[user_id] = (datetime.now().timestamp(), balance)
    
    def invalidate(self, user_id: int):
        self.cache.pop(user_id, None)
    
    def clear(self):
        self.cache.clear()

balance_cache = BalanceCache(ttl_seconds=30)

class BalanceDeductionTracker:
    
    def __init__(self):
        self.pending_deductions: Dict[int, str] = {}
        self.completed_deductions: Set[str] = set()
    
    def start_deduction(self, user_id: int, request_id: str) -> bool:
        if user_id in self.pending_deductions:
            return False
        self.pending_deductions[user_id] = request_id
        return True
    
    def complete_deduction(self, user_id: int, request_id: str):
        if user_id in self.pending_deductions:
            completed_id = self.pending_deductions.pop(user_id)
            self.completed_deductions.add(completed_id)
            if len(self.completed_deductions) > 1000:
                self.completed_deductions = set(list(self.completed_deductions)[-1000:])
    
    def cancel_deduction(self, user_id: int):
        self.pending_deductions.pop(user_id, None)

deduction_tracker = BalanceDeductionTracker()

