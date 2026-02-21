import os
from dotenv import load_dotenv

load_dotenv()  # загружаем переменные из .env

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Токен не найден! Добавьте BOT_TOKEN в файл .env")
