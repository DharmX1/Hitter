import os
import json
import time
import random
import asyncio
import aiohttp
import tempfile
import threading

PROXY_FILE = "proxies.json"

_proxy_lock = threading.Lock()

def load_proxies() -> dict:
    """Load proxies from JSON file"""
    with _proxy_lock:
        if os.path.exists(PROXY_FILE):
            try:
                with open(PROXY_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

def save_proxies(data: dict):
    """Save proxies to JSON file atomically"""
    with _proxy_lock:
        dir_name = os.path.dirname(PROXY_FILE) or '.'
        fd, temp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, PROXY_FILE)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

def parse_proxy_format(proxy_str: str) -> dict:
    """Parse proxy string into components"""
    proxy_str = proxy_str.strip()
    result = {"user": None, "password": None, "host": None, "port": None, "raw": proxy_str}
    
    try:
        if '@' in proxy_str:
            if proxy_str.count('@') == 1:
                auth_part, host_part = proxy_str.rsplit('@', 1)
                if ':' in auth_part:
                    result["user"], result["password"] = auth_part.split(':', 1)
                if ':' in host_part:
                    result["host"], port_str = host_part.rsplit(':', 1)
                    result["port"] = int(port_str)
        else:
            parts = proxy_str.split(':')
            if len(parts) == 4:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
                result["user"] = parts[2]
                result["password"] = parts[3]
            elif len(parts) == 2:
                result["host"] = parts[0]
                result["port"] = int(parts[1])
    except Exception:
        pass
    
    return result

def get_proxy_url(proxy_str: str) -> str:
    """Convert proxy string to URL format"""
    parsed = parse_proxy_format(proxy_str)
    if parsed["host"] and parsed["port"]:
        if parsed["user"] and parsed["password"]:
            return f"http://{parsed['user']}:{parsed['password']}@{parsed['host']}:{parsed['port']}"
        else:
            return f"http://{parsed['host']}:{parsed['port']}"
    return None

def get_user_proxies(user_id: int) -> list:
    """Get all proxies for a user"""
    proxies = load_proxies()
    user_data = proxies.get(str(user_id), [])
    if isinstance(user_data, str):
        return [user_data] if user_data else []
    return user_data if isinstance(user_data, list) else []

def add_user_proxy(user_id: int, proxy: str):
    """Add a proxy for a user"""
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key not in proxies:
        proxies[user_key] = []
    elif isinstance(proxies[user_key], str):
        proxies[user_key] = [proxies[user_key]] if proxies[user_key] else []
    
    if proxy not in proxies[user_key]:
        proxies[user_key].append(proxy)
    save_proxies(proxies)

def remove_user_proxy(user_id: int, proxy: str = None) -> bool:
    """Remove a proxy (or all) for a user"""
    proxies = load_proxies()
    user_key = str(user_id)
    if user_key in proxies:
        if proxy is None or proxy.lower() == "all":
            del proxies[user_key]
        else:
            if isinstance(proxies[user_key], list):
                proxies[user_key] = [p for p in proxies[user_key] if p != proxy]
                if not proxies[user_key]:
                    del proxies[user_key]
            elif isinstance(proxies[user_key], str) and proxies[user_key] == proxy:
                del proxies[user_key]
        save_proxies(proxies)
        return True
    return False

def get_user_proxy(user_id: int) -> str:
    """Get a random proxy for a user"""
    user_proxies = get_user_proxies(user_id)
    if user_proxies:
        return random.choice(user_proxies)
    return None

def obfuscate_ip(ip: str) -> str:
    """Obfuscate IP for display"""
    if not ip:
        return "N/A"
    parts = ip.split('.')
    if len(parts) == 4:
        return f"{parts[0][0]}XX.{parts[1][0]}XX.{parts[2][0]}XX.{parts[3][0]}XX"
    return "N/A"

async def get_proxy_info(proxy_str: str = None, timeout: int = 15) -> dict:
    """Get info about a proxy (IP, country, etc.)"""
    result = {
        "status": "dead",
        "ip": None,
        "ip_obfuscated": None,
        "country": None,
        "city": None,
        "org": None,
        "using_proxy": False
    }
    
    proxy_url = None
    if proxy_str:
        proxy_url = get_proxy_url(proxy_str)
        result["using_proxy"] = True
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    test_endpoints = [
        "https://httpbin.org/ip",
        "https://api.ipify.org?format=json",
        "http://ip-api.com/json",
    ]
    
    for url in test_endpoints:
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                kwargs = {
                    "timeout": aiohttp.ClientTimeout(total=timeout),
                    "headers": headers
                }
                if proxy_url:
                    kwargs["proxy"] = proxy_url
                
                async with session.get(url, **kwargs) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result["status"] = "alive"
                        
                        ip = data.get("query") or data.get("ip") or data.get("origin")
                        if ip and "," in str(ip):
                            ip = ip.split(",")[0].strip()
                        result["ip"] = ip
                        result["ip_obfuscated"] = obfuscate_ip(ip)
                        result["country"] = data.get("country", "Unknown")
                        result["city"] = data.get("city", "Unknown")
                        result["org"] = data.get("isp", data.get("org", "Unknown"))
                        return result
        except Exception:
            continue
    
    return result

async def check_proxy_alive(proxy_str: str, timeout: int = 15) -> dict:
    """Check if a proxy is alive using multiple endpoints"""
    result = {
        "proxy": proxy_str,
        "status": "dead",
        "response_time": None,
        "external_ip": None,
        "error": None
    }
    
    proxy_url = get_proxy_url(proxy_str)
    if not proxy_url:
        result["error"] = "Invalid format"
        return result
    
    test_endpoints = [
        ("https://httpbin.org/ip", "origin"),
        ("https://api.ipify.org?format=json", "ip"),
        ("http://ip-api.com/json", "query"),
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    for url, ip_key in test_endpoints:
        try:
            start = time.perf_counter()
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(
                    url,
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    headers=headers
                ) as resp:
                    elapsed = round((time.perf_counter() - start) * 1000, 2)
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                            result["status"] = "alive"
                            result["response_time"] = f"{elapsed}ms"
                            result["external_ip"] = data.get(ip_key, str(data)[:50])
                            return result
                        except:
                            text = await resp.text()
                            result["status"] = "alive"
                            result["response_time"] = f"{elapsed}ms"
                            result["external_ip"] = text[:50]
                            return result
        except asyncio.TimeoutError:
            result["error"] = "Timeout"
        except aiohttp.ClientProxyConnectionError:
            result["error"] = "Proxy connection failed"
        except aiohttp.ClientSSLError:
            result["error"] = "SSL error"
        except Exception as e:
            result["error"] = str(e)[:50]
    
    return result

async def check_proxies_batch(proxies: list, max_threads: int = 10) -> list:
    """Check multiple proxies in parallel"""
    semaphore = asyncio.Semaphore(max_threads)
    
    async def check_with_semaphore(proxy):
        async with semaphore:
            return await check_proxy_alive(proxy)
    
    tasks = [check_with_semaphore(p) for p in proxies]
    return await asyncio.gather(*tasks)
