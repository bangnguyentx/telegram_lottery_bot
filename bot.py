# bot.py — Main khởi động QLottery_bot

import os
import asyncio
from telegram.ext import ApplicationBuilder

from handlers import register_user_handlers, register_group_handlers
from utils import start_lottery_cycle

# ==============================
# ⚙️ 1. Cấu hình BOT
# ==============================

# Token Telegram Bot (bắt buộc)
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu biến môi trường BOT_TOKEN!")

# Cổng chạy (Render hoặc Localhost)
PORT = int(os.getenv("PORT", 10000))

# ==============================
# 🚀 2. Khởi tạo App
# ==============================

app = ApplicationBuilder().token(TOKEN).build()

# ==============================
# 🧠 3. Đăng ký Handlers
# ==============================

register_user_handlers(app)
register_group_handlers(app)

# ==============================
# 🌀 4. Vòng quay xổ số nền
# ==============================

async def background_lottery_cycle():
    """Chạy vòng xổ số cho tất cả group mỗi 60s"""
    while True:
        try:
            await start_lottery_cycle(app)
        except Exception as e:
            print(f"[❌ Lỗi vòng xổ số]: {e}")
        await asyncio.sleep(1)  # tránh vòng lặp siêu tốc khi lỗi

# ==============================
# 🏁 5. Main
# ==============================

async def main():
    print("✅ QLottery Bot đang khởi động...")
    # Chạy background xổ số song song
    asyncio.create_task(background_lottery_cycle())
    # Chạy bot polling
    await app.run_polling(drop_pending_updates=True, allowed_updates=telegram.constants.Update.ALL_TYPES)

if __name__ == "__main__":
    import telegram  # import ở đây để tránh lỗi vòng tròn
    asyncio.run(main())
