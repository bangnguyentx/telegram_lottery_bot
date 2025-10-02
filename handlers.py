from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
from db import ensure_user, insert_bet, update_balance
from utils import format_money
from datetime import datetime

MIN_BET = 1000

# =============== USER MENU ===================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id, user.username or "")
    text = (
        f"👋 Chào mừng {user.first_name} đến với *QLottery Bot*!\n\n"
        "🎁 Bạn được tặng 80.000₫ miễn phí.\n"
        "📌 Phải cược đủ 9 vòng và nạp 100K mới được rút.\n\n"
        "Chọn bên dưới để bắt đầu 👇"
    )
    keyboard = [
        [InlineKeyboardButton("🎮 Game", callback_data="menu_game")],
        [InlineKeyboardButton("💰 Nạp tiền", callback_data="menu_nap")],
        [InlineKeyboardButton("🏧 Rút tiền", callback_data="menu_rut")],
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_game":
        await query.edit_message_text(
            "🎯 *Danh sách Game:*\n\n"
            "• Room QLottery: đặt cược Nhỏ/Lớn, Chẵn/Lẻ hoặc số\n"
            "👉 Link tham gia nhóm: @QLROOM\n\n"
            "• Chẵn lẻ: Coming soon\n• Sicbo: Coming soon",
            parse_mode="Markdown"
        )
    elif data == "menu_nap":
        await query.edit_message_text("💰 Liên hệ nạp tiền: @HOANGDUNGG789")
    elif data == "menu_rut":
        await query.edit_message_text(
            "🏧 *Rút tiền*\n\n"
            "Nhập lệnh:\n`/ruttien <Ngân hàng> <Số TK> <Số tiền>`\n\n"
            "• Rút tối thiểu 100.000₫\n"
            "• Phải cược đủ 1.1 vòng cược",
            parse_mode="Markdown"
        )

# =============== BET HANDLERS ===================

async def bet_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg is None or msg.text is None:
        return

    text = msg.text.strip()
    user = update.effective_user
    chat = update.effective_chat
    ensure_user(user.id, user.username or "")

    # Đặt Nhỏ / Lớn
    if text.lower().startswith("/n") or text.lower().startswith("/l") or text.lower().startswith("/c") or text.lower().startswith("/le"):
        prefix = text[1:].lower()
        bet_type = None
        if text.lower().startswith("/n"): bet_type = "nho"
        elif text.lower().startswith("/l"): bet_type = "lon"
        elif text.lower().startswith("/c"): bet_type = "chan"
        elif text.lower().startswith("/le"): bet_type = "le"

        try:
            amount = int(prefix[1:])
        except:
            await msg.reply_text("❌ Sai cú pháp cược. Ví dụ: /N1000 hoặc /L5000")
            return

        if amount < MIN_BET:
            await msg.reply_text(f"⚠️ Mức cược tối thiểu {MIN_BET:,}₫")
            return

        # ❗ TODO: kiểm tra số dư, trừ tiền
        # ❗ TODO: lấy round_id hiện tại
        round_id = datetime.utcnow().strftime("%Y%m%d%H%M")  # tạm thời
        insert_bet(user.id, chat.id, round_id, bet_type, bet_type, amount)
        await msg.reply_text(f"✅ Đã đặt {bet_type.upper()} {format_money(amount)} cho phiên {round_id}")

# =============== REGISTER ===================

def register_user_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), bet_message_handler))
    app.add_handler(MessageHandler(filters.COMMAND, bet_message_handler))  # bắt /N1000, /S123, ...
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, start))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, lambda u, c: None))
    app.add_handler(MessageHandler(filters.UpdateType.CALLBACK_QUERY, menu_callback))


def register_group_handlers(app):
    # Có thể thêm lệnh /batdau, /stop sau
    pass
