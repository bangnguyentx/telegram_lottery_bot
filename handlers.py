# handlers.py — Xử lý lệnh người dùng & nhóm cho QLottery_bot

import re
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from db import (
    get_user,
    ensure_user,
    insert_bet,
    get_user_bet_in_round,
    update_bet_amount,
    get_group,
)
from utils import (
    get_current_round_id,
    format_money,
)

# ----------- CẤU HÌNH -----------

MIN_BET = 5000  # Mức cược tối thiểu

# ----------- HỖ TRỢ -----------

def parse_bet_command(text: str):
    """
    Trả về (bet_type, bet_value, amount) nếu hợp lệ
    Hỗ trợ:
    /N1000 /L5000 /C20000 /Le10000
    /S123456 1000
    """
    text = text.strip()

    # Lớn / Nhỏ / Chẵn / Lẻ
    m = re.match(r"^/(N|L|C|Le)(\d+)$", text, re.IGNORECASE)
    if m:
        bet_type = m.group(1).upper()
        amount = int(m.group(2))
        return bet_type, bet_type, amount

    # Đặt số cụ thể: /S123456 1000
    m = re.match(r"^/S(\d{1,6})\s+(\d+)$", text, re.IGNORECASE)
    if m:
        bet_value = m.group(1)
        amount = int(m.group(2))
        return "S", bet_value, amount

    return None

# ----------- ĐẶT CƯỢC TRONG NHÓM -----------

async def group_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    chat = update.effective_chat
    user = update.effective_user

    # Chỉ xử lý trong group
    if chat.type not in ("group", "supergroup"):
        return

    if not msg.text:
        return

    parsed = parse_bet_command(msg.text)
    if not parsed:
        return

    bet_type, bet_value, amount = parsed

    # Kiểm tra mức cược
    if amount < MIN_BET:
        await msg.reply_text(f"⚠️ Mức cược tối thiểu là {format_money(MIN_BET)}")
        return

    # Đảm bảo user tồn tại trong DB
    ensure_user(user.id, user.username or "", user.first_name or "")

    u = get_user(user.id)
    if not u:
        await msg.reply_text("❌ Lỗi người dùng, hãy /start trước khi cược.")
        return

    if u["balance"] < amount:
        await msg.reply_text("💸 Số dư không đủ để đặt cược.")
        return

    # Kiểm tra group đã được duyệt chạy chưa
    g = get_group(chat.id)
    if not g or g["approved"] != 1:
        await msg.reply_text("⛔ Nhóm này chưa được admin duyệt để bot hoạt động.")
        return

    # Xác định round hiện tại
    round_id = get_current_round_id(chat.id)

    # Kiểm tra vé đã cược trong phiên này
    existing_bet = get_user_bet_in_round(user.id, chat.id, round_id, bet_type, bet_value)

    # ❌ Không cho cược ngược
    if bet_type in ("N", "L"):
        opposite = "L" if bet_type == "N" else "N"
    elif bet_type in ("C", "LE"):
        opposite = "LE" if bet_type == "C" else "C"
    else:
        opposite = None

    if opposite:
        opposite_bet = get_user_bet_in_round(user.id, chat.id, round_id, opposite, opposite)
        if opposite_bet:
            await msg.reply_text("🚫 Bạn không thể cược ngược trong cùng một phiên!")
            return

    # Nếu đã cược cùng loại → cộng dồn tiền
    if existing_bet:
        new_amount = existing_bet["amount"] + amount
        update_bet_amount(existing_bet["id"], new_amount)
    else:
        insert_bet(chat.id, round_id, user.id, bet_type, bet_value, amount)

    # Trừ tiền người chơi
    new_balance = u["balance"] - amount
    from db import update_balance
    update_balance(user.id, new_balance)

    await msg.reply_text(f"✅ Đã cược {bet_type} {format_money(amount)} cho phiên hiện tại.")

# ----------- ĐĂNG KÝ HANDLERS -----------

def register_group_handlers(app):
    """Đăng ký handler cho group"""
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, group_bet_handler))
    app.add_handler(MessageHandler(filters.COMMAND, group_bet_handler))


def register_user_handlers(app):
    """Các lệnh riêng tư (PM bot)"""
    pass
