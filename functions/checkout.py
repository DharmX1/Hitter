import re
import os
import time
import base64
import shutil
import aiohttp
from urllib.parse import unquote
from functions.session import get_session, HEADERS

def find_playwright_chromium():
    """Find Playwright's installed chromium in cache directories"""
    import glob
    cache_dirs = [
        '/ms-playwright',
        '/root/.cache/ms-playwright',
        os.path.expanduser('~/.cache/ms-playwright'),
        '/home/runner/.cache/ms-playwright',
    ]
    for cache_dir in cache_dirs:
        if os.path.exists(cache_dir):
            chrome_patterns = [
                f'{cache_dir}/chromium-*/chrome-linux/chrome',
                f'{cache_dir}/chromium-*/chrome-linux64/chrome',
                f'{cache_dir}/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell',
            ]
            for pattern in chrome_patterns:
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]
    return None

def get_chromium_path():
    """Get chromium path with fallback options"""
    pw_chrome = find_playwright_chromium()
    if pw_chrome:
        return pw_chrome
    system_path = shutil.which('chromium')
    if system_path:
        return system_path
    fallback_paths = [
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/google-chrome',
        '/usr/bin/google-chrome-stable',
    ]
    for path in fallback_paths:
        if os.path.exists(path):
            return path
    return None

async def launch_browser(playwright):
    """Launch browser - tries multiple methods to find and launch chromium"""
    browser_args = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
    
    try:
        browser = await playwright.chromium.launch(headless=True, args=browser_args)
        return browser
    except Exception as e1:
        chromium_path = get_chromium_path()
        if chromium_path:
            try:
                browser = await playwright.chromium.launch(
                    headless=True, 
                    executable_path=chromium_path, 
                    args=browser_args
                )
                return browser
            except Exception as e2:
                raise Exception(f"Browser launch failed: {str(e2)[:50]}")
        raise Exception(f"No browser found: {str(e1)[:50]}")

def get_currency_symbol(currency: str) -> str:
    """Get currency symbol for display"""
    symbols = {
        "USD": "$", "EUR": "€", "GBP": "£", "INR": "₹", "JPY": "¥",
        "CNY": "¥", "KRW": "₩", "RUB": "₽", "BRL": "R$", "CAD": "C$",
        "AUD": "A$", "MXN": "MX$", "SGD": "S$", "HKD": "HK$", "THB": "฿",
        "VND": "₫", "PHP": "₱", "IDR": "Rp", "MYR": "RM", "ZAR": "R",
        "CHF": "CHF", "SEK": "kr", "NOK": "kr", "DKK": "kr", "PLN": "zł",
        "TRY": "₺", "AED": "د.إ", "SAR": "﷼", "ILS": "₪", "TWD": "NT$"
    }
    return symbols.get(currency, "")

def extract_checkout_url(text: str) -> str:
    """Extract Stripe checkout URL from text"""
    patterns = [
        r'https?://checkout\.stripe\.com/c/pay/cs_[^\s\"\'\<\>\)]+',
        r'https?://checkout\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://buy\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://billing\.stripe\.com/p/subscription/recovery/[^\s\"\'\<\>\)]+',
        r'https?://billing\.stripe\.com/[^\s\"\'\<\>\)]+',
        r'https?://invoice\.stripe\.com/i/[^\s\"\'\<\>\)]+',
    ]
    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            url = m.group(0).rstrip('.,;:')
            return url
    return None

def is_billing_url(url: str) -> bool:
    """Check if URL is a Stripe billing/subscription recovery URL"""
    return 'billing.stripe.com' in url if url else False

def is_invoice_url(url: str) -> bool:
    """Check if URL is a Stripe invoice URL"""
    return 'invoice.stripe.com' in url if url else False

def is_payment_link_url(url: str) -> bool:
    """Check if URL is a Stripe Payment Link (buy.stripe.com)"""
    return 'buy.stripe.com' in url if url else False

def decode_pk_from_url(url: str) -> dict:
    """Extract PK and CS from Stripe checkout URL hash fragment using XOR decoding"""
    result = {"pk": None, "cs": None, "site": None}
    
    try:
        cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', url)
        if cs_match:
            result["cs"] = cs_match.group(0)
        
        if '#' not in url:
            return result
        
        hash_part = url.split('#')[1]
        hash_decoded = unquote(hash_part)
        
        try:
            decoded_bytes = base64.b64decode(hash_decoded)
            xored = ''.join(chr(b ^ 5) for b in decoded_bytes)
            
            pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', xored)
            if pk_match:
                result["pk"] = pk_match.group(0)
            
            site_match = re.search(r'https?://[^\s\"\'\<\>]+', xored)
            if site_match:
                result["site"] = site_match.group(0)
        except Exception:
            pass
            
    except Exception:
        pass
    
    return result

async def get_checkout_info(url: str) -> dict:
    """Get full checkout information from Stripe URL"""
    start = time.perf_counter()
    result = {
        "url": url,
        "pk": None,
        "cs": None,
        "merchant": None,
        "price": None,
        "currency": None,
        "product": None,
        "country": None,
        "mode": None,
        "customer_name": None,
        "customer_email": None,
        "support_email": None,
        "support_phone": None,
        "cards_accepted": None,
        "success_url": None,
        "cancel_url": None,
        "init_data": None,
        "error": None,
        "time": 0
    }
    
    try:
        decoded = decode_pk_from_url(url)
        result["pk"] = decoded.get("pk")
        result["cs"] = decoded.get("cs")
        
        if result["pk"] and result["cs"]:
            s = await get_session()
            body = f"key={result['pk']}&eid=NA&browser_locale=en-US&redirect_type=url"
            
            async with s.post(
                f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init",
                headers=HEADERS,
                data=body
            ) as r:
                init_data = await r.json()
            
            if "error" not in init_data:
                result["init_data"] = init_data
                
                acc = init_data.get("account_settings", {})
                result["merchant"] = acc.get("display_name") or acc.get("business_name")
                result["support_email"] = acc.get("support_email")
                result["support_phone"] = acc.get("support_phone")
                result["country"] = acc.get("country")
                
                lig = init_data.get("line_item_group")
                inv = init_data.get("invoice")
                if lig:
                    result["price"] = lig.get("total", 0) / 100
                    result["currency"] = lig.get("currency", "").upper()
                    if lig.get("line_items"):
                        items = lig["line_items"]
                        currency = lig.get("currency", "").upper()
                        sym = get_currency_symbol(currency)
                        product_parts = []
                        for item in items:
                            qty = item.get("quantity", 1)
                            name = item.get("name", "Product")
                            amt = item.get("amount", 0) / 100
                            interval = item.get("recurring_interval")
                            if interval:
                                product_parts.append(f"{qty} × {name} (at {sym}{amt:.2f} / {interval})")
                            else:
                                product_parts.append(f"{qty} × {name} ({sym}{amt:.2f})")
                        result["product"] = ", ".join(product_parts)
                elif inv:
                    result["price"] = inv.get("total", 0) / 100
                    result["currency"] = inv.get("currency", "").upper()
                
                mode = init_data.get("mode", "")
                if mode:
                    result["mode"] = mode.upper()
                elif init_data.get("subscription"):
                    result["mode"] = "SUBSCRIPTION"
                else:
                    result["mode"] = "PAYMENT"
                
                cust = init_data.get("customer") or {}
                result["customer_name"] = cust.get("name")
                result["customer_email"] = init_data.get("customer_email") or cust.get("email")
                
                pm_types = init_data.get("payment_method_types") or []
                if pm_types:
                    cards = [t.upper() for t in pm_types if t != "card"]
                    if "card" in pm_types:
                        cards.insert(0, "CARD")
                    result["cards_accepted"] = ", ".join(cards) if cards else "CARD"
                
                result["success_url"] = init_data.get("success_url")
                result["cancel_url"] = init_data.get("cancel_url")
            else:
                result["error"] = init_data.get("error", {}).get("message", "Init failed")
        else:
            result["error"] = "Could not decode PK/CS from URL"
            
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def check_checkout_active(pk: str, cs: str) -> bool:
    """Check if checkout session is still active"""
    try:
        s = await get_session()
        body = f"key={pk}&eid=NA&browser_locale=en-US&redirect_type=url"
        async with s.post(
            f"https://api.stripe.com/v1/payment_pages/{cs}/init",
            headers=HEADERS,
            data=body,
            timeout=aiohttp.ClientTimeout(total=5)
        ) as r:
            data = await r.json()
            return "error" not in data
    except Exception:
        return False

async def get_billing_info_playwright(url: str) -> dict:
    """Get billing info using Playwright to capture SetupIntent client_secret"""
    import asyncio
    result = {
        "url": url,
        "type": "BILLING_RECOVERY", 
        "pk": None,
        "merchant": None,
        "setup_intent": None,
        "client_secret": None,
        "price": None,
        "currency": "USD",
        "mode": "SUBSCRIPTION",
        "error": None
    }
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            try:
                browser = await launch_browser(p)
            except Exception as e:
                result["error"] = f"Browser not available: {str(e)}"
                return result
            context = await browser.new_context()
            page = await context.new_page()
            
            captured_data = {"pk": None, "seti": None, "secret": None}
            
            async def on_request(request):
                url_str = request.url
                if 'elements/sessions' in url_str and 'client_secret=' in url_str:
                    import re
                    secret_match = re.search(r'client_secret=(seti_[A-Za-z0-9]+_secret_[A-Za-z0-9]+)', url_str)
                    if secret_match:
                        full_secret = secret_match.group(1)
                        captured_data["secret"] = full_secret
                        seti_match = re.search(r'(seti_[A-Za-z0-9]+)_secret', full_secret)
                        if seti_match:
                            captured_data["seti"] = seti_match.group(1)
                    
                    pk_match = re.search(r'key=(pk_(?:live|test)_[A-Za-z0-9]+)', url_str)
                    if pk_match:
                        captured_data["pk"] = pk_match.group(1)
            
            page.on('request', on_request)
            
            await page.goto(url, timeout=20000)
            await asyncio.sleep(3)
            
            if captured_data["secret"]:
                result["setup_intent"] = captured_data["seti"]
                result["client_secret"] = captured_data["secret"]
                result["pk"] = captured_data["pk"]
            
            content = await page.content()
            
            import re, html
            content = html.unescape(content)
            
            if not result["pk"]:
                pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', content)
                if pk_match:
                    result["pk"] = pk_match.group(0)
            
            branding_match = re.search(r'"business_name":"([^"]+)"', content)
            if branding_match:
                result["merchant"] = branding_match.group(1)
            
            portal_match = re.search(r'portal_session_id["\s:]+["\']?(bps_[A-Za-z0-9]+)', content)
            if portal_match:
                result["portal_session_id"] = portal_match.group(1)
            
            try:
                all_text = await page.inner_text('body')
                
                failed_match = re.search(r'FAILED PAYMENT AMOUNT\s*\$([0-9,]+\.?\d*)', all_text, re.IGNORECASE)
                if failed_match:
                    result["amount"] = f"${failed_match.group(1)}"
                    try:
                        result["price"] = float(failed_match.group(1).replace(',', ''))
                    except:
                        pass
                
                if not result.get("amount"):
                    amounts = re.findall(r'\$([0-9,]+\.[0-9]{2})', all_text)
                    if amounts:
                        result["amount"] = f"${amounts[-1]}"
                        try:
                            result["price"] = float(amounts[-1].replace(',', ''))
                        except:
                            pass
            except:
                pass
            
            await browser.close()
            
    except Exception as e:
        result["error"] = f"Playwright error: {str(e)[:100]}"
    
    return result

async def get_billing_info(url: str) -> dict:
    """Get info from Stripe billing/subscription recovery page"""
    start = time.perf_counter()
    result = {
        "url": url,
        "type": "BILLING_RECOVERY",
        "pk": None,
        "merchant": None,
        "amount": None,
        "price": None,
        "currency": None,
        "subscription": None,
        "customer_email": None,
        "mode": "SUBSCRIPTION",
        "setup_intent": None,
        "client_secret": None,
        "init_data": None,
        "error": None
    }
    
    try:
        token_match = re.search(r'/recovery/(live_[A-Za-z0-9_-]+)', url)
        recovery_token = None
        if token_match:
            recovery_token = token_match.group(1)
            result["recovery_token"] = recovery_token
        
        s = await get_session()
        async with s.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml"
        }, timeout=aiohttp.ClientTimeout(total=10)) as r:
            html_content = await r.text()
        
        pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', html_content)
        if pk_match:
            result["pk"] = pk_match.group(0)
        
        merchant_match = re.search(r'"business_name":"([^"]+)"', html_content)
        if merchant_match:
            result["merchant"] = merchant_match.group(1)
        elif '<title>' in html_content:
            title_match = re.search(r'<title>([^<]+)</title>', html_content)
            if title_match:
                title = title_match.group(1)
                if ' - ' in title:
                    result["merchant"] = title.split(' - ')[0].strip()
                else:
                    result["merchant"] = title.strip()
        
        amount_match = re.search(r'\$([0-9,]+(?:\.[0-9]{2})?)', html_content)
        if amount_match:
            result["amount"] = amount_match.group(0)
            try:
                result["price"] = float(amount_match.group(1).replace(',', ''))
            except:
                pass
        
        result["currency"] = "USD"
        
        sub_match = re.search(r'(?:Pro|Premium|Basic|Standard|Plus|Enterprise)[\s\d]*', html_content, re.IGNORECASE)
        if sub_match:
            result["subscription"] = sub_match.group(0).strip()
            result["product"] = result["subscription"]
        
        email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', html_content)
        if email_match:
            result["customer_email"] = email_match.group(0)
        
        pw_result = await get_billing_info_playwright(url)
        
        if pw_result.get("setup_intent") and pw_result.get("client_secret"):
            result["setup_intent"] = pw_result["setup_intent"]
            result["client_secret"] = pw_result["client_secret"]
            if pw_result.get("pk"):
                result["pk"] = pw_result["pk"]
            if pw_result.get("merchant") and not result["merchant"]:
                result["merchant"] = pw_result["merchant"]
            if pw_result.get("amount") and not result.get("amount"):
                result["amount"] = pw_result["amount"]
            if pw_result.get("price") and not result.get("price"):
                result["price"] = pw_result["price"]
        
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def get_invoice_info(url: str) -> dict:
    """Parse Stripe invoice URL and extract payment details using Playwright"""
    start = time.perf_counter()
    result = {
        "url": url,
        "type": "INVOICE",
        "pk": None,
        "payment_intent": None,
        "client_secret": None,
        "invoice_id": None,
        "amount": None,
        "price": None,
        "currency": None,
        "merchant": None,
        "error": None
    }
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            try:
                browser = await launch_browser(p)
            except Exception as e:
                result["error"] = f"Browser not available: {str(e)}"
                return result
            page = await browser.new_page()
            
            captured_data = {}
            
            async def handle_response(response):
                resp_url = response.url
                try:
                    if 'elements/sessions' in resp_url:
                        data = await response.json()
                        captured_data['elements'] = data
                    elif '/invoices/' in resp_url and '/hosted' in resp_url:
                        data = await response.json()
                        captured_data['invoice'] = data
                except:
                    pass
            
            page.on('response', handle_response)
            
            await page.goto(url, timeout=25000)
            await page.wait_for_timeout(4000)
            
            content = await page.content()
            
            pk_match = re.search(r'pk_(?:live|test)_[A-Za-z0-9]+', content)
            if pk_match:
                result["pk"] = pk_match.group(0)
            
            if 'invoice' in captured_data:
                inv = captured_data['invoice']
                result["invoice_id"] = inv.get('id')
                result["currency"] = (inv.get('currency') or 'usd').upper()
                
                if inv.get('payment_intent'):
                    pi = inv['payment_intent']
                    if isinstance(pi, dict):
                        result["payment_intent"] = pi.get('id')
                        result["client_secret"] = pi.get('client_secret')
                        amount_cents = pi.get('amount', 0)
                        result["price"] = amount_cents / 100
                        sym = get_currency_symbol(result["currency"])
                        result["amount"] = f"{sym}{result['price']:.2f}"
                    elif isinstance(pi, str):
                        result["payment_intent"] = pi
            
            if 'elements' in captured_data:
                elem = captured_data['elements']
                if elem.get('business_name'):
                    result["merchant"] = elem['business_name']
                if not result["pk"] and elem.get('merchant_id'):
                    result["pk"] = f"pk_live_{elem['merchant_id']}"
            
            if not result.get("merchant"):
                try:
                    body_text = await page.inner_text('body')
                    lines = body_text.split('\n')
                    for line in lines[:5]:
                        if line.strip() and len(line.strip()) < 50:
                            result["merchant"] = line.strip()
                            break
                except:
                    pass
            
            await browser.close()
            
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def get_payment_link_info(url: str) -> dict:
    """Parse Stripe Payment Link (buy.stripe.com) - uses fast Playwright to extract CS only"""
    start = time.perf_counter()
    result = {
        "url": url,
        "type": "PAYMENT_LINK",
        "pk": None,
        "cs": None,
        "payment_intent": None,
        "client_secret": None,
        "amount": None,
        "price": None,
        "currency": None,
        "merchant": None,
        "product": None,
        "mode": None,
        "init_data": None,
        "error": None
    }
    
    try:
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            try:
                browser = await launch_browser(p)
            except Exception as e:
                result["error"] = f"Browser not available: {str(e)}"
                return result
            
            context = await browser.new_context()
            page = await context.new_page()
            
            captured = {"pk": None, "cs": None}
            
            async def on_request(request):
                url_str = request.url
                
                if 'payment_pages' in url_str:
                    cs_match = re.search(r'payment_pages/(cs_(?:live|test)_[A-Za-z0-9]+)', url_str)
                    if cs_match:
                        captured["cs"] = cs_match.group(1)
                    pk_match = re.search(r'key=(pk_(?:live|test)_[A-Za-z0-9]+)', url_str)
                    if pk_match:
                        captured["pk"] = pk_match.group(1)
                
                if 'checkout/sessions' in url_str or 'payment_links' in url_str:
                    cs_match = re.search(r'(cs_(?:live|test)_[A-Za-z0-9]+)', url_str)
                    if cs_match and not captured.get("cs"):
                        captured["cs"] = cs_match.group(1)
                
                if 'stripe.com' in url_str and 'key=' in url_str:
                    pk_match = re.search(r'key=(pk_(?:live|test)_[A-Za-z0-9]+)', url_str)
                    if pk_match and not captured.get("pk"):
                        captured["pk"] = pk_match.group(1)
                
                if 'c/pay/' in url_str or '/v1/checkout' in url_str:
                    cs_match = re.search(r'(cs_(?:live|test)_[A-Za-z0-9]+)', url_str)
                    if cs_match and not captured.get("cs"):
                        captured["cs"] = cs_match.group(1)
            
            async def on_response(response):
                try:
                    resp_url = response.url
                    
                    if 'payment_pages' in resp_url:
                        data = await response.json()
                        if 'error' not in data:
                            result["init_data"] = data
                            cs_in_data = re.search(r'cs_(live|test)_[A-Za-z0-9]+', str(data))
                            if cs_in_data and not captured.get("cs"):
                                captured["cs"] = cs_in_data.group(0)
                    
                    if 'checkout/sessions' in resp_url or 'payment_links' in resp_url:
                        data = await response.json()
                        if data.get('id') and data['id'].startswith('cs_'):
                            captured["cs"] = data['id']
                        if data.get('url'):
                            cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', data['url'])
                            if cs_match:
                                captured["cs"] = cs_match.group(0)
                except:
                    pass
            
            page.on('request', on_request)
            page.on('response', on_response)
            
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(2000)
            
            try:
                page_content = await page.content()
                
                amt_match = re.search(r'\$([0-9,]+\.[0-9]{2})', page_content)
                if amt_match:
                    result["amount"] = f"${amt_match.group(1)}"
                    result["price"] = float(amt_match.group(1).replace(',', ''))
                
                merchant_patterns = [
                    r'"companyName":"([^"]+)"',
                    r'"businessName":"([^"]+)"',
                    r'"business_name":"([^"]+)"',
                    r'"display_name":"([^"]+)"',
                    r'"merchantName":"([^"]+)"',
                    r'"accountName":"([^"]+)"',
                ]
                
                for pattern in merchant_patterns:
                    merchant_match = re.search(pattern, page_content)
                    if merchant_match:
                        result["merchant"] = merchant_match.group(1)
                        break
                
                if not result.get("merchant"):
                    title = await page.title()
                    if title:
                        if ' - ' in title:
                            result["merchant"] = title.split(' - ')[0].strip()
                        elif ' | ' in title:
                            result["merchant"] = title.split(' | ')[0].strip()
                        elif title and title != "Stripe" and "checkout" not in title.lower():
                            result["merchant"] = title.strip()
            except:
                pass
            
            try:
                email_input = page.locator('input[type="email"], input[name="email"], input[id*="email"]').first
                await email_input.fill("test@example.com", timeout=3000)
                await page.wait_for_timeout(1000)
            except:
                pass
            
            for _ in range(15):
                if captured.get("cs") and captured.get("pk"):
                    break
                await page.wait_for_timeout(300)
            
            final_url = page.url
            if 'checkout.stripe.com' in final_url:
                cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', final_url)
                if cs_match and not captured.get("cs"):
                    captured["cs"] = cs_match.group(0)
                decoded = decode_pk_from_url(final_url)
                if decoded.get("pk") and not captured.get("pk"):
                    captured["pk"] = decoded["pk"]
            
            if not captured.get("cs") or not captured.get("pk"):
                content = await page.content()
                if not captured.get("pk"):
                    pk_match = re.search(r'pk_(live|test)_[A-Za-z0-9]+', content)
                    if pk_match:
                        captured["pk"] = pk_match.group(0)
                if not captured.get("cs"):
                    cs_match = re.search(r'cs_(live|test)_[A-Za-z0-9]+', content)
                    if cs_match:
                        captured["cs"] = cs_match.group(0)
            
            result["pk"] = captured.get("pk")
            result["cs"] = captured.get("cs")
            
            if result.get("cs") and result.get("pk") and not result.get("init_data"):
                try:
                    s = await get_session()
                    init_url = f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init?key={result['pk']}"
                    async with s.get(init_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            result["init_data"] = await resp.json()
                except:
                    pass
            
            if result.get("cs") and result.get("pk") and not result.get("init_data"):
                try:
                    checkout_url = f"https://checkout.stripe.com/c/pay/{result['cs']}#fidkdWxOYHwnPyd1blpxYHZxWjA0"
                    await page.goto(checkout_url, timeout=15000)
                    await page.wait_for_timeout(2000)
                except:
                    pass
            
            if result.get("cs") and result.get("pk") and not result.get("init_data"):
                try:
                    s = await get_session()
                    init_url = f"https://api.stripe.com/v1/payment_pages/{result['cs']}/init?key={result['pk']}"
                    async with s.get(init_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            result["init_data"] = await resp.json()
                except:
                    pass
            
            if result["init_data"]:
                init = result["init_data"]
                acc = init.get("account_settings", {})
                result["merchant"] = acc.get("display_name") or acc.get("business_name")
                
                lig = init.get("line_item_group")
                if lig:
                    result["price"] = lig.get("total", 0) / 100
                    result["currency"] = lig.get("currency", "usd").upper()
                    sym = get_currency_symbol(result["currency"])
                    result["amount"] = f"{sym}{result['price']:.2f}"
                    
                    if lig.get("line_items"):
                        items = lig["line_items"]
                        parts = [f"{i.get('quantity',1)}x {i.get('name','Product')}" for i in items]
                        result["product"] = ", ".join(parts)
                
                mode = init.get("mode", "")
                result["mode"] = mode.upper() if mode else "PAYMENT"
            
            if not result.get("amount"):
                try:
                    text = await page.inner_text('body')
                    amt = re.search(r'\$([0-9,]+\.[0-9]{2})', text)
                    if amt:
                        result["amount"] = f"${amt.group(1)}"
                        result["price"] = float(amt.group(1).replace(',', ''))
                except:
                    pass
            
            await browser.close()
            
    except Exception as e:
        result["error"] = str(e)
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result
