from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from db import update_balance

async def admin_add_money(update: Update, context: ContextTypes.DEFAULT_TYPE, admin_ids):
    if update.effective_user.id not in admin_ids:
        return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
    except:
        await update.message.reply_text("❌ Sai cú pháp. /congtien <user_id> <số tiền>")
        return
    update_balance(uid, amount)
    await update.message.reply_text(f"✅ Đã cộng {amount:,}₫ cho user {uid}")

def register_admin_handlers(app, admin_ids):
    app.add_handler(CommandHandler("congtien", lambda u, c: admin_add_money(u, c, admin_ids)))
