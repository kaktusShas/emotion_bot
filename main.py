import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

import config
import database as db

# Включаем логирование (чтобы видеть ошибки)
logging.basicConfig(level=logging.INFO)

# Инициализируем бота и диспетчер
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# ---------- Клавиатуры ----------
def get_main_keyboard():
    """Главная клавиатура с кнопками"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="📊 Статистика")
    kb.button(text="🧪 Пройти тест")
    kb.button(text="💡 Методики")
    kb.adjust(2)  # две кнопки в ряду
    return kb.as_markup(resize_keyboard=True)

def get_stats_period_keyboard():
    """Инлайн-клавиатура для выбора периода статистики"""
    buttons = [
        [InlineKeyboardButton(text="День", callback_data="stats_day"),
         InlineKeyboardButton(text="Неделя", callback_data="stats_week"),
         InlineKeyboardButton(text="Месяц", callback_data="stats_month")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Вопросы для ежедневного опроса ----------
QUESTIONS = [
    {"text": "Как вы себя чувствуете сегодня? (1 - ужасно, 5 - отлично)", "key": "feeling", "type": "scale", "min":1, "max":5},
    {"text": "Оцените уровень тревоги (1 - нет, 5 - очень высокая)", "key": "anxiety", "type": "scale", "min":1, "max":5},
    {"text": "Были ли сегодня вспышки агрессии? (0 - нет, 1 - да)", "key": "aggression", "type": "binary"},
]

# Хранилище состояний опроса (временное, в оперативной памяти)
# Ключ: user_id, значение: индекс текущего вопроса и собранные ответы
poll_states = {}

# ---------- Команда /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    # Инициализируем пользователя в базе (если ещё нет)
    db.get_user(user_id)
    await message.answer(
        "Привет! Я бот для отслеживания эмоционального состояния.\n"
        "Каждый день я буду задавать несколько вопросов, чтобы оценить ваше самочувствие.\n"
        "Вы также можете пройти тест на тревожность/депрессию или посмотреть статистику.",
        reply_markup=get_main_keyboard()
    )

# ---------- Обработка главного меню ----------
@dp.message(lambda msg: msg.text == "📊 Статистика")
async def stats_menu(message: types.Message):
    await message.answer("Выберите период:", reply_markup=get_stats_period_keyboard())

@dp.message(lambda msg: msg.text == "🧪 Пройти тест")
async def test_menu(message: types.Message):
    # Здесь можно предложить выбор теста, но для примера сделаем один простой тест
    await message.answer("Выберите тест:\n1. Тест на тревожность (GAD-7) – скоро будет...\nПока просто команда /test для демо")
    # Можно сразу запустить тест, но для упрощения пока заглушка

@dp.message(lambda msg: msg.text == "💡 Методики")
async def methods_menu(message: types.Message):
    text = (
        "**Методики для снижения тревоги:**\n"
        "- Дыхательное упражнение 4-7-8\n"
        "- Прогрессивная мышечная релаксация\n"
        "- Медитация осознанности\n\n"
        "**При агрессии:**\n"
        "- Сосчитать до 10\n"
        "- Физическая активность\n"
        "- Дневник эмоций"
    )
    await message.answer(text)

# ---------- Обработка инлайн-кнопок (статистика) ----------
@dp.callback_query(lambda c: c.data.startswith("stats_"))
async def process_stats_callback(callback: types.CallbackQuery):
    period = callback.data.split("_")[1]  # day, week, month
    user_id = callback.from_user.id
    user_data = db.get_user(user_id)
    answers = user_data.get("answers", [])
    
    if not answers:
        await callback.message.edit_text("У вас пока нет данных для статистики.")
        await callback.answer()
        return
    
    now = datetime.now()
    if period == "day":
        start_date = now - timedelta(days=1)
    elif period == "week":
        start_date = now - timedelta(weeks=1)
    else:  # month
        start_date = now - timedelta(days=30)
    
    # Фильтруем ответы за период
    filtered = [a for a in answers if datetime.fromisoformat(a["date"]) >= start_date]
    
    if not filtered:
        await callback.message.edit_text(f"Нет данных за выбранный период ({period}).")
        await callback.answer()
        return
    
    # Вычисляем средние значения
    total_feeling = sum(a["feeling"] for a in filtered)
    total_anxiety = sum(a["anxiety"] for a in filtered)
    total_aggression = sum(a["aggression"] for a in filtered)
    count = len(filtered)
    
    stats_text = (
        f"📊 Статистика за {period}:\n"
        f"Количество записей: {count}\n"
        f"Среднее настроение: {total_feeling/count:.1f}/5\n"
        f"Средняя тревога: {total_anxiety/count:.1f}/5\n"
        f"Дней с агрессией: {total_aggression}"
    )
    await callback.message.edit_text(stats_text)
    await callback.answer()

# ---------- Запуск ежедневного опроса ----------
async def send_daily_poll(user_id):
    """Отправляет пользователю первый вопрос опроса"""
    # Проверяем, не проходит ли он уже опрос (чтобы не наслаивать)
    if user_id in poll_states:
        return
    poll_states[user_id] = {
        "step": 0,
        "answers": {}
    }
    await bot.send_message(
        user_id,
        QUESTIONS[0]["text"],
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

# Планировщик для отправки опросов всем пользователям
scheduler = AsyncIOScheduler()

async def scheduled_polls():
    """Функция, которая запускается по расписанию и отправляет опрос всем, кто не проходил сегодня"""
    users = db.load_data()
    now = datetime.now()
    for user_id_str, data in users.items():
        last_poll = data.get("last_poll_time")
        # Если последний опрос был не сегодня, отправляем новый
        if last_poll is None or datetime.fromisoformat(last_poll).date() < now.date():
            await send_daily_poll(int(user_id_str))

# ---------- Обработка ответов на вопросы ----------
@dp.message()
async def handle_poll_answer(message: types.Message):
    user_id = message.from_user.id
    # Проверяем, находится ли пользователь в процессе опроса
    if user_id not in poll_states:
        # Если не в опросе, просто игнорируем или можно предложить меню
        await message.answer("Используйте кнопки меню.", reply_markup=get_main_keyboard())
        return
    
    state = poll_states[user_id]
    step = state["step"]
    question = QUESTIONS[step]
    answer_text = message.text.strip()
    
    # Валидация ответа (число и в нужном диапазоне)
    try:
        value = int(answer_text)
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
        return
    
    if question["type"] == "scale" and (value < question["min"] or value > question["max"]):
        await message.answer(f"Введите число от {question['min']} до {question['max']}.")
        return
    elif question["type"] == "binary" and value not in (0, 1):
        await message.answer("Введите 0 (нет) или 1 (да).")
        return
    
    # Сохраняем ответ
    state["answers"][question["key"]] = value
    
    # Переходим к следующему вопросу или завершаем
    next_step = step + 1
    if next_step < len(QUESTIONS):
        state["step"] = next_step
        await message.answer(
            QUESTIONS[next_step]["text"],
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
    else:
        # Опрос завершён
        # Сохраняем ответы в базу
        user_data = db.get_user(user_id)
        answers = user_data.get("answers", [])
        now = datetime.now().isoformat()
        answers.append({
            "date": now,
            **state["answers"]
        })
        db.update_user(user_id, {"answers": answers, "last_poll_time": now})
        
        # Удаляем состояние
        del poll_states[user_id]
        
        # Простой анализ и рекомендация
        feeling = state["answers"]["feeling"]
        anxiety = state["answers"]["anxiety"]
        aggression = state["answers"]["aggression"]
        
        advice = ""
        if feeling <= 2:
            advice += "Ваше настроение низкое. Попробуйте сделать что-то приятное для себя.\n"
        if anxiety >= 4:
            advice += "Уровень тревоги высокий. Рекомендую дыхательное упражнение 4-7-8.\n"
        if aggression == 1:
            advice += "Была агрессия. Попробуйте физическую активность или дневник эмоций.\n"
        
        if not advice:
            advice = "У вас всё хорошо! Так держать."
        
        await message.answer(
            f"Спасибо за ответы!\n{advice}",
            reply_markup=get_main_keyboard()
        )

# ---------- Запуск бота ----------
async def main():
    # Настраиваем планировщик: запускать опросы каждый день в 10:00 утра
    scheduler.add_job(scheduled_polls, trigger=IntervalTrigger(hours=24), id="daily_polls", replace_existing=True)
    scheduler.start()
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
