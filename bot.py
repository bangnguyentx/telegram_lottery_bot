import logging
import asyncio
from telegram.ext import ApplicationBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from handlers import register_user_handlers, register_group_handlers
from admin import register_admin_handlers
from db import init_db
from utils import start_lottery_cycle

# --- CẤU HÌNH ---
TOKEN = "7482983031:AAHp-DGJMGr0AWoOEk75eV02glQNlPn0wKI"
ADMIN_IDS = [7760459637]   # Admin chính
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- MAIN ---
async def main():
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()

    # Đăng ký handler
    register_user_handlers(app)
    register_group_handlers(app)
    register_admin_handlers(app, ADMIN_IDS)

    # Scheduler 60s quay số
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(start_lottery_cycle, "interval", seconds=60, args=[app])
    scheduler.start()

    logger.info("QLottery_bot started ✅")
    await app.run_polling()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
from admin import (
    add_money_handler,
    create_code_handler,
    topnap_handler,
    force_result_handler
)

app.add_handler(CommandHandler("congtien", add_money_handler))
app.add_handler(CommandHandler("code", create_code_handler))
app.add_handler(CommandHandler("topnap", topnap_handler))
app.add_handler(CommandHandler(["nho", "lon", "chan", "le"], force_result_handler))

