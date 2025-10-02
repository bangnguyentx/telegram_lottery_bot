import random
import string
from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime

from db import (
    add_balance,
    create_code,
    insert_round,
    get_top10_users,
)

# 🧑‍💼 DANH SÁCH ADMIN (thay ID thật của bạn vào)
ADMIN_IDS = [7760459637]  # ← Bạn có thể thêm nhiều ID vào đây

# ==============================
# 🧰 Kiểm tra quyền admin
# ==============================
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# ==============================
# 💬 Gửi cảnh báo crash bot
# ==============================
async def notify_admins_on_crash(context: ContextTypes.DEFAULT_TYPE, error_text: str):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🚨 <b>Bot bị crash!</b>\n\n<code>{error_text}</code>",
                parse_mode="HTML"
            )
        except Exception:
            pass

# ==============================
# 💰 /congtien <user_id> <số tiền>
# ==============================
async def add_money_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await update.message.reply_text("❌ Bạn không có quyền dùng lệnh này.")

    args = context.args
    if len(args) != 2:
        return await update.message.reply_text("❗ Cú pháp: /congtien <user_id> <số tiền>")

    try:
        target_id = int(args[0])
        amount = int(args[1])
    except ValueError:
        return await update.message.reply_text("❌ ID hoặc số tiền không hợp lệ.")

    add_balance(target_id, amount)
    await update.message.reply_text(f"✅ Đã cộng {amount:,}₫ cho ID {target_id}.")

# ==============================
# 🧾 /code <số tiền> <vòng cược>
# ==============================
async def create_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await update.message.reply_text("❌ Bạn không có quyền dùng lệnh này.")

    args = context.args
    if len(args) != 2:
        return await update.message.reply_text("❗ Cú pháp: /code <số tiền> <vòng cược>")

    try:
        amount = int(args[0])
        bet_turns = int(args[1])
    except ValueError:
        return await update.message.reply_text("❌ Số tiền hoặc vòng cược không hợp lệ.")

    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    create_code(code, amount, bet_turns)
    await update.message.reply_text(f"✅ Mã code đã tạo:\n<code>{code}</code>\n💰 Giá trị: {amount:,}₫\n🔁 Vòng cược: {bet_turns}",
                                    parse_mode="HTML")

# ==============================
# 🏆 /topnap — Top 10 người nhiều tiền nhất
# ==============================
async def topnap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    top_users = get_top10_users()
    if not top_users:
        return await update.message.reply_text("❌ Chưa có dữ liệu.")

    lines = []
    for rank, (uid, username, balance) in enumerate(top_users, start=1):
        uname = f"@{username}" if username else f"ID {uid}"
        lines.append(f"{rank}. {uname} — {balance:,}₫")

    text = "🏆 <b>Top 10 người nạp nhiều nhất</b>\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="HTML")

# ==============================
# 📝 /nho, /lon, /chan, /le — Chỉnh kết quả phiên
# ==============================
async def force_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return await update.message.reply_text("❌ Bạn không có quyền.")

    cmd = update.message.text.strip().lower()
    if cmd == "/nho":
        result = "NHO"
    elif cmd == "/lon":
        result = "LON"
    elif cmd == "/chan":
        result = "CHAN"
    elif cmd == "/le":
        result = "LE"
    else:
        return

    # Lấy period hiện tại
    now = datetime.utcnow()
    period_id = int(now.timestamp() // 60)  # mỗi phút = 1 phiên

    insert_round(period_id, result)
    await update.message.reply_text(f"✅ Đã chỉnh kết quả phiên {period_id} thành: {result}")
