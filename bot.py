import asyncio
import logging
import time
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()

from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ErrorEvent, Message, TelegramObject
from typing import Callable, Dict, Any, Awaitable
from config import BOT_TOKEN
from commands import router
from functions import close_session, close_charge_session

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    """Rate limiting middleware to prevent abuse"""
    
    def __init__(self, rate_limit: float = 1.0, burst_limit: int = 5):
        self.rate_limit = rate_limit
        self.burst_limit = burst_limit
        self.user_requests: Dict[int, list] = defaultdict(list)
        self._cleanup_task = None
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else 0
            current_time = time.time()
            
            self.user_requests[user_id] = [
                t for t in self.user_requests[user_id] 
                if current_time - t < self.rate_limit * self.burst_limit
            ]
            
            if len(self.user_requests[user_id]) >= self.burst_limit:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                await event.answer(
                    "⚠️ <b>Too many requests!</b>\n\nPlease wait a moment before trying again.",
                    parse_mode="HTML"
                )
                return None
            
            self.user_requests[user_id].append(current_time)
        
        return await handler(event, data)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
dp.message.middleware(ThrottlingMiddleware(rate_limit=1.0, burst_limit=10))
dp.include_router(router)

@dp.error()
async def global_error_handler(event: ErrorEvent):
    """Global error handler to catch all unhandled exceptions"""
    logger.error(f"Unhandled error: {event.exception}", exc_info=event.exception)
    
    update = event.update
    if update and update.message:
        try:
            await update.message.answer(
                "⚠️ <b>An error occurred while processing your request.</b>\n\n"
                "Please try again in a moment. If the problem persists, contact support.",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to send error message: {e}")
    elif update and update.callback_query:
        try:
            await update.callback_query.answer(
                "An error occurred. Please try again.",
                show_alert=True
            )
        except Exception as e:
            logger.error(f"Failed to answer callback: {e}")

async def main():
    logger.info("Starting bot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook deleted, starting polling...")
        await dp.start_polling(bot, skip_updates=True, drop_pending_updates=True)
    finally:
        logger.info("Shutting down...")
        await close_session()
        await close_charge_session()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
