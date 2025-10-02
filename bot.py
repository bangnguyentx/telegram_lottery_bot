# bot.py — Main khởi động QLottery_bot
import os, asyncio
import telegram
from telegram.ext import ApplicationBuilder
from handlers import register_user_handlers, register_group_handlers
from utils import start_lottery_cycle
from db import init_db

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu biến môi trường BOT_TOKEN!")

PORT = int(os.getenv("PORT", 10000))

init_db()  # đảm bảo DB có sẵn

app = ApplicationBuilder().token(TOKEN).build()

register_user_handlers(app)
register_group_handlers(app)

async def background_lottery_cycle():
    while True:
        try:
            await start_lottery_cycle(app)
        except Exception as e:
            print(f"[❌ Lỗi vòng xổ số]: {e}")
        await asyncio.sleep(1)

async def main():
    print("✅ QLottery Bot đang khởi động...")
    asyncio.create_task(background_lottery_cycle())
    await app.run_polling(drop_pending_updates=True, allowed_updates=telegram.constants.Update.ALL_TYPES)

if __name__ == "__main__":
    asyncio.run(main())
