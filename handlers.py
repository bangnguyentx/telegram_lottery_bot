from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
from db import db_query, db_execute, ensure_user
from utils import format_money, lock_group_chat, unlock_group_chat
import re

MIN_BET = 1000

# 🟢 Xử lý cược lớn / nhỏ / chẵn / lẻ
async def bet_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg is None or msg.text is None:
        return

    text = msg.text.strip()
    user = update.effective_user
    chat = update.effective_chat

    # Chỉ nhận lệnh bắt đầu bằng /
    if not text.startswith("/"):
        return

    # Nhận dạng lệnh: /N1000, /L1000, /C1000, /Le1000
    cmd = text[1:].lower()

    # Kiểm tra định dạng hợp lệ
    prefix = None
    if cmd.startswith("n"):
        prefix = "nho"
    elif cmd.startswith("l") and not cmd.startswith("le"):
        prefix = "lon"
    elif cmd.startswith("c"):
        prefix = "chan"
    elif cmd.startswith("le"):
        prefix = "le"

    if not prefix:
        # có thể là cược số
        await bet_number_handler(update, context)
        return

    # lấy tiền cược
    amount_str = re.sub(r'[^0-9]', '', cmd)
    if not amount_str.isdigit():
        return
    amount = int(amount_str)

    if amount < MIN_BET:
        await msg.reply_text(f"❌ Cược tối thiểu {MIN_BET:,}₫")
        return

    # kiểm tra user có trong DB chưa
    ensure_user(user.id, user.username or "", user.first_name or "")
    u = db_query("SELECT balance FROM users WHERE user_id=?", (user.id,))
    if not u or (u[0]['balance'] or 0) < amount:
        await msg.reply_text("💸 Số dư không đủ.")
        return

    # trừ tiền ngay
    new_balance = (u[0]['balance'] or 0) - amount
    db_execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user.id))

    # lưu cược vào DB
    now_ts = int(datetime.utcnow().timestamp())
    round_epoch = now_ts // 60
    round_id = f"{chat.id}_{round_epoch}"

    db_execute("""
        INSERT INTO bets(chat_id, round_id, user_id, bet_type, amount, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (chat.id, round_id, user.id, prefix, amount, datetime.utcnow().isoformat()))

    await msg.reply_text(f"✅ Đã đặt {prefix.upper()} {format_money(amount)} cho phiên hiện tại.")

# 🔢 Cược theo số /S<dãy số> <tiền>
async def bet_number_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = msg.text.strip()
    user = update.effective_user
    chat = update.effective_chat

    # cú pháp: /S123456 1000
    match = re.match(r"^/s(\d{1,6})\s+(\d+)$", text.lower())
    if not match:
        return
    number_seq = match.group(1)
    amount = int(match.group(2))

    if amount < MIN_BET:
        await msg.reply_text(f"❌ Cược tối thiểu {MIN_BET:,}₫")
        return

    ensure_user(user.id, user.username or "", user.first_name or "")
    u = db_query("SELECT balance FROM users WHERE user_id=?", (user.id,))
    if not u or (u[0]['balance'] or 0) < amount:
        await msg.reply_text("💸 Số dư không đủ.")
        return

    new_balance = (u[0]['balance'] or 0) - amount
    db_execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, user.id))

    now_ts = int(datetime.utcnow().timestamp())
    round_epoch = now_ts // 60
    round_id = f"{chat.id}_{round_epoch}"

    db_execute("""
        INSERT INTO bets(chat_id, round_id, user_id, bet_type, bet_value, amount, timestamp)
        VALUES (?, ?, ?, 'so', ?, ?, ?)
    """, (chat.id, round_id, user.id, number_seq, amount, datetime.utcnow().isoformat()))

    await msg.reply_text(f"✅ Đã đặt {number_seq} {format_money(amount)} cho phiên hiện tại.")

# ⏱ Gửi thông báo đếm ngược 30s, 10s, khóa chat 5s
async def countdown_notifications(context: ContextTypes.DEFAULT_TYPE, chat_id: int, seconds_left: int):
    if seconds_left == 30:
        await context.bot.send_message(chat_id=chat_id, text="⏱ Còn 30 giây để đặt cược!")
    elif seconds_left == 10:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Còn 10 giây!")
    elif seconds_left == 5:
        await context.bot.send_message(chat_id=chat_id, text="🔒 Khoá chat, chuẩn bị quay số!")
        await lock_group_chat(context.bot, chat_id)
    elif seconds_left == 0:
        await unlock_group_chat(context.bot, chat_id)
