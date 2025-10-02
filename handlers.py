# handlers.py — Xử lý lệnh người dùng & nhóm
import re
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from db import (
    get_user, ensure_user, insert_bet,
    get_user_bet_in_round, update_bet_amount, get_group, update_balance
)
from utils import get_current_round_id, format_money

MIN_BET = 5000

def parse_bet_command(text: str):
    text = text.strip()
    m = re.match(r"^/(N|L|C|Le)(\d+)$", text, re.IGNORECASE)
    if m:
        bet_type = m.group(1).upper()
        amount = int(m.group(2))
        return bet_type, bet_type, amount
    m = re.match(r"^/S(\d{1,6})\s+(\d+)$", text, re.IGNORECASE)
    if m:
        return "S", m.group(1), int(m.group(2))
    return None

async def group_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    if chat.type not in ("group", "supergroup") or not msg.text:
        return

    parsed = parse_bet_command(msg.text)
    if not parsed: return

    bet_type, bet_value, amount = parsed
    if amount < MIN_BET:
        await msg.reply_text(f"⚠️ Mức cược tối thiểu là {format_money(MIN_BET)}")
        return

    ensure_user(user.id, user.username or "", user.first_name or "")
    u = get_user(user.id)
    if not u or u["balance"] < amount:
        await msg.reply_text("💸 Số dư không đủ.")
        return

    g = get_group(chat.id)
    if not g or g["approved"] != 1:
        await msg.reply_text("⛔ Nhóm này chưa được admin duyệt.")
        return

    round_id = get_current_round_id(chat.id)
    existing_bet = get_user_bet_in_round(user.id, chat.id, round_id, bet_type, bet_value)

    if existing_bet:
        update_bet_amount(existing_bet["id"], existing_bet["amount"] + amount)
    else:
        insert_bet(chat.id, round_id, user.id, bet_type, bet_value, amount)

    update_balance(user.id, u["balance"] - amount)
    await msg.reply_text(f"✅ Đã cược {bet_type} {format_money(amount)}!")

def register_group_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group_bet_handler))
    app.add_handler(MessageHandler(filters.COMMAND, group_bet_handler))

def register_user_handlers(app):
    pass
