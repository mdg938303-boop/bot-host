import os
import logging
from pathlib import Path
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from manager.core import BotManager

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))
TOKEN = os.environ.get("MANAGER_BOT_TOKEN", "")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot-host")
manager = BotManager(BASE, DATA)

MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("📤 Upload Bot"), KeyboardButton("🤖 My Bots")],
        [KeyboardButton("▶️ Start Bot"), KeyboardButton("⏹ Stop Bot")],
        [KeyboardButton("🔄 Restart Bot"), KeyboardButton("📝 Edit Code")],
        [KeyboardButton("📋 Logs"), KeyboardButton("🐞 Crash Reports")],
        [KeyboardButton("📊 System Status"), KeyboardButton("ℹ️ Help")],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

def is_admin(update: Update) -> bool:
    return bool(update.effective_user and ADMIN_ID and update.effective_user.id == ADMIN_ID)

async def send(update: Update, text: str):
    if update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=MENU)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await send(update, "⛔ Access denied. এই Hosting Manager শুধু অনুমোদিত Admin ব্যবহার করতে পারবেন।")
        return
    await send(update, "🛡️ BotHost Manager\n\nস্বাগতম! নিচের Reply Keyboard থেকে কাজ বেছে নিন।\n\n📤 Upload Bot — .py/.zip আপলোড\n🤖 My Bots — বট তালিকা ও ID\n📝 Edit Code — বটের ফাইল পরিবর্তন\n🐞 Crash Reports — সাম্প্রতিক ত্রুটি")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await send(update, "⛔ Access denied.")
        return
    await send(update, "ব্যবহার:\n1) 📤 Upload Bot চাপুন, এরপর .py অথবা .zip ফাইল পাঠান।\n2) 🤖 My Bots থেকে ID দেখুন।\n3) Start/Stop/Restart চাপুন, তারপর ID পাঠান।\n4) 📝 Edit Code চাপুন, তারপর ID এবং ফাইলের আপেক্ষিক path পাঠান।\n5) 📋 Logs বা 🐞 Crash Reports চাপুন, তারপর ID পাঠান।\n\nZIP-এর ভেতরে entrypoint হিসেবে main.py বা bot.py রাখুন। requirements.txt থাকলে upload-এর সময় dependencies ইনস্টল হবে।")

async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await send(update, "⛔ Access denied.")
        return
    # If this document is the replacement file for the code editor, do not
    # also treat it as a fresh bot upload.
    if context.user_data.get("action") == "edit" and "edit_path" in context.user_data:
        return
    doc = update.effective_message.document
    if not doc:
        return
    name = Path(doc.file_name or "upload").name
    if not (name.endswith(".py") or name.endswith(".zip")):
        await send(update, "শুধু .py অথবা .zip ফাইল আপলোড করা যাবে।")
        return
    if doc.file_size and doc.file_size > 10 * 1024 * 1024:
        await send(update, "ফাইলটি 10 MB-এর বেশি। ছোট ফাইল পাঠান।")
        return
    tg_file = await context.bot.get_file(doc.file_id)
    temp = DATA / f"upload_{update.effective_user.id}_{name}"
    await tg_file.download_to_drive(custom_path=temp)
    try:
        bot_id, message = manager.add_upload(temp, name)
        await send(update, f"✅ Upload complete\nBot ID: `{bot_id}`\n{message}\n\nএখন ▶️ Start Bot চাপুন এবং Bot ID পাঠান।")
    except Exception as exc:
        log.exception("upload failed")
        await send(update, f"❌ Upload failed: {type(exc).__name__}: {exc}")
    finally:
        temp.unlink(missing_ok=True)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await send(update, "⛔ Access denied.")
        return
    text = (update.effective_message.text or "").strip()
    actions = {
        "📤 Upload Bot": "upload",
        "🤖 My Bots": "list",
        "▶️ Start Bot": "start",
        "⏹ Stop Bot": "stop",
        "🔄 Restart Bot": "restart",
        "📝 Edit Code": "edit",
        "📋 Logs": "logs",
        "🐞 Crash Reports": "crashes",
        "📊 System Status": "status",
        "ℹ️ Help": "help",
    }
    if text in actions:
        action = actions[text]
        context.user_data["action"] = action
        if action == "list":
            await send(update, manager.list_bots())
        elif action == "status":
            await send(update, manager.system_status())
        elif action == "help":
            await help_cmd(update, context)
        elif action == "upload":
            await send(update, "এখন .py অথবা .zip ফাইল Document হিসেবে পাঠান।")
        elif action == "edit":
            await send(update, "প্রথমে Bot ID পাঠান। তারপর ফাইলের relative path চাইব।")
        else:
            await send(update, f"{text}\nএখন Bot ID পাঠান।")
        return

    action = context.user_data.get("action")
    if not action:
        await send(update, "মেনু থেকে একটি কাজ বেছে নিন। /start")
        return

    try:
        if action in ("start", "stop", "restart", "logs", "crashes"):
            bot_id = text
            if action == "start":
                result = manager.start_bot(bot_id)
            elif action == "stop":
                result = manager.stop_bot(bot_id)
            elif action == "restart":
                result = manager.restart_bot(bot_id)
            elif action == "logs":
                result = manager.get_logs(bot_id)
            else:
                result = manager.get_crashes(bot_id)
            context.user_data.pop("action", None)
            await send(update, result[:3900])
        elif action == "edit":
            if "edit_bot_id" not in context.user_data:
                if not manager.bot_exists(text):
                    await send(update, "Bot ID পাওয়া যায়নি। 🤖 My Bots দেখে সঠিক ID দিন।")
                    return
                context.user_data["edit_bot_id"] = text
                await send(update, "এখন ফাইলের relative path দিন (যেমন main.py)। Absolute path বা ../ ব্যবহার করবেন না।")
            else:
                bot_id = context.user_data.pop("edit_bot_id")
                result = manager.prepare_edit(bot_id, text)
                context.user_data["edit_path"] = text
                context.user_data["edit_bot_id"] = bot_id
                await send(update, result + "\n\nএখন পরিবর্তিত সম্পূর্ণ ফাইলটি Document হিসেবে পাঠান।")
        else:
            await send(update, "কাজটি বুঝতে পারিনি। /start চাপুন।")
    except Exception as exc:
        log.exception("action failed")
        context.user_data.pop("action", None)
        await send(update, f"❌ {type(exc).__name__}: {exc}\n\n🐞 Crash Reports বা 📋 Logs দেখুন।")

async def edit_document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    if context.user_data.get("action") != "edit" or "edit_path" not in context.user_data:
        return
    doc = update.effective_message.document
    if not doc:
        return
    if doc.file_size and doc.file_size > 2 * 1024 * 1024:
        await send(update, "Edit file সর্বোচ্চ 2 MB হতে পারে।")
        return
    bot_id = context.user_data.pop("edit_bot_id")
    rel = context.user_data.pop("edit_path")
    temp = DATA / f"edit_{update.effective_user.id}_{Path(doc.file_name or 'file').name}"
    try:
        await (await context.bot.get_file(doc.file_id)).download_to_drive(custom_path=temp)
        result = manager.apply_edit(bot_id, rel, temp)
        context.user_data.pop("action", None)
        await send(update, result)
    except Exception as exc:
        log.exception("edit failed")
        await send(update, f"❌ Edit failed: {type(exc).__name__}: {exc}")
    finally:
        temp.unlink(missing_ok=True)

def main():
    if not TOKEN or ADMIN_ID == 0:
        raise SystemExit("Set MANAGER_BOT_TOKEN and ADMIN_ID environment variables before starting.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, edit_document_handler), group=0)
    app.add_handler(MessageHandler(filters.Document.ALL, document_handler), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    log.info("Bot Host Manager starting")
    app.run_polling()

if __name__ == "__main__":
    main()
