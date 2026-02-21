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

logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.BOT_TOKEN)
dp = Dispatcher()

# ---------- Клавиатуры ----------
def get_main_keyboard():
    """Главная клавиатура с кнопками"""
    kb = ReplyKeyboardBuilder()
    kb.button(text="📊 Статистика")
    kb.button(text="🧪 Пройти тест")
    kb.button(text="💡 Методики")
    kb.button(text="📝 Опрос состояния")   # <-- Исправленное название
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)

def get_stats_period_keyboard():
    """Инлайн-клавиатура для выбора периода статистики"""
    buttons = [
        [InlineKeyboardButton(text="День", callback_data="stats_day"),
         InlineKeyboardButton(text="Неделя", callback_data="stats_week"),
         InlineKeyboardButton(text="Месяц", callback_data="stats_month")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ---------- Ежедневный опрос (короткий) ----------
QUESTIONS = [
    {"text": "Как вы себя чувствуете сегодня? (1 - ужасно, 5 - отлично)", "key": "feeling", "type": "scale", "min":1, "max":5},
    {"text": "Оцените уровень тревоги (1 - нет, 5 - очень высокая)", "key": "anxiety", "type": "scale", "min":1, "max":5},
    {"text": "Были ли сегодня вспышки агрессии? (0 - нет, 1 - да)", "key": "aggression", "type": "binary"},
]

# ---------- НОВЫЙ опрос состояния (психологический, с кнопками 1-5) ----------
STATE_QUESTIONS = [
    {
        "text": "🔋 Энергия: Как вы оцениваете свой уровень энергии сейчас? (1 - полный упадок сил, 5 - очень энергичен)",
        "key": "energy",
        "type": "scale",
        "min": 1,
        "max": 5
    },
    {
        "text": "😶 Апатия: Чувствуете ли вы безразличие, отсутствие интереса к происходящему? (1 - нет, 5 - полная апатия)",
        "key": "apathy",
        "type": "scale",
        "min": 1,
        "max": 5
    },
    {
        "text": "🤬 Агрессия: Оцените свою раздражительность и склонность к гневу в последнее время (1 - спокоен, 5 - очень агрессивен)",
        "key": "aggression",
        "type": "scale",
        "min": 1,
        "max": 5
    },
    {
        "text": "😤 Раздражение: Как часто вы замечаете, что вас раздражают мелочи? (1 - редко, 5 - постоянно)",
        "key": "irritation",
        "type": "scale",
        "min": 1,
        "max": 5
    },
    {
        "text": "😰 Тревожность: Оцените уровень своей тревоги и беспокойства (1 - нет, 5 - очень высокая тревога)",
        "key": "anxiety",
        "type": "scale",
        "min": 1,
        "max": 5
    }
]

# Хранилище состояний опроса
poll_states = {}

# ---------- Команда /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    db.get_user(user_id)
    await message.answer(
        "Привет! Я бот для отслеживания эмоционального состояния.\n"
        "Каждый день я буду задавать несколько вопросов.\n"
        "Вы также можете пройти развёрнутый опрос состояния, тест или посмотреть статистику.",
        reply_markup=get_main_keyboard()
    )

# ---------- Обработка главного меню ----------
@dp.message(lambda msg: msg.text == "📊 Статистика")
async def stats_menu(message: types.Message):
    await message.answer("Выберите период:", reply_markup=get_stats_period_keyboard())

@dp.message(lambda msg: msg.text == "🧪 Пройти тест")
async def test_menu(message: types.Message):
    await message.answer("Раздел тестов в разработке. Скоро здесь появятся GAD-7, PHQ-9 и другие.")

@dp.message(lambda msg: msg.text == "💡 Методики")
async def methods_menu(message: types.Message):
    text = (
        "🧘 **Снижение тревоги:**\n"
        "- Дыхание 4-7-8 (вдох 4 сек, задержка 7, выдох 8)\n"
        "- Прогрессивная мышечная релаксация\n"
        "- Медитация осознанности\n\n"
        "💪 **При агрессии/раздражении:**\n"
        "- Сосчитать до 10\n"
        "- Физическая активность (приседания, прогулка)\n"
        "- Дневник эмоций (записать, что вызвало гнев)\n\n"
        "😴 **При апатии и упадке энергии:**\n"
        "- Разбить дела на маленькие шаги\n"
        "- 5-минутное правило (начать делать что-то на 5 минут)\n"
        "- Побыть на солнце или включить яркий свет"
    )
    await message.answer(text)

# ---------- Запуск опроса состояния (по кнопке) ----------
@dp.message(lambda msg: msg.text == "📝 Опрос состояния")
async def state_poll_start(message: types.Message):
    user_id = message.from_user.id
    if user_id in poll_states:
        await message.answer("Предыдущий опрос прерван. Начинаем новый.")
    
    poll_states[user_id] = {
        "step": 0,
        "answers": {},
        "type": "state"  # новый тип опроса
    }
    # Отправляем первый вопрос с кнопками 1-5
    await message.answer(
        STATE_QUESTIONS[0]["text"],
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

# ---------- Обработка инлайн-кнопок (статистика) ----------
@dp.callback_query(lambda c: c.data.startswith("stats_"))
async def process_stats_callback(callback: types.CallbackQuery):
    period = callback.data.split("_")[1]
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
    else:
        start_date = now - timedelta(days=30)
    
    filtered = []
    for a in answers:
        if "date" in a:
            try:
                d = datetime.fromisoformat(a["date"])
                if d >= start_date:
                    filtered.append(a)
            except:
                continue
    
    if not filtered:
        await callback.message.edit_text(f"Нет данных за выбранный период ({period}).")
        await callback.answer()
        return
    
    # Собираем все числовые поля
    field_values = {}
    for entry in filtered:
        for key, value in entry.items():
            if key in ("date", "type"):
                continue
            try:
                val = float(value)
            except (ValueError, TypeError):
                continue
            if key not in field_values:
                field_values[key] = []
            field_values[key].append(val)
    
    lines = [f"📊 Статистика за {period}:"]
    lines.append(f"Количество записей: {len(filtered)}")
    
    # Словарь для красивых названий
    field_names = {
        "feeling": "Настроение",
        "anxiety": "Тревога",
        "aggression": "Агрессия",
        "energy": "Энергия",
        "apathy": "Апатия",
        "irritation": "Раздражение"
    }
    
    for key, values in field_values.items():
        avg = sum(values) / len(values)
        display_name = field_names.get(key, key.capitalize())
        lines.append(f"{display_name}: {avg:.1f}/5")
    
    await callback.message.edit_text("\n".join(lines))
    await callback.answer()

# ---------- Ежедневный опрос (автоматический) ----------
async def send_daily_poll(user_id):
    if user_id in poll_states:
        return
    poll_states[user_id] = {
        "step": 0,
        "answers": {},
        "type": "daily"
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

scheduler = AsyncIOScheduler()

async def scheduled_polls():
    users = db.load_data()
    now = datetime.now()
    for user_id_str, data in users.items():
        last_poll = data.get("last_poll_time")
        if last_poll is None or datetime.fromisoformat(last_poll).date() < now.date():
            await send_daily_poll(int(user_id_str))

# ---------- Обработка ответов на вопросы (универсальная) ----------
@dp.message()
async def handle_poll_answer(message: types.Message):
    user_id = message.from_user.id
    if user_id not in poll_states:
        await message.answer("Используйте кнопки меню.", reply_markup=get_main_keyboard())
        return
    
    state = poll_states[user_id]
    step = state["step"]
    poll_type = state.get("type", "daily")
    
    # Выбираем нужный список вопросов
    if poll_type == "daily":
        questions = QUESTIONS
    elif poll_type == "state":
        questions = STATE_QUESTIONS
    else:
        questions = QUESTIONS
    
    question = questions[step]
    answer_text = message.text.strip()
    
    # Валидация ответа
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
    
    # Следующий вопрос или завершение
    next_step = step + 1
    if next_step < len(questions):
        state["step"] = next_step
        await message.answer(
            questions[next_step]["text"],
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
    else:
        # Опрос завершён
        now_iso = datetime.now().isoformat()
        entry = {
            "date": now_iso,
            "type": poll_type,
            **state["answers"]
        }
        
        user_data = db.get_user(user_id)
        answers = user_data.get("answers", [])
        answers.append(entry)
        
        updates = {"answers": answers}
        if poll_type == "daily":
            updates["last_poll_time"] = now_iso
        
        db.update_user(user_id, updates)
        del poll_states[user_id]
        
        # Персональная рекомендация (только для daily)
        if poll_type == "daily":
            feeling = state["answers"].get("feeling", 3)
            anxiety = state["answers"].get("anxiety", 3)
            aggression = state["answers"].get("aggression", 0)
            
            advice = ""
            if feeling <= 2:
                advice += "❗ Настроение низкое. Попробуйте сделать что-то приятное.\n"
            if anxiety >= 4:
                advice += "😰 Тревога высокая. Сделайте дыхательное упражнение.\n"
            if aggression == 1:
                advice += "😤 Была агрессия. Попробуйте физическую активность.\n"
            
            if not advice:
                advice = "✅ У вас всё хорошо! Так держать."
            
            await message.answer(
                f"Спасибо за ответы!\n{advice}",
                reply_markup=get_main_keyboard()
            )
        else:
            await message.answer(
                "✅ Спасибо за прохождение опроса! Ваши ответы сохранены.",
                reply_markup=get_main_keyboard()
            )

# ---------- Запуск ----------
async def main():
    scheduler.add_job(scheduled_polls, trigger=IntervalTrigger(hours=24), id="daily_polls", replace_existing=True)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
