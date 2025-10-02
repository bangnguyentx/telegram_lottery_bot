# handlers.py — Xử lý lệnh cược & nhóm QLottery_bot

import re
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters

from db import get_user, ensure_user, update_balance, insert_or_update_bet, get_bets_for_round, clear_bets_for_round
from utils import format_money, get_current_round_id, lock_group_chat, unlock_group_chat, send_countdown

logger = logging.getLogger(__name__)

# Hệ số trả thưởng
PAYOUTS = {
    "N": 1.97,
    "L": 1.97,
    "C": 1.97,
    "LE": 1.97
}

# ----- 📌 XỬ LÝ CƯỢC -----

async def group_bet_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý cược trong nhóm: /N1000, /L1000, /C1000, /Le1000, /S123456 1000"""
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    text = msg.text.strip()

    if chat.type not in ("group", "supergroup"):
        return

    # Đảm bảo user tồn tại DB
    ensure_user(user.id, user.username or "", user.first_name or "")

    # Lấy thông tin user
    u = get_user(user.id)
    if not u:
        await msg.reply_text("Lỗi tài khoản, vui lòng /start lại.")
        return

    # Xác định loại cược
    bet_type = None
    amount = None
    bet_value = None

    # Kiểm tra lệnh nhỏ/lớn/chẵn/lẻ
    m = re.match(r"^/(N|L|C|Le)(\d+)$", text, re.IGNORECASE)
    if m:
        bet_type = m.group(1).upper()
        amount = int(m.group(2))
        if bet_type == "LE":
            bet_type = "LE"  # giữ nguyên chữ hoa cho lẻ

    # Kiểm tra lệnh cược số /S123456 1000
    if text.startswith("/S"):
        parts = text.split()
        if len(parts) != 2:
            await msg.reply_text("Cú pháp sai. Ví dụ: /S123456 1000")
            return
        numbers = parts[0][2:].strip()
        amount = int(parts[1])
        if not numbers.isdigit() or len(numbers) == 0 or len(numbers) > 6:
            await msg.reply_text("Số cược không hợp lệ (1–6 chữ số).")
            return
        bet_type = "S"
        bet_value = numbers

    if not bet_type or not amount or amount <= 0:
        return

    # ✅ Kiểm tra số dư
    balance = u["balance"] or 0
    if balance < amount:
        await msg.reply_text("❌ Số dư không đủ.")
        return

    # ✅ Xác định round hiện tại
    round_id = get_current_round_id(chat.id)

    # ✅ Kiểm tra không cược ngược cùng phiên
    existing_bets = get_bets_for_round(chat.id, round_id, user.id)
    if existing_bets:
        for b in existing_bets:
            if b["bet_type"] in ("N", "L") and bet_type in ("N", "L") and b["bet_type"] != bet_type:
                await msg.reply_text("❌ Bạn không thể cược Nhỏ và Lớn cùng phiên.")
                return
            if b["bet_type"] in ("C", "LE") and bet_type in ("C", "LE") and b["bet_type"] != bet_type:
                await msg.reply_text("❌ Bạn không thể cược Chẵn và Lẻ cùng phiên.")
                return

    # ✅ Trừ tiền ngay
    new_balance = balance - amount
    update_balance(user.id, new_balance)

    # ✅ Ghi cược vào DB (nếu đã cược cùng loại → cộng dồn)
    insert_or_update_bet(chat.id, round_id, user.id, bet_type, bet_value, amount)

    # ✅ Xác nhận đặt cược
    if bet_type == "S":
        display = f"Số {bet_value}"
    elif bet_type == "N":
        display = "Nhỏ"
    elif bet_type == "L":
        display = "Lớn"
    elif bet_type == "C":
        display = "Chẵn"
    elif bet_type == "LE":
        display = "Lẻ"

    await msg.reply_text(f"✅ Đã đặt {display} {format_money(amount)} cho phiên hiện tại.")

# ----- 🧮 TÍNH THƯỞNG -----

def calculate_payout(bet_type: str, bet_value: str, amount: int, result_number: str, result_category: str):
    """Tính tiền thưởng dựa theo loại cược & kết quả"""
    if bet_type in ("N", "L", "C", "LE"):
        if bet_type == result_category:
            return int(amount * PAYOUTS[bet_type])
        return 0

    if bet_type == "S":
        # So khớp số cuối cùng của kết quả với bet_value
        if result_number.endswith(bet_value):
            n = len(bet_value)
            if n == 1:
                return int(amount * 9.2)
            elif n == 2:
                return int(amount * 90)
            elif n == 3:
                return int(amount * 900)
            elif n == 4:
                return int(amount * 8000)
            elif n == 5:
                return int(amount * 50000)
            elif n == 6:
                return int(amount * 200000)
    return 0

# ----- ⏰ ĐĂNG KÝ HANDLER -----

def register_group_handlers(app):
    app.add_handler(MessageHandler(filters.TEXT & filters.ChatType.GROUPS, group_bet_handler))
