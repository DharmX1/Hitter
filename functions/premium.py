"""Premium key management for the bot"""
import json
import os
import time
import secrets
import string
import tempfile
import threading
from typing import Optional, Dict, List

KEYS_FILE = "premium_keys.json"
USERS_FILE = "premium_users.json"

_file_locks = {}
_lock_mutex = threading.Lock()

def _get_file_lock(file_path: str) -> threading.Lock:
    """Get or create a lock for a specific file"""
    with _lock_mutex:
        if file_path not in _file_locks:
            _file_locks[file_path] = threading.Lock()
        return _file_locks[file_path]

def _load_json(file_path: str) -> dict:
    """Load JSON file or return empty dict"""
    lock = _get_file_lock(file_path)
    with lock:
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

def _save_json(file_path: str, data: dict):
    """Save data to JSON file atomically"""
    lock = _get_file_lock(file_path)
    with lock:
        dir_name = os.path.dirname(file_path) or '.'
        fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, file_path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

def generate_key(duration_days: int) -> str:
    """Generate a new premium key with specified duration in days"""
    chars = string.ascii_uppercase + string.digits
    key = 'FN-' + ''.join(secrets.choice(chars) for _ in range(16))
    
    keys_data = _load_json(KEYS_FILE)
    keys_data[key] = {
        'duration_days': duration_days,
        'created_at': time.time(),
        'used': False,
        'used_by': None,
        'used_at': None
    }
    _save_json(KEYS_FILE, keys_data)
    
    return key

def get_all_keys() -> Dict[str, dict]:
    """Get all keys (used and unused)"""
    return _load_json(KEYS_FILE)

def get_unused_keys() -> Dict[str, dict]:
    """Get only unused keys"""
    keys = _load_json(KEYS_FILE)
    return {k: v for k, v in keys.items() if not v.get('used', False)}

def delete_key(key: str) -> bool:
    """Delete a key"""
    keys_data = _load_json(KEYS_FILE)
    if key in keys_data:
        del keys_data[key]
        _save_json(KEYS_FILE, keys_data)
        return True
    return False

def redeem_key(user_id: int, key: str) -> tuple[bool, str]:
    """
    Redeem a key for a user.
    Returns (success, message)
    """
    keys_data = _load_json(KEYS_FILE)
    
    if key not in keys_data:
        return False, "Invalid key"
    
    key_info = keys_data[key]
    
    if key_info.get('used', False):
        return False, "Key already used"
    
    duration_days = key_info['duration_days']
    duration_seconds = duration_days * 24 * 60 * 60
    
    users_data = _load_json(USERS_FILE)
    user_id_str = str(user_id)
    
    current_time = time.time()
    
    if user_id_str in users_data and users_data[user_id_str]['expires_at'] > current_time:
        new_expiry = users_data[user_id_str]['expires_at'] + duration_seconds
    else:
        new_expiry = current_time + duration_seconds
    
    users_data[user_id_str] = {
        'expires_at': new_expiry,
        'last_key': key,
        'redeemed_at': current_time
    }
    _save_json(USERS_FILE, users_data)
    
    keys_data[key]['used'] = True
    keys_data[key]['used_by'] = user_id
    keys_data[key]['used_at'] = current_time
    _save_json(KEYS_FILE, keys_data)
    
    return True, f"{duration_days} days added"

def is_premium(user_id: int) -> bool:
    """Check if user has active premium"""
    users_data = _load_json(USERS_FILE)
    user_id_str = str(user_id)
    
    if user_id_str not in users_data:
        return False
    
    return users_data[user_id_str]['expires_at'] > time.time()

def get_premium_status(user_id: int) -> Optional[dict]:
    """Get user's premium status details"""
    users_data = _load_json(USERS_FILE)
    user_id_str = str(user_id)
    
    if user_id_str not in users_data:
        return None
    
    user_info = users_data[user_id_str]
    expires_at = user_info['expires_at']
    current_time = time.time()
    
    if expires_at <= current_time:
        return None
    
    time_left = expires_at - current_time
    days_left = int(time_left / (24 * 60 * 60))
    hours_left = int((time_left % (24 * 60 * 60)) / (60 * 60))
    mins_left = int((time_left % (60 * 60)) / 60)
    
    return {
        'expires_at': expires_at,
        'time_left': time_left,
        'days_left': days_left,
        'hours_left': hours_left,
        'mins_left': mins_left,
        'display': f"{days_left}d {hours_left}h {mins_left}m"
    }

def revoke_premium(user_id: int) -> bool:
    """Revoke a user's premium status"""
    users_data = _load_json(USERS_FILE)
    user_id_str = str(user_id)
    
    if user_id_str in users_data:
        del users_data[user_id_str]
        _save_json(USERS_FILE, users_data)
        return True
    return False

def get_all_premium_users() -> List[dict]:
    """Get all users with active premium"""
    users_data = _load_json(USERS_FILE)
    current_time = time.time()
    
    active_users = []
    for user_id_str, info in users_data.items():
        if info['expires_at'] > current_time:
            time_left = info['expires_at'] - current_time
            days_left = int(time_left / (24 * 60 * 60))
            hours_left = int((time_left % (24 * 60 * 60)) / (60 * 60))
            
            active_users.append({
                'user_id': int(user_id_str),
                'expires_at': info['expires_at'],
                'time_left': f"{days_left}d {hours_left}h"
            })
    
    return active_users
