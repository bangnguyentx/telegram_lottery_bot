from telegram import Update
from telegram.ext import ContextTypes
from db import db_query, db_execute
from utils import format_money
from datetime import datetime

# 🧑‍💻 DANH SÁCH ADMIN ID
ADMIN_IDS = [7760459637]  # 👈 bạn có thể thêm nhiều ID nếu muốn

# 📢 Gửi thông báo crash cho admin
async def notify_admins(context: ContextTypes.DEFAULT_TYPE, message: str):
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=f"🚨 BOT CRASH: {message}")
        except Exception:
            pass

# 🧾 /topnap — Top 10 người nạp nhiều nhất
async def topnap_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    rows = db_query("SELECT user_id, total_deposit FROM users ORDER BY total_deposit DESC LIMIT 10")
    if not rows:
        await update.message.reply_text("Chưa có dữ liệu nạp.")
        return
    msg = "🏆 *TOP 10 NẠP NHIỀU NHẤT*\n\n"
    for i, r in enumerate(rows, 1):
        msg += f"{i}. ID {r['user_id']} — {format_money(int(r['total_deposit'] or 0))}\n"
    await update.message.reply_text(msg)

# 📝 /congtien <user_id> <amount>
async def congtien_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    try:
        _, uid, amount = update.message.text.strip().split()
        uid = int(uid)
        amount = int(amount)
    except:
        await update.message.reply_text("❌ Sai cú pháp. Ví dụ: /congtien 123456 100000")
        return

    user = db_query("SELECT balance FROM users WHERE user_id=?", (uid,))
    if not user:
        await update.message.reply_text("❌ Không tìm thấy user này.")
        return

    new_balance = int(user[0]['balance']) + amount
    db_execute("UPDATE users SET balance=? WHERE user_id=?", (new_balance, uid))
    await update.message.reply_text(f"✅ Đã cộng {format_money(amount)} cho ID {uid}.\n💰 Số dư mới: {format_money(new_balance)}")

# 🧮 /nho — Chỉnh kết quả phiên thành nhỏ
# 🧮 /lon — Chỉnh kết quả phiên thành lớn
# 🧮 /chan — Chỉnh kết quả phiên thành chẵn
# 🧮 /le — Chỉnh kết quả phiên thành lẻ
# Không thông báo vào nhóm khi chỉnh
async def set_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    cmd = update.message.text.strip().lower()
    if cmd not in ("/nho", "/lon", "/chan", "/le"):
        return

    # Lấy round_id hiện tại (phiên đang chạy)
    row = db_query("SELECT round_id FROM rounds ORDER BY created_at DESC LIMIT 1")
    if not row:
        await update.message.reply_text("❌ Không tìm thấy phiên hiện tại.")
        return
    round_id = row[0]['round_id']

    if cmd == "/nho":
        db_execute("UPDATE rounds SET forced_result='nho' WHERE round_id=?", (round_id,))
    elif cmd == "/lon":
        db_execute("UPDATE rounds SET forced_result='lon' WHERE round_id=?", (round_id,))
    elif cmd == "/chan":
        db_execute("UPDATE rounds SET forced_result='chan' WHERE round_id=?", (round_id,))
    elif cmd == "/le":
        db_execute("UPDATE rounds SET forced_result='le' WHERE round_id=?", (round_id,))

    await update.message.reply_text(f"✅ Đã chỉnh kết quả phiên {round_id} thành {cmd[1:].upper()}")

# 🎟 /code <amount> <wager>
async def create_code_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    try:
        _, amount, wager = update.message.text.strip().split()
        amount = int(amount)
        wager = int(wager)
    except:
        await update.message.reply_text("❌ Sai cú pháp. Ví dụ: /code 100000 9")
        return

    now = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    code = f"CODE{now}"

    db_execute("INSERT INTO codes(code, amount, wager, active) VALUES (?, ?, ?, 1)", (code, amount, wager))
    await update.message.reply_text(f"✅ Tạo code thành công:\n🔸 Code: {code}\n💰 Giá trị: {format_money(amount)}\n🔁 Vòng cược: {wager}")
