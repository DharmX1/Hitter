import asyncio
import logging
import shutil
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

def find_playwright_chromium():
    """Find Playwright's installed chromium in cache directories"""
    import os
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
    import os
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

async def capture_screenshot(url: str, timeout: int = 15000) -> bytes | None:
    """Capture a screenshot of the given URL and return as bytes"""
    playwright = None
    browser = None
    context = None
    page = None
    try:
        logger.info(f"Starting screenshot capture for: {url}")
        playwright = await async_playwright().start()
        browser = await launch_browser(playwright)
        
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            device_scale_factor=1.5
        )
        
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=timeout)
            
            await asyncio.sleep(2)
            
            for _ in range(5):
                content = await page.content()
                if 'skeleton' not in content.lower() and len(content) > 5000:
                    break
                await asyncio.sleep(1)
            
            await asyncio.sleep(1)
            
            screenshot = await page.screenshot(full_page=False)
            logger.info(f"Screenshot captured successfully, size: {len(screenshot)} bytes")
            return screenshot
        except Exception as e:
            logger.warning(f"Page load error: {e}, trying screenshot anyway")
            try:
                await asyncio.sleep(3)
                screenshot = await page.screenshot(full_page=False)
                return screenshot
            except Exception as e2:
                logger.error(f"Screenshot failed: {e2}")
                return None
    except Exception as e:
        logger.error(f"Browser launch error: {e}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass

async def capture_checkout_result(url: str, card: dict) -> bytes | None:
    """Fill checkout form with card details, submit, and capture the result page"""
    playwright = None
    browser = None
    context = None
    page = None
    try:
        logger.info(f"Starting checkout result capture for: {url}")
        playwright = await async_playwright().start()
        browser = await launch_browser(playwright)
        
        context = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            device_scale_factor=1.5
        )
        
        page = await context.new_page()
        
        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            cc = card.get('cc', '')
            month = card.get('month', '')
            year = card.get('year', '')
            cvv = card.get('cvv', '')
            
            full_year = year if len(year) == 4 else f"20{year}"
            
            card_input = page.locator('input[name="cardNumber"], input[placeholder*="1234"], input[id*="cardNumber"]').first
            if await card_input.count() > 0:
                await card_input.fill(cc)
                await asyncio.sleep(0.3)
            
            expiry_input = page.locator('input[name="cardExpiry"], input[placeholder*="MM"], input[id*="expiry"]').first
            if await expiry_input.count() > 0:
                await expiry_input.fill(f"{month}/{year}")
                await asyncio.sleep(0.3)
            
            cvc_input = page.locator('input[name="cardCvc"], input[placeholder*="CVC"], input[id*="cvc"]').first
            if await cvc_input.count() > 0:
                await cvc_input.fill(cvv)
                await asyncio.sleep(0.3)
            
            name_input = page.locator('input[name="billingName"], input[placeholder*="name on card"], input[id*="name"]').first
            if await name_input.count() > 0:
                await name_input.fill("John Smith")
                await asyncio.sleep(0.3)
            
            country_select = page.locator('select[name*="country"], select[id*="country"]').first
            if await country_select.count() > 0:
                try:
                    await country_select.select_option("US")
                    await asyncio.sleep(0.3)
                except:
                    pass
            
            address_input = page.locator('input[name*="addressLine1"], input[placeholder*="Address"]').first
            if await address_input.count() > 0:
                await address_input.fill("476 West White Mountain Blvd")
                await asyncio.sleep(0.3)
            
            submit_button = page.locator('button[type="submit"], .SubmitButton, button:has-text("Pay"), button:has-text("Subscribe")').first
            if await submit_button.count() > 0:
                await submit_button.click()
                logger.info("Submit button clicked, waiting for result...")
                
                await asyncio.sleep(8)
                
                for _ in range(10):
                    content = await page.content()
                    if any(x in content.lower() for x in ['declined', 'error', 'failed', 'success', 'thank', 'complete', 'confirmed']):
                        break
                    await asyncio.sleep(1)
                
                await asyncio.sleep(2)
            
            screenshot = await page.screenshot(full_page=False)
            logger.info(f"Checkout result screenshot captured, size: {len(screenshot)} bytes")
            return screenshot
            
        except Exception as e:
            logger.warning(f"Form fill/submit error: {e}, taking screenshot anyway")
            try:
                await asyncio.sleep(2)
                screenshot = await page.screenshot(full_page=False)
                return screenshot
            except Exception as e2:
                logger.error(f"Screenshot failed: {e2}")
                return None
                
    except Exception as e:
        logger.error(f"Browser launch error: {e}")
        return None
    finally:
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if playwright:
            try:
                await playwright.stop()
            except Exception:
                pass

async def capture_success_screenshot(success_url: str) -> bytes | None:
    """Capture screenshot of success page after payment"""
    if not success_url:
        logger.warning("No success URL provided")
        return None
    logger.info(f"Capturing success screenshot: {success_url}")
    return await capture_screenshot(success_url, timeout=20000)
