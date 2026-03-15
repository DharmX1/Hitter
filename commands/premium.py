from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode
from config import OWNER_IDS, ALLOWED_GROUP
from functions.premium import (
    generate_key,
    get_all_keys,
    get_unused_keys,
    delete_key,
    redeem_key,
    is_premium,
    get_premium_status,
    revoke_premium,
    get_all_premium_users
)
from functions.fonts import to_bold, to_mono, fmt, fmt_code, header, section, divider

router = Router()

def check_access(msg: Message) -> bool:
    """Check if user has access to the bot"""
    if msg.chat.id == ALLOWED_GROUP:
        return True
    if msg.chat.type == "private" and msg.from_user.id in OWNER_IDS:
        return True
    return False

def is_owner(user_id: int) -> bool:
    """Check if user is an owner"""
    return user_id in OWNER_IDS

@router.message(Command("genkey"))
async def genkey_handler(msg: Message):
    """Generate a premium key (owner only)"""
    if not check_access(msg):
        return
    
    user_id = msg.from_user.id
    if not is_owner(user_id):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Error', 'OWNER ONLY COMMAND', '❌')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split()
    
    if len(args) < 2:
        await msg.answer(
            f"{divider()}\n"
            f"{header('GENERATE KEY', '🔑')}\n"
            f"{divider()}\n\n"
            f"{section('📋 USAGE')}\n\n"
            f"{fmt('1 Day', '/genkey 1d', '📅')}\n"
            f"{fmt('7 Days', '/genkey 7d', '📅')}\n"
            f"{fmt('30 Days', '/genkey 30d', '📅')}\n"
            f"{fmt('Custom', '/genkey 14d', '📅')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    duration_str = args[1].lower().strip()
    
    if duration_str.endswith('d'):
        try:
            days = int(duration_str[:-1])
            if days < 1 or days > 365:
                raise ValueError()
        except:
            await msg.answer(
                f"{divider()}\n"
                f"{header('ERROR', '❌')}\n"
                f"{divider()}\n\n"
                f"{fmt('Detail', 'INVALID DURATION (1-365 DAYS)', '📝')}\n\n"
                f"{divider()}",
                parse_mode=ParseMode.HTML
            )
            return
    else:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'USE FORMAT: 1d, 7d, 30d', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    key = generate_key(days)
    
    await msg.answer(
        f"{divider()}\n"
        f"{header('KEY GENERATED', '🔑')}\n"
        f"{divider()}\n\n"
        f"{fmt_code('Key', key, '🔑')}\n"
        f"{fmt('Duration', f'{days} DAYS', '📅')}\n\n"
        f"{divider()}\n"
        f"{fmt('Redeem', '/redeem KEY', '💎')}\n"
        f"{divider()}",
        parse_mode=ParseMode.HTML
    )

@router.message(Command("redeem"))
async def redeem_handler(msg: Message):
    """Redeem a premium key"""
    if not check_access(msg):
        return
    
    args = msg.text.split()
    user_id = msg.from_user.id
    
    if len(args) < 2:
        await msg.answer(
            f"{divider()}\n"
            f"{header('REDEEM KEY', '💎')}\n"
            f"{divider()}\n\n"
            f"{fmt('Usage', '/redeem FN-XXXX', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    key = args[1].strip().upper()
    
    success, message = redeem_key(user_id, key)
    
    if success:
        status = get_premium_status(user_id)
        await msg.answer(
            f"{divider()}\n"
            f"{header('KEY REDEEMED', '✅')}\n"
            f"{divider()}\n\n"
            f"{fmt('Added', message.upper(), '⏰')}\n"
            f"{fmt('Expires In', status['display'].upper(), '📅')}\n\n"
            f"{divider()}\n"
            f"{fmt('Enjoy', 'PREMIUM ACCESS', '💎')}\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
    else:
        await msg.answer(
            f"{divider()}\n"
            f"{header('REDEEM FAILED', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Error', message.upper(), '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )

@router.message(Command("key"))
async def key_status_handler(msg: Message):
    """Check premium status"""
    if not check_access(msg):
        return
    
    user_id = msg.from_user.id
    status = get_premium_status(user_id)
    
    if status:
        await msg.answer(
            f"{divider()}\n"
            f"{header('PREMIUM STATUS', '💎')}\n"
            f"{divider()}\n\n"
            f"{fmt('Status', 'ACTIVE', '✅')}\n"
            f"{fmt('Expires In', status['display'].upper(), '⏰')}\n"
            f"{fmt('Days Left', str(status['days_left']), '📅')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
    else:
        await msg.answer(
            f"{divider()}\n"
            f"{header('PREMIUM STATUS', '💎')}\n"
            f"{divider()}\n\n"
            f"{fmt('Status', 'NOT ACTIVE', '❌')}\n\n"
            f"{divider()}\n"
            f"{fmt('Get Key', 'CONTACT OWNER', '🔑')}\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )

@router.message(Command("revoke"))
async def revoke_handler(msg: Message):
    """Revoke a user's premium (owner only)"""
    if not check_access(msg):
        return
    
    user_id = msg.from_user.id
    if not is_owner(user_id):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Error', 'OWNER ONLY COMMAND', '❌')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split()
    
    if len(args) < 2:
        await msg.answer(
            f"{divider()}\n"
            f"{header('REVOKE PREMIUM', '🗑')}\n"
            f"{divider()}\n\n"
            f"{fmt('Usage', '/revoke user_id', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    try:
        target_user_id = int(args[1])
    except:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'INVALID USER ID', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    if revoke_premium(target_user_id):
        await msg.answer(
            f"{divider()}\n"
            f"{header('PREMIUM REVOKED', '✅')}\n"
            f"{divider()}\n\n"
            f"{fmt('User ID', str(target_user_id), '👤')}\n"
            f"{fmt('Status', 'REMOVED', '🗑')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
    else:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'USER NOT FOUND OR NOT PREMIUM', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )

@router.message(Command("keys"))
async def keys_list_handler(msg: Message):
    """List all keys and premium users (owner only)"""
    if not check_access(msg):
        return
    
    user_id = msg.from_user.id
    if not is_owner(user_id):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Error', 'OWNER ONLY COMMAND', '❌')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    unused_keys = get_unused_keys()
    premium_users = get_all_premium_users()
    
    response = f"{divider()}\n"
    response += f"{header('KEY MANAGEMENT', '🔑')}\n"
    response += f"{divider()}\n\n"
    
    response += f"{section('🔑 UNUSED KEYS')}\n\n"
    if unused_keys:
        for key, info in list(unused_keys.items())[:10]:
            response += f"• <code>{key}</code> ({info['duration_days']}d)\n"
        if len(unused_keys) > 10:
            response += f"• ... and {len(unused_keys) - 10} more\n"
    else:
        response += f"{fmt('Status', 'NO UNUSED KEYS', '📋')}\n"
    response += "\n"
    
    response += f"{section('👑 PREMIUM USERS')}\n\n"
    if premium_users:
        for user in premium_users[:10]:
            response += f"• <code>{user['user_id']}</code> ({user['time_left']})\n"
        if len(premium_users) > 10:
            response += f"• ... and {len(premium_users) - 10} more\n"
    else:
        response += f"{fmt('Status', 'NO PREMIUM USERS', '📋')}\n"
    response += "\n"
    
    response += f"{divider()}\n"
    response += f"{fmt('Generate', '/genkey 7d', '➕')}\n"
    response += f"{fmt('Revoke', '/revoke user_id', '🗑')}\n"
    response += f"{divider()}"
    
    await msg.answer(response, parse_mode=ParseMode.HTML)

@router.message(Command("delkey"))
async def delkey_handler(msg: Message):
    """Delete an unused key (owner only)"""
    if not check_access(msg):
        return
    
    user_id = msg.from_user.id
    if not is_owner(user_id):
        await msg.answer(
            f"{divider()}\n"
            f"{header('ACCESS DENIED', '🚫')}\n"
            f"{divider()}\n\n"
            f"{fmt('Error', 'OWNER ONLY COMMAND', '❌')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    args = msg.text.split()
    
    if len(args) < 2:
        await msg.answer(
            f"{divider()}\n"
            f"{header('DELETE KEY', '🗑')}\n"
            f"{divider()}\n\n"
            f"{fmt('Usage', '/delkey FN-XXXX', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
        return
    
    key = args[1].strip().upper()
    
    if delete_key(key):
        await msg.answer(
            f"{divider()}\n"
            f"{header('KEY DELETED', '✅')}\n"
            f"{divider()}\n\n"
            f"{fmt_code('Key', key, '🗑')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
    else:
        await msg.answer(
            f"{divider()}\n"
            f"{header('ERROR', '❌')}\n"
            f"{divider()}\n\n"
            f"{fmt('Detail', 'KEY NOT FOUND', '📝')}\n\n"
            f"{divider()}",
            parse_mode=ParseMode.HTML
        )
