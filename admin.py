# admin.py — Lệnh quản trị cho QLottery_bot

from telegram import Update
from telegram.ext import ContextTypes
from db import get_user, update_balance, insert_history, get_all_groups
from utils import get_current_round_id
from datetime import datetime

# 🧑‍💻 Danh sách ID admin được phép dùng lệnh quản trị
ADMINS = [123456789]   # 👈 Thay ID admin thật của bạn vào đây

# ----- 📌 CHECK QUYỀN -----

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

# ----- 🧾 XEM ROUND CODE -----

async def cmd_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    if not is_admin(user_id):
        return

    round_id = get_current_round_id(chat_id)
    code = round_id.split("_")[-1]
    await update.message.reply_text(f"🔑 Mã round hiện tại: `{code}`", parse_mode="Markdown")

# ----- 💰 CỘNG TIỀN -----

async def cmd_addmoney(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Sai cú pháp. Dùng: `/addmoney <user_id> <số_tiền>`", parse_mode="Markdown")
        return

    user = get_user(target_id)
    if not user:
        await update.message.reply_text("⚠️ Không tìm thấy user.")
        return

    new_balance = user["balance"] + amount
    update_balance(target_id, new_balance)
    await update.message.reply_text(f"✅ Đã cộng {amount:.0f} cho user `{target_id}`.\n💰 Số dư mới: {new_balance:.0f}", parse_mode="Markdown")

# ----- 💸 XEM SỐ DƯ -----

async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Dùng: `/balance <user_id>`")
        return

    user = get_user(target_id)
    if not user:
        await update.message.reply_text("⚠️ Không tìm thấy user.")
        return

    await update.message.reply_text(f"👤 `{target_id}` — 💰 Số dư: {user['balance']:.0f}", parse_mode="Markdown")

# ----- 📝 XEM LỊCH SỬ GẦN NHẤT -----

import sqlite3
DB_PATH = "lottery.db"

def get_recent_history(limit=10):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    try:
        n = int(context.args[0]) if context.args else 10
    except ValueError:
        n = 10

    history = get_recent_history(n)
    if not history:
        await update.message.reply_text("📭 Không có lịch sử.")
        return

    lines = []
    for h in history:
        t = datetime.fromisoformat(h["created_at"]).strftime("%H:%M:%S")
        lines.append(f"{t} | {h['result_number']} | {h['size']}/{h['parity']}")

    msg = "📜 Lịch sử gần nhất:\n" + "\n".join(lines)
    await update.message.reply_text(msg)

# ----- 📢 GỬI THÔNG BÁO ĐẾN TOÀN BỘ GROUP -----

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    if not context.args:
        await update.message.reply_text("❌ Dùng: `/broadcast <nội dung>`")
        return

    msg = " ".join(context.args)
    groups = get_all_groups()
    count = 0
    for g in groups:
        try:
            await context.bot.send_message(g["chat_id"], f"📢 **THÔNG BÁO:**\n\n{msg}", parse_mode="Markdown")
            count += 1
        except Exception:
            pass

    await update.message.reply_text(f"✅ Đã gửi thông báo đến {count} nhóm.")

# ----- 📝 ĐĂNG KÝ HANDLERS -----

from telegram.ext import CommandHandler

def register_admin_handlers(app):
    app.add_handler(CommandHandler("code", cmd_code))
    app.add_handler(CommandHandler("addmoney", cmd_addmoney))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
