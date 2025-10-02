# bot.py — Khởi động bot QLottery

import os
import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
)
from handlers import register_group_handlers, register_user_handlers
from db import init_db

# ==============================
# 📝 LOGGING
# ==============================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================
# 🔐 ENV & CONFIG
# ==============================
TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", "10000"))  # Render yêu cầu PORT có sẵn

if not TOKEN:
    raise RuntimeError("❌ Thiếu BOT_TOKEN trong biến môi trường!")

# ==============================
# 🏁 COMMANDS CƠ BẢN
# ==============================

async def start(update, context):
    user = update.effective_user
    await update.message.reply_text(
        f"🎉 Xin chào {user.first_name}!\n"
        f"🤖 Đây là bot xổ số nhóm. Gõ /help để xem hướng dẫn cược."
    )

async def help_command(update, context):
    await update.message.reply_text(
        "📌 *Hướng dẫn cược*\n"
        "/N1000 → cược Nhỏ 1.000₫\n"
        "/L1000 → cược Lớn 1.000₫\n"
        "/C1000 → cược Chẵn 1.000₫\n"
        "/Le1000 → cược Lẻ 1.000₫\n"
        "/S123456 1000 → cược 6 số 123456 với 1.000₫\n\n"
        "💰 Tiền thưởng tự động tính sau mỗi phiên."
    )

# ==============================
# 🏗️ MAIN
# ==============================

def main():
    logger.info("🚀 Khởi tạo cơ sở dữ liệu...")
    init_db()

    logger.info("🤖 Đang khởi chạy bot...")
    application = ApplicationBuilder().token(TOKEN).build()

    # Lệnh cơ bản
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))

    # Đăng ký xử lý group & user
    register_group_handlers(application)
    register_user_handlers(application)

    # Khi chạy trên Render hoặc local
    if os.getenv("RENDER") == "true":
        # 🔸 Render yêu cầu bot chạy webhook thay vì polling
        logger.info(f"🌐 Đang chạy webhook trên cổng {PORT}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
        )
    else:
        # 🌀 Local development
        logger.info("🧪 Đang chạy local polling mode")
        application.run_polling()

if __name__ == "__main__":
    main()
