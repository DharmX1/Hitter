from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from config import ALLOWED_GROUP, OWNER_IDS
from functions.fonts import to_bold, to_mono, fmt, header, section, divider

router = Router()

def check_access(msg: Message) -> bool:
    """Check if user has access to the bot"""
    if msg.chat.id == ALLOWED_GROUP:
        return True
    if msg.chat.type == "private" and msg.from_user.id in OWNER_IDS:
        return True
    return False

@router.message(Command("start"))
async def start_handler(msg: Message):
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
    
    welcome = (
        f"{divider()}\n"
        f"{header('FN AUTO HITTER', '⚡')}\n"
        f"{divider()}\n\n"
        
        f"{section('🔗 SUPPORTED URL')}\n\n"
        f"{fmt('Checkout', 'checkout.stripe.com', '🛒')}\n"
        f"{fmt('Billing', 'billing.stripe.com', '💳')}\n"
        f"{fmt('Invoice', 'invoice.stripe.com', '📄')}\n"
        f"{fmt('Payment Link', 'buy.stripe.com', '🔗')}\n\n"
        
        f"{section('🛒 CHECKOUT')}\n\n"
        f"[📋] {to_bold('Parse')} ⌁ /co url\n"
        f"[💳] {to_bold('Charge')} ⌁ /co url card\n"
        f"[🔄] {to_bold('Retry')} ⌁ /co card\n"
        f"[📋] {to_bold('Session')} ⌁ /session\n\n"
        
        f"{section('🌐 PROXY')}\n\n"
        f"[➕] {to_bold('Add')} ⌁ /addproxy\n"
        f"[➖] {to_bold('Remove')} ⌁ /removeproxy\n"
        f"[✅] {to_bold('Check')} ⌁ /proxy check\n\n"
        
        f"{section('💎 PREMIUM')}\n\n"
        f"[🔑] {to_bold('Status')} ⌁ /key\n"
        f"[💎] {to_bold('Redeem')} ⌁ /redeem key\n\n"
        
        f"{divider()}\n"
        f"{fmt('Contact', '@ThorinX1', '📞')}\n"
        f"{divider()}"
    )
    await msg.answer(welcome, parse_mode=ParseMode.HTML)

@router.message(Command("help"))
async def help_handler(msg: Message):
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
    
    help_text = (
        f"{divider()}\n"
        f"{header('COMMANDS', '📋')}\n"
        f"{divider()}\n\n"
        
        f"{section('⚡ MAIN')}\n\n"
        f"{fmt('/start', 'WELCOME', '🏠')}\n"
        f"{fmt('/help', 'COMMANDS', '❓')}\n"
        f"{fmt('/co url', 'PARSE CHECKOUT', '📋')}\n"
        f"{fmt('/co url card', 'CHARGE CARD', '💳')}\n"
        f"{fmt('/co card', 'RETRY WITH SAVED', '🔄')}\n"
        f"{fmt('/session', 'VIEW SESSION', '📋')}\n\n"
        
        f"{section('🌐 PROXY')}\n\n"
        f"{fmt('/addproxy', 'ADD PROXY', '➕')}\n"
        f"{fmt('/removeproxy', 'REMOVE PROXY', '➖')}\n"
        f"{fmt('/proxy check', 'CHECK PROXIES', '✅')}\n\n"
        
        f"{section('💎 PREMIUM')}\n\n"
        f"{fmt('/key', 'CHECK STATUS', '🔑')}\n"
        f"{fmt('/redeem', 'REDEEM KEY', '💎')}\n\n"
        
        f"{section('💳 FORMAT')}\n\n"
        f"{fmt('Format', 'cc|mm|yy|cvv', '📝')}\n"
        f"{fmt('Example', '4242424242424242|12|25|123', '📋')}\n\n"
        
        f"{divider()}"
    )
    await msg.answer(help_text, parse_mode=ParseMode.HTML)
