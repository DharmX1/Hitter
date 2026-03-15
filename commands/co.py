import time
import asyncio
import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode

from config import ALLOWED_GROUP, OWNER_IDS
from functions import (
    parse_cards,
    extract_checkout_url,
    get_checkout_info,
    check_checkout_active,
    get_currency_symbol,
    is_billing_url,
    get_billing_info,
    is_invoice_url,
    get_invoice_info,
    is_payment_link_url,
    get_payment_link_info,
    charge_card,
    charge_cards_batch,
    try_bypass_3ds,
    charge_cs_direct,
    charge_billing_card,
    charge_invoice_card,
    charge_payment_link_card,
    get_user_proxies,
    add_user_proxy,
    remove_user_proxy,
    get_user_proxy,
    get_proxy_info,
    check_proxies_batch,
)
from functions.fonts import to_bold, to_mono, fmt, fmt_code, header, section, divider
from functions.premium import is_premium

router = Router()

user_checkout_sessions = {}
SESSION_TIMEOUT = 300

def get_result_keyboard(user_id: int, has_session: bool = False) -> InlineKeyboardMarkup:
    """Create inline keyboard for results"""
    buttons = []
    if has_session:
        buttons.append([
            InlineKeyboardButton(text="🔄 Retry", callback_data=f"retry_{user_id}"),
            InlineKeyboardButton(text="💳 New Card", callback_data=f"newcard_{user_id}")
        ])
        buttons.append([
            InlineKeyboardButton(text="🗑 Clear Session", callback_data=f"clear_{user_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def format_card(card_str: str) -> str:
    """Auto-format card string, fixing common mistakes"""
    card_str = card_str.strip()
    card_str = re.sub(r'\s+', '', card_str)
    card_str = re.sub(r'[/:;\-\s]+', '|', card_str)
    card_str = re.sub(r'\|+', '|', card_str)
    
    parts = card_str.split('|')
    if len(parts) >= 4:
        cc = re.sub(r'\D', '', parts[0])
        mm = parts[1].zfill(2) if len(parts[1]) <= 2 else parts[1][:2]
        yy = parts[2]
        if len(yy) == 4:
            yy = yy[2:]
        cvv = parts[3]
        return f"{cc}|{mm}|{yy}|{cvv}"
    return card_str

def get_session_time_left(user_id: int) -> int:
    """Get remaining session time in seconds"""
    if user_id not in user_checkout_sessions:
        return 0
    session = user_checkout_sessions[user_id]
    elapsed = time.time() - session.get('timestamp', 0)
    remaining = SESSION_TIMEOUT - elapsed
    return max(0, int(remaining))

def make_progress_bar(current: int, total: int, width: int = 10) -> str:
    """Create a text-based progress bar"""
    if total == 0:
        return "▓" * width
    filled = int((current / total) * width)
    empty = width - filled
    bar = "▓" * filled + "░" * empty
    percent = int((current / total) * 100)
    return f"[{bar}] {current}/{total} ({percent}%)"

def check_access(msg: Message) -> bool:
    """Check if user has access to the bot"""
    if msg.chat.id == ALLOWED_GROUP:
        return True
    if msg.chat.type == "private" and msg.from_user.id in OWNER_IDS:
        return True
    return False

@router.message(Command("session"))
async def session_handler(msg: Message):
    """Show saved session status"""
    if not check_access(msg):
        return
    
    user_id = msg.from_user.id
    time_left = get_session_time_left(user_id)
    
    if time_left <= 0:
        if user_id in user_checkout_sessions:
            del user_checkout_sessions[user_id]
        await msg.answer(
            f"{divider()}\n"
            f"{header('SESSION STATUS', '📋')}\n"
            f"{divider()}\n\n"
            f"{fmt('Status', 'NO ACTIVE SESSION', '❌')}\n\n"
            f"{divider()}\n"
            f"{fmt('Tip', '/co url', '💡')}\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    session = user_checkout_sessions[user_id]
    checkout_data = session.get('data', {})
    url = session.get('url', '')
    
    mins = time_left // 60
    secs = time_left % 60
    
    currency = checkout_data.get('currency', '')
    sym = get_currency_symbol(currency)
    price = checkout_data.get('price', 0)
    price_str = f"{sym}{price:.2f} {currency}" if price else "N/A"
    
    await msg.answer(
        f"{divider()}\n"
        f"{header('SESSION STATUS', '📋')}\n"
        f"{divider()}\n\n"
        f"{fmt('Status', 'ACTIVE', '✅')}\n"
        f"{fmt('Expires', f'{mins}m {secs}s', '⏳')}\n"
        f"{fmt('Merchant', checkout_data.get('merchant', 'N/A'), '🏪')}\n"
        f"{fmt('Amount', price_str, '💰')}\n\n"
        f"[🔗] {to_bold('URL')} ⌁ <a href=\"{url}\">{to_mono('OPEN CHECKOUT')}</a>\n\n"
        f"{divider()}\n"
        f"{fmt('Tip', '/co card', '💡')}\n"
        f"{divider()}",
        parse_mode=ParseMode.HTML,
        reply_markup=get_result_keyboard(user_id, True)
    )

@router.callback_query(F.data.startswith("retry_"))
async def retry_callback(callback: CallbackQuery):
    """Handle retry button"""
    user_id = int(callback.data.split("_")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("This button is not for you!", show_alert=True)
        return
    
    time_left = get_session_time_left(user_id)
    if time_left <= 0:
        await callback.answer("Session expired! Send a new checkout URL.", show_alert=True)
        return
    
    await callback.answer("Send your card to retry!", show_alert=False)
    await callback.message.answer(
        f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>🔄 𝗥𝗘𝗧𝗥𝗬 𝗠𝗢𝗗𝗘 🔄</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>💳 𝗦𝗲𝗻𝗱</b>  ➜  <code>/co card|mm|yy|cvv</code>\n"
        f"<b>⏳ 𝗧𝗶𝗺𝗲</b>  ➜  <code>{time_left}s left</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━</b>",
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("newcard_"))
async def newcard_callback(callback: CallbackQuery):
    """Handle new card button"""
    user_id = int(callback.data.split("_")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("This button is not for you!", show_alert=True)
        return
    
    time_left = get_session_time_left(user_id)
    if time_left <= 0:
        await callback.answer("Session expired! Send a new checkout URL.", show_alert=True)
        return
    
    await callback.answer("Send a new card!", show_alert=False)
    await callback.message.answer(
        f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n"
        f"<b>💳 𝗡𝗘𝗪 𝗖𝗔𝗥𝗗 💳</b>\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━</b>\n\n"
        f"<b>💳 𝗦𝗲𝗻𝗱</b>  ➜  <code>/co card|mm|yy|cvv</code>\n"
        f"<b>📝 𝗙𝗼𝗿𝗺𝗮𝘁</b>  ➜  <code>4111111111111111|12|25|123</code>\n"
        f"<b>⏳ 𝗧𝗶𝗺𝗲</b>  ➜  <code>{time_left}s left</code>\n\n"
        f"<b>━━━━━━━━━━━━━━━━━━━━</b>",
        parse_mode=ParseMode.HTML
    )

@router.callback_query(F.data.startswith("clear_"))
async def clear_callback(callback: CallbackQuery):
    """Handle clear session button"""
    user_id = int(callback.data.split("_")[1])
    
    if callback.from_user.id != user_id:
        await callback.answer("This button is not for you!", show_alert=True)
        return
    
    if user_id in user_checkout_sessions:
        del user_checkout_sessions[user_id]
    
    await callback.answer("Session cleared!", show_alert=True)
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except:
        pass

@router.message(Command("addproxy"))
async def addproxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Join', '@fn_network_reborn', '📢')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    user_proxies = get_user_proxies(user_id)
    
    if len(args) < 2:
        if user_proxies:
            proxy_list = "\n".join([f"    • <code>{p}</code>" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n    • <code>... and {len(user_proxies) - 10} more</code>"
        else:
            proxy_list = "    • <code>None</code>"
        
        await msg.answer(
            f"{divider()}\n"
            f"{header('PROXY MANAGER', '🔒')}\n"
            f"{divider()}\n\n"
            f"{fmt('Your Proxies', str(len(user_proxies)), '📋')}\n{proxy_list}\n\n"
            f"{section('⚙️ COMMANDS')}\n\n"
            f"{fmt('Add', '/addproxy proxy', '➕')}\n"
            f"{fmt('Remove', '/removeproxy proxy', '➖')}\n"
            f"{fmt('Remove All', '/removeproxy all', '🗑')}\n"
            f"{fmt('Check', '/proxy check', '✅')}\n\n"
            f"{section('📝 FORMATS')}\n\n"
            f"• <code>host:port:user:pass</code>\n"
            f"• <code>user:pass@host:port</code>\n"
            f"• <code>host:port</code>\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_input = args[1].strip()
    proxies_to_add = [p.strip() for p in proxy_input.split('\n') if p.strip()]
    
    if not proxies_to_add:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'NO VALID PROXIES PROVIDED', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    checking_msg = await msg.answer(
        f"{divider()}\n"
        f"{header('CHECKING PROXIES', '⏳')}\n"
        f"{divider()}\n\n"
        f"{fmt('Total', str(len(proxies_to_add)), '📋')}\n"
        f"{fmt('Threads', '10', '⚡')}\n\n"
        f"{divider()}",
        parse_mode=ParseMode.HTML
    )
    
    results = await check_proxies_batch(proxies_to_add, max_threads=10)
    
    alive_proxies = []
    dead_proxies = []
    
    for r in results:
        if r["status"] == "alive":
            alive_proxies.append(r)
            add_user_proxy(user_id, r["proxy"])
        else:
            dead_proxies.append(r)
    
    response = f"{divider()}\n"
    response += f"{header('PROXY CHECK COMPLETE', '✅')}\n"
    response += f"{divider()}\n\n"
    response += f"{fmt('Alive', f'{len(alive_proxies)}/{len(proxies_to_add)}', '✅')}\n"
    response += f"{fmt('Dead', f'{len(dead_proxies)}/{len(proxies_to_add)}', '❌')}\n\n"
    
    if alive_proxies:
        response += f"{section('📋 ADDED')}\n\n"
        for p in alive_proxies[:5]:
            response += f"• <code>{p['proxy']}</code> ({p['response_time']})\n"
        if len(alive_proxies) > 5:
            response += f"• <code>... and {len(alive_proxies) - 5} more</code>\n"
        response += f"\n{divider()}"
    
    await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

@router.message(Command("removeproxy"))
async def removeproxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Join', '@fn_network_reborn', '📢')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    
    if len(args) < 2:
        await msg.answer(
            f"{divider()}\n"
            f"{header('REMOVE PROXY', '🗑')}\n"
            f"{divider()}\n\n"
            f"{fmt('Usage', '/removeproxy proxy', '📝')}\n"
            f"{fmt('All', '/removeproxy all', '🗑')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_input = args[1].strip()
    
    if proxy_input.lower() == "all":
        user_proxies = get_user_proxies(user_id)
        count = len(user_proxies)
        remove_user_proxy(user_id, "all")
        await msg.answer(
            f"{divider()}\n"
            f"{header('ALL PROXIES REMOVED', '✅')}\n"
            f"{divider()}\n\n"
            f"{fmt('Removed', f'{count} PROXIES', '🗑')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    if remove_user_proxy(user_id, proxy_input):
        await msg.answer(
            f"{divider()}\n"
            f"{header('PROXY REMOVED', '✅')}\n"
            f"{divider()}\n\n"
            f"{fmt('Proxy', proxy_input, '🌐')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
    else:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'PROXY NOT FOUND', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )

@router.message(Command("proxy"))
async def proxy_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Join', '@fn_network_reborn', '📢')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split(maxsplit=1)
    user_id = msg.from_user.id
    
    if len(args) < 2 or args[1].strip().lower() != "check":
        user_proxies = get_user_proxies(user_id)
        if user_proxies:
            proxy_list = "\n".join([f"    • <code>{p}</code>" for p in user_proxies[:10]])
            if len(user_proxies) > 10:
                proxy_list += f"\n    • <code>... and {len(user_proxies) - 10} more</code>"
        else:
            proxy_list = "    • <code>None</code>"
        
        await msg.answer(
            f"{divider()}\n"
            f"{header('PROXY MANAGER', '🔒')}\n"
            f"{divider()}\n\n"
            f"{fmt('Your Proxies', str(len(user_proxies)), '📋')}\n{proxy_list}\n\n"
            f"{fmt('Check All', '/proxy check', '✅')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    user_proxies = get_user_proxies(user_id)
    
    if not user_proxies:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'NO PROXIES TO CHECK', '📝')}\n"
            f"{fmt('Add', '/addproxy proxy', '➕')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    checking_msg = await msg.answer(
        f"{divider()}\n"
        f"{header('CHECKING PROXIES', '⏳')}\n"
        f"{divider()}\n\n"
        f"{fmt('Total', str(len(user_proxies)), '📋')}\n"
        f"{fmt('Threads', '10', '⚡')}\n\n"
        f"{divider()}",
        parse_mode=ParseMode.HTML
    )
    
    results = await check_proxies_batch(user_proxies, max_threads=10)
    
    alive = [r for r in results if r["status"] == "alive"]
    dead = [r for r in results if r["status"] == "dead"]
    
    response = f"{divider()}\n"
    response += f"{header('PROXY CHECK RESULTS', '📊')}\n"
    response += f"{divider()}\n\n"
    response += f"{fmt('Alive', f'{len(alive)}/{len(user_proxies)}', '✅')}\n"
    response += f"{fmt('Dead', f'{len(dead)}/{len(user_proxies)}', '❌')}\n\n"
    
    if alive:
        response += f"{section('✅ ALIVE')}\n\n"
        for p in alive[:5]:
            ip_display = p['external_ip'] or 'N/A'
            response += f"• <code>{p['proxy']}</code>\n  IP: {ip_display} | {p['response_time']}\n"
        if len(alive) > 5:
            response += f"• <code>... and {len(alive) - 5} more</code>\n"
        response += "\n"
    
    if dead:
        response += f"{section('❌ DEAD')}\n\n"
        for p in dead[:3]:
            error = p.get('error', 'Unknown')
            response += f"• <code>{p['proxy']}</code> ({error})\n"
        if len(dead) > 3:
            response += f"• <code>... and {len(dead) - 3} more</code>\n"
    
    response += f"\n{divider()}"
    
    await checking_msg.edit_text(response, parse_mode=ParseMode.HTML)

@router.message(Command("co"))
async def co_handler(msg: Message):
    if not check_access(msg):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Join', '@fn_network_reborn', '📢')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    start_time = time.perf_counter()
    user_id = msg.from_user.id
    
    is_in_group = msg.chat.id == ALLOWED_GROUP
    if not is_in_group and user_id not in OWNER_IDS and not is_premium(user_id):
        await msg.answer(
            f"{divider()}\n"
            f"{header('PREMIUM REQUIRED', '💎')}\n"
            f"{divider()}\n\n"
            f"{fmt('Status', 'NOT PREMIUM', '❌')}\n"
            f"{fmt('Action', '/redeem KEY', '🔑')}\n\n"
            f"{divider()}\n"
            f"{fmt('Get Key', 'CONTACT OWNER', '📞')}\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    text = msg.text or ""
    lines = text.strip().split('\n')
    first_line_args = lines[0].split(maxsplit=3)
    
    cards = []
    bypass_3ds = True
    url = None
    use_saved_session = False
    saved_session_type = None
    
    if len(first_line_args) >= 2:
        potential_url = extract_checkout_url(first_line_args[1])
        if potential_url:
            url = potential_url
        else:
            formatted = format_card(first_line_args[1])
            cards = parse_cards(formatted)
            if cards and user_id in user_checkout_sessions:
                session = user_checkout_sessions[user_id]
                if time.time() - session.get('timestamp', 0) < SESSION_TIMEOUT:
                    url = session.get('url')
                    use_saved_session = True
                    saved_session_type = 'payment_link' if session.get('is_payment_link') else 'billing' if session.get('is_billing') else 'invoice' if session.get('is_invoice') else 'checkout'
                else:
                    del user_checkout_sessions[user_id]
            elif not cards:
                url = first_line_args[1].strip()
    
    if len(first_line_args) > 2:
        formatted = format_card(first_line_args[2])
        cards.extend(parse_cards(formatted))
    
    if len(lines) > 1:
        remaining_lines = [format_card(line) for line in lines[1:]]
        remaining_text = '\n'.join(remaining_lines)
        cards.extend(parse_cards(remaining_text))
    
    if msg.reply_to_message and msg.reply_to_message.document:
        doc = msg.reply_to_message.document
        if doc.file_name and doc.file_name.endswith('.txt'):
            try:
                file = await msg.bot.get_file(doc.file_id)
                file_content = await msg.bot.download_file(file.file_path)
                text_content = file_content.read().decode('utf-8')
                cards = parse_cards(text_content)
            except Exception as e:
                await msg.answer(
                    "<blockquote><code>𝗘𝗿𝗿𝗼𝗿 ❌</code></blockquote>\n\n"
                    f"<blockquote>「❃」 𝗗𝗲𝘁𝗮𝗶𝗹 : <code>Failed to read file: {str(e)}</code></blockquote>",
                    parse_mode=ParseMode.HTML
                )
                return
    
    if not url:
        await msg.answer(
            "<blockquote><code>𝗡𝗼 𝗖𝗵𝗲𝗰𝗸𝗼𝘂𝘁 ❌</code></blockquote>\n\n"
            "<blockquote>「❃」 𝗦𝘁𝗮𝘁𝘂𝘀 : <code>No checkout URL found</code>\n"
            "「❃」 𝗨𝘀𝗮𝗴𝗲 : <code>/co url cc|mm|yy|cvv</code></blockquote>",
            parse_mode=ParseMode.HTML
        )
        return
    
    user_proxy = get_user_proxy(user_id)
    
    if not user_proxy:
        await msg.answer(
            f"{divider()}\n"
            f"{header('NO PROXY', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Status', 'YOU MUST SET A PROXY FIRST', '📝')}\n"
            f"{fmt('Action', '/addproxy host:port:user:pass', '➕')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_info = await get_proxy_info(user_proxy)
    
    if proxy_info["status"] == "dead":
        await msg.answer(
            f"{divider()}\n"
            f"{header('PROXY DEAD', '💀')}\n"
            f"{divider()}\n\n"
            f"{fmt('Status', 'NOT RESPONDING', '❌')}\n"
            f"{fmt('Action', '/proxy or /removeproxy', '🔧')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    proxy_display = f"LIVE ✅ | {proxy_info['ip_obfuscated']}"
    
    if is_billing_url(url):
        processing_msg = await msg.answer(
            f"{divider()}\n"
            f"{header('PROCESSING', '⏳')}\n"
            f"{divider()}\n\n"
            f"{fmt('Type', 'BILLING RECOVERY', '💳')}\n"
            f"{fmt('Proxy', proxy_display, '🌐')}\n"
            f"{fmt('Status', 'PARSING...', '📡')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        
        billing_data = await get_billing_info(url)
        
        if billing_data.get("error"):
            await processing_msg.edit_text(
                f"{divider()}\n"
                f"{header('ERROR', '❌')}\n"
                f"{divider()}\n\n"
                f"{fmt('Detail', billing_data['error'], '📝')}\n\n"
                f"{divider()}",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_checkout_sessions[user_id] = {'url': url, 'data': billing_data, 'timestamp': time.time(), 'is_billing': True}
        
        if not cards:
            total_time = round(time.perf_counter() - start_time, 2)
            
            response = f"{divider()}\n"
            response += f"{header('STRIPE BILLING', '💳')}\n"
            response += f"{divider()}\n\n"
            
            response += f"{fmt('Type', billing_data.get('type', 'SUBSCRIPTION RECOVERY'), '📋')}\n"
            response += f"{fmt('Merchant', billing_data.get('merchant') or 'N/A', '🏪')}\n"
            response += f"{fmt('Amount', billing_data.get('amount') or 'N/A', '💰')}\n"
            response += f"{fmt('Subscription', billing_data.get('subscription') or 'N/A', '🔄')}\n"
            response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
            
            if billing_data.get('pk'):
                response += f"{section('🔑 API DATA')}\n\n"
                response += f"{fmt('PK', billing_data['pk'][:30] + '...', '🔑')}\n"
                if billing_data.get('recovery_token'):
                    response += f"{fmt('Token', billing_data['recovery_token'][:20] + '...', '🎫')}\n"
                response += "\n"
            
            response += f"{divider()}\n"
            response += f"{fmt('Time', f'{total_time}s', '⏱')}\n"
            response += f"{divider()}"
            
            await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
            return
        
        amount_str = billing_data.get('amount') or 'N/A'
        
        await processing_msg.edit_text(
            f"{divider()}\n"
            f"{header(f'CHARGING {amount_str}', '⚡')}\n"
            f"{divider()}\n\n"
            f"{fmt('Proxy', proxy_display, '🌐')}\n"
            f"{fmt('Cards', str(len(cards)), '💳')}\n"
            f"{fmt('Type', 'BILLING RECOVERY', '📋')}\n"
            f"{fmt('Status', 'CHARGING...', '📡')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        
        results = []
        charged_card = None
        
        for card in cards:
            result = await charge_billing_card(card, billing_data, user_proxy)
            results.append(result)
            if result['status'] == 'CHARGED':
                charged_card = result
                break
        
        total_time = round(time.perf_counter() - start_time, 2)
        
        response = f"{divider()}\n"
        live_card = any(r['status'] == 'LIVE' for r in results)
        if charged_card:
            response += f"{header('CHARGED', '✅')}\n"
        elif live_card:
            response += f"{header('CARD LIVE', '💚')}\n"
        else:
            response += f"{header('BILLING RESULT', '💳')}\n"
        response += f"{divider()}\n\n"
        
        response += f"{fmt('Amount', amount_str, '💰')}\n"
        response += f"{fmt('Merchant', billing_data.get('merchant') or 'N/A', '🏪')}\n"
        response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
        
        if len(results) == 1:
            r = results[0]
            status_emoji = "✅" if r['status'] == 'CHARGED' else "💚" if r['status'] == 'LIVE' else "❌" if r['status'] == 'DECLINED' else "🔐" if '3DS' in r['status'] else "⚠️"
            
            r_time = r['time']
            response += f"{section('💳 CARD DETAILS')}\n\n"
            response += f"{fmt_code('Card', r['card'], '💳')}\n"
            response += f"{fmt('Status', r['status'], status_emoji)}\n"
            response += f"{fmt('Response', r['response'], '📝')}\n"
            response += f"{fmt('Time', f'{r_time}s', '⏱')}\n\n"
        else:
            charged = sum(1 for r in results if r['status'] == 'CHARGED')
            declined = sum(1 for r in results if r['status'] == 'DECLINED')
            three_ds = sum(1 for r in results if '3DS' in r['status'])
            errors = sum(1 for r in results if r['status'] in ['ERROR', 'FAILED', 'TIMEOUT'])
            
            response += f"{section('📊 SUMMARY')}\n\n"
            response += f"{fmt('Total', f'{len(results)} CARDS', '📋')}\n"
            response += f"{fmt('Charged', str(charged), '✅')}\n"
            response += f"{fmt('Declined', str(declined), '❌')}\n"
            response += f"{fmt('3DS', str(three_ds), '🔐')}\n"
            response += f"{fmt('Errors', str(errors), '⚠️')}\n\n"
        
        response += f"{divider()}\n"
        response += f"{fmt('Command', '/co', '⚙️')}\n"
        response += f"{fmt('Total Time', f'{total_time}s', '⏱')}\n"
        response += f"{divider()}"
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
        return
    
    if is_invoice_url(url):
        processing_msg = await msg.answer(
            f"{divider()}\n"
            f"{header('PROCESSING', '⏳')}\n"
            f"{divider()}\n\n"
            f"{fmt('Type', 'INVOICE', '🧾')}\n"
            f"{fmt('Proxy', proxy_display, '🌐')}\n"
            f"{fmt('Status', 'PARSING...', '📡')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        
        invoice_data = await get_invoice_info(url)
        
        if invoice_data.get("error"):
            await processing_msg.edit_text(
                f"{divider()}\n"
                f"{header('ERROR', '❌')}\n"
                f"{divider()}\n\n"
                f"{fmt('Detail', invoice_data['error'], '📝')}\n\n"
                f"{divider()}",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_checkout_sessions[user_id] = {'url': url, 'data': invoice_data, 'timestamp': time.time(), 'is_invoice': True}
        
        if not cards:
            total_time = round(time.perf_counter() - start_time, 2)
            
            response = f"{divider()}\n"
            response += f"{header('STRIPE INVOICE', '🧾')}\n"
            response += f"{divider()}\n\n"
            
            response += f"{fmt('Amount', invoice_data.get('amount') or 'N/A', '💰')}\n"
            response += f"{fmt('Merchant', invoice_data.get('merchant') or 'N/A', '🏪')}\n"
            response += f"{fmt('Invoice', invoice_data.get('invoice_id') or 'N/A', '🧾')}\n"
            response += f"{fmt('Currency', invoice_data.get('currency') or 'N/A', '💵')}\n"
            response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
            
            if invoice_data.get('pk'):
                response += f"{section('🔑 API DATA')}\n\n"
                response += f"{fmt('PK', invoice_data['pk'][:30] + '...', '🔑')}\n"
                if invoice_data.get('payment_intent'):
                    response += f"{fmt('PI', invoice_data['payment_intent'][:25] + '...', '💳')}\n"
                response += "\n"
            
            response += f"{divider()}\n"
            response += f"{fmt('Time', f'{total_time}s', '⏱')}\n"
            response += f"{divider()}"
            
            await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
            return
        
        amount_str = invoice_data.get('amount') or 'N/A'
        
        await processing_msg.edit_text(
            f"{divider()}\n"
            f"{header(f'CHARGING {amount_str}', '⚡')}\n"
            f"{divider()}\n\n"
            f"{fmt('Proxy', proxy_display, '🌐')}\n"
            f"{fmt('Cards', str(len(cards)), '💳')}\n"
            f"{fmt('Type', 'INVOICE', '🧾')}\n"
            f"{fmt('Status', 'CHARGING...', '📡')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        
        results = []
        charged_card = None
        
        for card in cards:
            result = await charge_invoice_card(card, invoice_data, user_proxy)
            results.append(result)
            if result['status'] == 'CHARGED':
                charged_card = result
                break
        
        total_time = round(time.perf_counter() - start_time, 2)
        
        response = f"{divider()}\n"
        live_card = any(r['status'] == 'LIVE' for r in results)
        if charged_card:
            response += f"{header('CHARGED', '✅')}\n"
        elif live_card:
            response += f"{header('CARD LIVE', '💚')}\n"
        else:
            response += f"{header('INVOICE RESULT', '🧾')}\n"
        response += f"{divider()}\n\n"
        
        response += f"{fmt('Amount', amount_str, '💰')}\n"
        response += f"{fmt('Merchant', invoice_data.get('merchant') or 'N/A', '🏪')}\n"
        response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
        
        if len(results) == 1:
            r = results[0]
            status_emoji = "✅" if r['status'] == 'CHARGED' else "❌" if r['status'] == 'DECLINED' else "🔐" if r['status'] == '3DS' else "⚠️"
            time_str = f"{r['time']}s"
            response += f"{section('💳 CARD DETAILS')}\n\n"
            response += f"{fmt_code('Card', r['card'], '💳')}\n"
            response += f"{fmt('Status', r['status'], status_emoji)}\n"
            response += f"{fmt('Response', r['response'], '📝')}\n"
            response += f"{fmt('Time', time_str, '⏱')}\n\n"
        else:
            charged = sum(1 for r in results if r['status'] == 'CHARGED')
            declined = sum(1 for r in results if r['status'] == 'DECLINED')
            three_ds = sum(1 for r in results if r['status'] == '3DS')
            errors = len(results) - charged - declined - three_ds
            
            response += f"{section('📊 SUMMARY')}\n\n"
            response += f"{fmt('Total', f'{len(results)} CARDS', '📋')}\n"
            response += f"{fmt('Charged', str(charged), '✅')}\n"
            response += f"{fmt('Declined', str(declined), '❌')}\n"
            response += f"{fmt('3DS', str(three_ds), '🔐')}\n"
            response += f"{fmt('Errors', str(errors), '⚠️')}\n\n"
        
        response += f"{divider()}\n"
        response += f"{fmt('Command', '/co', '⚙️')}\n"
        response += f"{fmt('Total Time', f'{total_time}s', '⏱')}\n"
        response += f"{divider()}"
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
        return
    
    if is_payment_link_url(url) or saved_session_type == 'payment_link':
        processing_msg = await msg.answer(
            f"{divider()}\n"
            f"{header('PROCESSING', '⏳')}\n"
            f"{divider()}\n\n"
            f"{fmt('Type', 'PAYMENT LINK', '🔗')}\n"
            f"{fmt('Proxy', proxy_display, '🌐')}\n"
            f"{fmt('Status', 'USING SAVED SESSION...' if use_saved_session else 'PARSING...', '📡')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        
        if use_saved_session and user_id in user_checkout_sessions:
            link_data = user_checkout_sessions[user_id].get('data')
            if not link_data:
                link_data = await get_payment_link_info(url)
        else:
            link_data = await get_payment_link_info(url)
        
        if link_data.get("error"):
            if user_id in user_checkout_sessions:
                del user_checkout_sessions[user_id]
            await processing_msg.edit_text(
                f"{divider()}\n"
                f"{header('ERROR', '❌')}\n"
                f"{divider()}\n\n"
                f"{fmt('Detail', link_data['error'], '📝')}\n\n"
                f"{divider()}",
                parse_mode=ParseMode.HTML
            )
            return
        
        user_checkout_sessions[user_id] = {'url': url, 'data': link_data, 'timestamp': time.time(), 'is_payment_link': True}
        
        if not cards:
            total_time = round(time.perf_counter() - start_time, 2)
            
            response = f"{divider()}\n"
            response += f"{header('STRIPE PAYMENT LINK', '🔗')}\n"
            response += f"{divider()}\n\n"
            
            response += f"{fmt('Amount', link_data.get('amount') or 'N/A', '💰')}\n"
            response += f"{fmt('Merchant', link_data.get('merchant') or 'N/A', '🏪')}\n"
            response += f"{fmt('Product', link_data.get('product') or 'N/A', '📦')}\n"
            response += f"{fmt('Mode', link_data.get('mode') or 'N/A', '📋')}\n"
            response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
            
            if link_data.get('pk'):
                response += f"{section('🔑 API DATA')}\n\n"
                response += f"{fmt('PK', link_data['pk'][:30] + '...', '🔑')}\n"
                if link_data.get('cs'):
                    response += f"{fmt('CS', link_data['cs'][:25] + '...', '🎫')}\n"
                if link_data.get('payment_intent'):
                    response += f"{fmt('PI', link_data['payment_intent'][:25] + '...', '💳')}\n"
                response += "\n"
            
            response += f"{divider()}\n"
            response += f"{fmt('Time', f'{total_time}s', '⏱')}\n"
            response += f"{divider()}"
            
            await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
            return
        
        amount_str = link_data.get('amount') or 'N/A'
        
        await processing_msg.edit_text(
            f"{divider()}\n"
            f"{header(f'CHARGING {amount_str}', '⚡')}\n"
            f"{divider()}\n\n"
            f"{fmt('Proxy', proxy_display, '🌐')}\n"
            f"{fmt('Cards', str(len(cards)), '💳')}\n"
            f"{fmt('Type', 'PAYMENT LINK', '🔗')}\n"
            f"{fmt('Status', 'CHARGING...', '📡')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        
        results = []
        charged_card = None
        
        pk = link_data.get('pk')
        cs = link_data.get('cs')
        client_secret = link_data.get('client_secret')
        pi = link_data.get('payment_intent')
        
        for card in cards:
            if cs and link_data.get('init_data'):
                result = await charge_card(card, link_data, user_proxy)
            elif client_secret and pi:
                result = await charge_payment_link_card(card, pk, pi, client_secret, user_proxy)
            elif cs and pk:
                result = await charge_cs_direct(card, cs, pk, user_proxy)
            else:
                result = {
                    "card": f"{card['cc'][:6]}******{card['cc'][-4:]}|{card['month']}|{card['year']}|{card['cvv']}",
                    "status": "DECLINED",
                    "message": "NO CS OR SECRET FOUND",
                    "time": 0
                }
            results.append(result)
            if result['status'] == 'CHARGED':
                charged_card = result
                break
        
        total_time = round(time.perf_counter() - start_time, 2)
        
        response = f"{divider()}\n"
        live_card = any(r['status'] == 'LIVE' for r in results)
        if charged_card:
            response += f"{header('CHARGED', '✅')}\n"
        elif live_card:
            response += f"{header('CARD LIVE', '💚')}\n"
        else:
            response += f"{header('PAYMENT LINK RESULT', '🔗')}\n"
        response += f"{divider()}\n\n"
        
        response += f"{fmt('Amount', amount_str, '💰')}\n"
        response += f"{fmt('Merchant', link_data.get('merchant') or 'N/A', '🏪')}\n"
        response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
        
        if len(results) == 1:
            r = results[0]
            card_status = r['status']
            status_emoji = "✅" if card_status == 'CHARGED' else "❌" if card_status == 'DECLINED' else "🔐" if card_status == '3DS' else "⚠️"
            time_str = f"{r['time']}s"
            response += f"{section('💳 CARD DETAILS')}\n\n"
            response += f"{fmt_code('Card', r['card'], '💳')}\n"
            response += f"{fmt('Status', f'{status_emoji} {card_status}', '📊')}\n"
            msg_text = r.get('message') or r.get('response') or 'No response'
            msg_short = msg_text[:60] + '...' if len(msg_text) > 60 else msg_text
            response += f"{fmt('Response', msg_short, '📝')}\n"
            response += f"{fmt('Time', time_str, '⏱')}\n\n"
        else:
            charged = sum(1 for r in results if r['status'] == 'CHARGED')
            declined = sum(1 for r in results if r['status'] == 'DECLINED')
            three_ds = sum(1 for r in results if r['status'] == '3DS')
            errors = len(results) - charged - declined - three_ds
            
            response += f"{section('📊 SUMMARY')}\n\n"
            response += f"{fmt('Total', f'{len(results)} CARDS', '📋')}\n"
            response += f"{fmt('Charged', str(charged), '✅')}\n"
            response += f"{fmt('Declined', str(declined), '❌')}\n"
            response += f"{fmt('3DS', str(three_ds), '🔐')}\n"
            response += f"{fmt('Errors', str(errors), '⚠️')}\n\n"
        
        response += f"{divider()}\n"
        response += f"{fmt('Command', '/co', '⚙️')}\n"
        response += f"{fmt('Total Time', f'{total_time}s', '⏱')}\n"
        response += f"{divider()}"
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
        return
    
    processing_msg = await msg.answer(
        f"{divider()}\n"
        f"{header('PROCESSING', '⏳')}\n"
        f"{divider()}\n\n"
        f"{fmt('Proxy', proxy_display, '🌐')}\n"
        f"{fmt('Status', 'PARSING CHECKOUT...', '📡')}\n\n"
        f"{divider()}",
        parse_mode=ParseMode.HTML
    )
    
    if use_saved_session and user_id in user_checkout_sessions:
        checkout_data = user_checkout_sessions[user_id].get('data')
        if not checkout_data:
            checkout_data = await get_checkout_info(url)
    else:
        checkout_data = await get_checkout_info(url)
    
    if checkout_data.get("error"):
        if user_id in user_checkout_sessions:
            del user_checkout_sessions[user_id]
        await processing_msg.edit_text(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', checkout_data['error'], '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    user_checkout_sessions[user_id] = {'url': url, 'data': checkout_data, 'timestamp': time.time()}
    
    if not cards:
        currency = checkout_data.get('currency', '')
        sym = get_currency_symbol(currency)
        price_str = f"{sym}{checkout_data['price']:.2f} {currency}" if checkout_data['price'] else "N/A"
        total_time = round(time.perf_counter() - start_time, 2)
        
        response = f"{divider()}\n"
        response += f"{header('STRIPE CHECKOUT', '🛒')}\n"
        response += f"{divider()}\n\n"
        
        response += f"{fmt('Amount', price_str, '💰')}\n"
        response += f"{fmt('Status', 'SUCCESS', '✅')}\n"
        response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
        
        response += f"{section('🏪 MERCHANT')}\n\n"
        response += f"{fmt('Name', checkout_data['merchant'] or 'N/A', '🏪')}\n"
        response += f"{fmt('Product', checkout_data['product'] or 'N/A', '📦')}\n"
        response += f"{fmt('Country', checkout_data['country'] or 'N/A', '🌍')}\n"
        response += f"{fmt('Mode', checkout_data['mode'] or 'N/A', '⚙️')}\n\n"
        
        if checkout_data['customer_name'] or checkout_data['customer_email']:
            response += f"{section('👤 CUSTOMER')}\n\n"
            response += f"{fmt('Name', checkout_data['customer_name'] or 'N/A', '👤')}\n"
            response += f"{fmt('Email', checkout_data['customer_email'] or 'N/A', '📧')}\n\n"
        
        if checkout_data['support_email'] or checkout_data['support_phone']:
            response += f"{section('📞 SUPPORT')}\n\n"
            response += f"{fmt('Email', checkout_data['support_email'] or 'N/A', '📧')}\n"
            response += f"{fmt('Phone', checkout_data['support_phone'] or 'N/A', '📞')}\n\n"
        
        if checkout_data['cards_accepted']:
            response += f"{fmt('Cards', checkout_data['cards_accepted'], '💳')}\n\n"
        
        response += f"{divider()}\n"
        response += f"{fmt('CS', checkout_data['cs'][:30] + '...', '🔑')}\n"
        response += f"{fmt('PK', checkout_data['pk'][:30] + '...', '🔑')}\n"
        response += f"{fmt('Time', f'{total_time}s', '⏱')}\n"
        response += f"{divider()}"
        
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML)
        return
    
    currency = checkout_data.get('currency', '')
    sym = get_currency_symbol(currency)
    price_str = f"{sym}{checkout_data['price']:.2f} {currency}" if checkout_data['price'] else "N/A"
    
    concurrency = min(3, len(cards)) if len(cards) > 1 else 1
    
    await processing_msg.edit_text(
        f"{divider()}\n"
        f"{header(f'CHARGING {price_str}', '⚡')}\n"
        f"{divider()}\n\n"
        f"{fmt('Proxy', proxy_display, '🌐')}\n"
        f"{fmt('Cards', str(len(cards)), '💳')}\n"
        f"{fmt('Concurrency', f'{concurrency}x', '⚡')}\n"
        f"{fmt('Status', 'STARTING...', '📡')}\n\n"
        f"{divider()}",
        parse_mode=ParseMode.HTML
    )
    
    if len(cards) == 1:
        result = await charge_card(cards[0], checkout_data, user_proxy, bypass_3ds)
        results = [result]
        charged_card = result if result['status'] == 'CHARGED' else None
        cancelled = False
    else:
        results = []
        charged_card = None
        cancelled = False
        last_update = 0
        
        async def update_progress(current, total, current_result=None):
            nonlocal last_update, results, charged_card
            now = time.time()
            if current_result:
                results.append(current_result)
                if current_result['status'] == 'CHARGED':
                    charged_card = current_result
            
            if now - last_update >= 1.0 or current == total or charged_card:
                last_update = now
                progress = make_progress_bar(current, total)
                status = "Charging..." if not charged_card else "Charged! ✅"
                try:
                    await processing_msg.edit_text(
                        f"{divider()}\n"
                        f"{header(f'CHARGING {price_str}', '⚡')}\n"
                        f"{divider()}\n\n"
                        f"{fmt('Proxy', proxy_display, '🌐')}\n"
                        f"{fmt('Progress', progress, '📊')}\n"
                        f"{fmt('Status', status.upper(), '📡')}\n\n"
                        f"{divider()}",
                        parse_mode=ParseMode.HTML
                    )
                except:
                    pass
        
        batch_results = await charge_cards_batch(
            cards,
            checkout_data,
            user_proxy,
            bypass_3ds,
            concurrency=concurrency,
            stop_on_charge=True,
            progress_callback=update_progress
        )
        
        if not results:
            results = batch_results
        
        if not charged_card:
            charged_card = next((r for r in results if r['status'] == 'CHARGED'), None)
        cancelled = any(r['status'] == 'SKIPPED' for r in results)
    
    total_time = round(time.perf_counter() - start_time, 2)
    
    if charged_card or any(r['status'] in ['EXPIRED', 'USED'] for r in results):
        if user_id in user_checkout_sessions:
            del user_checkout_sessions[user_id]
    
    if cancelled:
        charged = sum(1 for r in results if r['status'] == 'CHARGED')
        declined = sum(1 for r in results if r['status'] == 'DECLINED')
        three_ds = sum(1 for r in results if r['status'] in ['3DS', '3DS SKIP', '3DS SOFT', '3DS SDK'])
        
        response = f"{divider()}\n"
        response += f"{header('CHECKOUT CANCELLED', '⛔')}\n"
        response += f"{divider()}\n\n"
        
        response += f"{fmt('Proxy', proxy_display, '🌐')}\n"
        response += f"{fmt('Merchant', checkout_data['merchant'] or 'N/A', '🏪')}\n"
        response += f"{fmt('Reason', 'CHECKOUT NO LONGER ACTIVE', '❌')}\n\n"
        
        response += f"{section('📊 SUMMARY')}\n\n"
        response += f"{fmt('Tried', f'{len(results)}/{len(cards)} CARDS', '📋')}\n"
        response += f"{fmt('Charged', str(charged), '✅')}\n"
        response += f"{fmt('Declined', str(declined), '❌')}\n"
        response += f"{fmt('3DS', str(three_ds), '🔐')}\n\n"
        
        response += f"{divider()}\n"
        response += f"{fmt('Total Time', f'{total_time}s', '⏱')}\n"
        response += f"{divider()}"
        
        has_session = user_id in user_checkout_sessions and get_session_time_left(user_id) > 0
        await processing_msg.edit_text(response, parse_mode=ParseMode.HTML, reply_markup=get_result_keyboard(user_id, has_session))
        return
    
    response = f"{divider()}\n"
    response += f"{header('STRIPE CHARGE', '⚡')}\n"
    response += f"{divider()}\n\n"
    
    response += f"{fmt('Amount', price_str, '💰')}\n"
    response += f"{fmt('Merchant', checkout_data['merchant'] or 'N/A', '🏪')}\n"
    response += f"{fmt('Product', checkout_data['product'] or 'N/A', '📦')}\n"
    response += f"{fmt('Proxy', proxy_display, '🌐')}\n\n"
    
    if charged_card:
        response += f"{section('💳 CARD DETAILS')}\n\n"
        response += f"{fmt_code('Card', charged_card['card'], '💳')}\n"
        response += f"{fmt('Status', 'CHARGED', '✅')}\n"
        response += f"{fmt('Response', charged_card['response'], '📝')}\n"
        card_time = charged_card['time']
        response += f"{fmt('Time', f'{card_time}s', '⏱')}\n\n"
        
        if checkout_data.get('success_url'):
            response += f"[🔗] {to_bold('Success')} ⌁ <a href=\"{checkout_data['success_url']}\">{to_mono('OPEN PAGE')}</a>\n"
        
        response += f"[🛒] {to_bold('Checkout')} ⌁ <a href=\"{url}\">{to_mono('OPEN LINK')}</a>\n\n"
        
        if len(results) > 1:
            response += f"{fmt('Tried', f'{len(results)}/{len(cards)} CARDS', '📊')}\n\n"
    elif len(results) == 1:
        r = results[0]
        if r['status'] == '3DS':
            status_emoji = "🔐"
            status_text = "3DS REQUIRED"
        elif r['status'] in ['3DS SKIP', '3DS SOFT', '3DS SDK']:
            status_emoji = "🔓"
            status_text = r['status']
        elif r['status'] == 'DECLINED':
            status_emoji = "❌"
            status_text = "DECLINED"
        elif r['status'] in ['EXPIRED', 'USED']:
            status_emoji = "⏳"
            status_text = r['status']
        elif r['status'] == 'NOT SUPPORTED':
            status_emoji = "🚫"
            status_text = "NOT SUPPORTED"
        elif r['status'] == 'PROCESSING':
            status_emoji = "⏳"
            status_text = "PROCESSING"
        elif r['status'] == 'TIMEOUT':
            status_emoji = "⏰"
            status_text = "TIMEOUT"
        else:
            status_emoji = "⚠️"
            status_text = r['status']
        
        response += f"{section('💳 CARD DETAILS')}\n\n"
        response += f"{fmt_code('Card', r['card'], '💳')}\n"
        response += f"{fmt('Status', status_text, status_emoji)}\n"
        response += f"{fmt('Response', r['response'], '📝')}\n"
        r_time = r['time']
        response += f"{fmt('Time', f'{r_time}s', '⏱')}\n\n"
    else:
        charged = sum(1 for r in results if r['status'] == 'CHARGED')
        declined = sum(1 for r in results if r['status'] == 'DECLINED')
        three_ds = sum(1 for r in results if r['status'] in ['3DS', '3DS SKIP', '3DS SOFT', '3DS SDK', '3DS REQUIRED'])
        errors = sum(1 for r in results if r['status'] in ['ERROR', 'FAILED', 'TIMEOUT', 'SKIPPED'])
        
        response += f"{section('📊 SUMMARY')}\n\n"
        response += f"{fmt('Total', f'{len(results)} CARDS', '📋')}\n"
        response += f"{fmt('Charged', str(charged), '✅')}\n"
        response += f"{fmt('Declined', str(declined), '❌')}\n"
        response += f"{fmt('3DS', str(three_ds), '🔐')}\n"
        response += f"{fmt('Errors', str(errors), '⚠️')}\n\n"
    
    response += f"{divider()}\n"
    response += f"{fmt('Command', '/co', '⚙️')}\n"
    response += f"{fmt('Total Time', f'{total_time}s', '⏱')}\n"
    response += f"{divider()}"
    
    has_session = user_id in user_checkout_sessions and get_session_time_left(user_id) > 0
    keyboard = get_result_keyboard(user_id, has_session)
    
    await processing_msg.edit_text(response, parse_mode=ParseMode.HTML, reply_markup=keyboard)
