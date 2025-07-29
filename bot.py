import logging
import os
import requests
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import json
from functools import wraps
import datetime

# Токены и ключи
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "7641501349:AAF7MdDDZUJlMm728k_KV1opANAYmA3LTjg")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-1ed0ae30c05f43fba1d65e46897400b8")
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

USERS_FILE = "users.json"
ADMIN_ID = 1129806592

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def save_user(chat_id):
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    except Exception:
        users = {}
    user = users.get(str(chat_id), {})
    now = datetime.datetime.now()
    hour = str(now.hour)
    if not user:
        user["first_seen"] = now.isoformat()
        user["messages_count"] = 1
        user["hours_activity"] = {hour: 1}
    else:
        user["messages_count"] = user.get("messages_count", 0) + 1
        hours = user.get("hours_activity", {})
        hours[hour] = hours.get(hour, 0) + 1
        user["hours_activity"] = hours
    users[str(chat_id)] = user
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def get_users():
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
            return set(users.keys())
    except Exception:
        return set()

def get_user_info(chat_id):
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
            return users.get(str(chat_id), {})
    except Exception:
        return {}

def collect_activity_by_hour():
    try:
        with open(USERS_FILE, "r") as f:
            users = json.load(f)
    except Exception:
        return {}
    total_by_hour = {str(h): 0 for h in range(24)}
    for user in users.values():
        hours = user.get("hours_activity", {})
        for h, count in hours.items():
            total_by_hour[h] = total_by_hour.get(h, 0) + count
    return total_by_hour

def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID:
            await update.message.reply_text("Нет доступа. Только для администратора.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id == ADMIN_ID:
        keyboard = [
            [KeyboardButton("Статистика"), KeyboardButton("Рассылка")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        text = "Привет, админ! Выберите действие:"
    else:
        keyboard = [
            [KeyboardButton("Помощь")],
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        text = "Привет! Я Telegram-бот с DeepSeek. Напиши мне что-нибудь или выбери действие."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_users()
    await update.message.reply_text(f"Пользователей в базе: {len(users)}")

@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Использование: /broadcast текст_сообщения")
        return
    text = " ".join(context.args)
    users = get_users()
    count = 0
    for chat_id in users:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            count += 1
        except Exception:
            pass
    await update.message.reply_text(f"Рассылка завершена. Сообщение отправлено {count} пользователям.")

@admin_only
async def activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = collect_activity_by_hour()
    lines = [f"{h.zfill(2)}:00 — {stats[h]} сообщений" for h in sorted(stats, key=lambda x: int(x))]
    text = "Активность по времени суток (по всем пользователям):\n" + "\n".join(lines)
    await update.message.reply_text(text)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    chat_id = update.effective_chat.id
    save_user(chat_id)
    user_id = update.effective_user.id
    # Обработка кнопок
    if user_message == "Статистика" and user_id == ADMIN_ID:
        await stats(update, context)
        return
    if user_message == "Рассылка" and user_id == ADMIN_ID:
        await context.bot.send_message(chat_id=chat_id, text="Введите команду /broadcast текст_сообщения для рассылки.")
        return
    if user_message == "Помощь":
        await context.bot.send_message(chat_id=chat_id, text="Я могу отвечать на ваши вопросы с помощью DeepSeek. Просто напишите сообщение!")
        return
    response = ask_deepseek(user_message)
    await context.bot.send_message(chat_id=chat_id, text=response)

def ask_deepseek(prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=data, timeout=30)
        r.raise_for_status()
        result = r.json()
        return result["choices"][0]["message"]["content"]
    except Exception:
        return "Сервис временно недоступен, попробуйте позже."

if __name__ == '__main__':
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('broadcast', broadcast))
    application.add_handler(CommandHandler('activity', activity))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.run_polling() 