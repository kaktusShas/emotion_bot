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

# Включаем логирование
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
    kb.button(text="📝 Глубокий опрос")   # <-- Новая кнопка
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

# ---------- Вопросы для ежедневного опроса (остаются без изменений) ----------
QUESTIONS = [
    {"text": "Как вы себя чувствуете сегодня? (1 - ужасно, 5 - отлично)", "key": "feeling", "type": "scale", "min":1, "max":5},
    {"text": "Оцените уровень тревоги (1 - нет, 5 - очень высокая)", "key": "anxiety", "type": "scale", "min":1, "max":5},
    {"text": "Были ли сегодня вспышки агрессии? (0 - нет, 1 - да)", "key": "aggression", "type": "binary"},
]

# ---------- Вопросы для глубокого опроса ----------
DEEP_QUESTIONS = [
    {"text": "Как вы оцениваете свою энергию сегодня? (1 - совсем нет сил, 5 - очень энергичен)", "key": "energy", "type": "scale", "min":1, "max":5},
    {"text": "Чувствуете ли вы апатию, безразличие? (1 - нет, 5 - очень сильная апатия)", "key": "apathy", "type": "scale", "min":1, "max":5},
    {"text": "Оцените уровень агрессии (1 - нет, 5 - очень агрессивен)", "key": "aggression", "type": "scale", "min":1, "max":5},
    {"text": "Как сильно вы раздражены? (1 - нет, 5 - постоянно раздражён)", "key": "irritation", "type": "scale", "min":1, "max":5},
    {"text": "Оцените уровень тревожности (1 - нет, 5 - очень высокая)", "key": "anxiety", "type": "scale", "min":1, "max":5},
]

# Хранилище состояний опроса: user_id -> {"step": int, "answers": dict, "type": "daily"/"deep"}
poll_states = {}

# ---------- Команда /start ----------
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    db.get_user(user_id)  # инициализируем пользователя
    await message.answer(
        "Привет! Я бот для отслеживания эмоционального состояния.\n"
        "Каждый день я буду задавать несколько вопросов, чтобы оценить ваше самочувствие.\n"
        "Вы также можете пройти глубокий опрос, тест или посмотреть статистику.",
        reply_markup=get_main_keyboard()
    )

# ---------- Обработка главного меню ----------
@dp.message(lambda msg: msg.text == "📊 Статистика")
async def stats_menu(message: types.Message):
    await message.answer("Выберите период:", reply_markup=get_stats_period_keyboard())

@dp.message(lambda msg: msg.text == "🧪 Пройти тест")
async def test_menu(message: types.Message):
    await message.answer("Выберите тест:\n1. Тест на тревожность (GAD-7) – скоро будет...\nПока просто команда /test для демо")

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

# ---------- НОВОЕ: Обработка кнопки глубокого опроса ----------
@dp.message(lambda msg: msg.text == "📝 Глубокий опрос")
async def deep_poll_start(message: types.Message):
    user_id = message.from_user.id
    # Если пользователь уже в процессе опроса, можно предупредить, но для простоты просто начнём заново
    if user_id in poll_states:
        await message.answer("Предыдущий опрос прерван. Начинаем глубокий опрос.")
    # Запускаем глубокий опрос
    poll_states[user_id] = {
        "step": 0,
        "answers": {},
        "type": "deep"
    }
    await message.answer(
        DEEP_QUESTIONS[0]["text"],
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(str(i)) for i in range(1, 6)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

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
    filtered = []
    for a in answers:
        # Поддержка старых записей (без поля date? но они должны быть)
        if "date" in a:
            try:
                d = datetime.fromisoformat(a["date"])
                if d >= start_date:
                    filtered.append(a)
            except:
                continue
        else:
            # Если нет даты, пропускаем
            continue
    
    if not filtered:
        await callback.message.edit_text(f"Нет данных за выбранный период ({period}).")
        await callback.answer()
        return
    
    # Собираем все числовые поля (кроме 'date' и 'type')
    field_values = {}
    for entry in filtered:
        for key, value in entry.items():
            if key in ("date", "type"):
                continue
            # Пытаемся привести к числу (на случай если значение сохранено как строка)
            try:
                val = float(value)
            except (ValueError, TypeError):
                continue
            if key not in field_values:
                field_values[key] = []
            field_values[key].append(val)
    
    # Формируем статистику
    lines = [f"📊 Статистика за {period}:"]
    lines.append(f"Количество записей: {len(filtered)}")
    for key, values in field_values.items():
        avg = sum(values) / len(values)
        # Красивое название поля
        field_names = {
            "feeling": "Настроение",
            "anxiety": "Тревога",
            "aggression": "Агрессия",
            "energy": "Энергия",
            "apathy": "Апатия",
            "irritation": "Раздражение"
        }
        display_name = field_names.get(key, key.capitalize())
        lines.append(f"{display_name}: {avg:.1f}/5")
    
    await callback.message.edit_text("\n".join(lines))
    await callback.answer()

# ---------- Запуск ежедневного опроса (немного изменён: добавляем тип) ----------
async def send_daily_poll(user_id):
    """Отправляет пользователю первый вопрос ежедневного опроса"""
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

# ---------- Обработка ответов на вопросы (обновлена для работы с двумя типами) ----------
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
    poll_type = state.get("type", "daily")  # по умолчанию daily для обратной совместимости
    
    # Выбираем соответствующий список вопросов
    if poll_type == "daily":
        questions = QUESTIONS
    else:
        questions = DEEP_QUESTIONS
    
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
    
    # Переходим к следующему вопросу или завершаем
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
        # Формируем запись для сохранения
        now_iso = datetime.now().isoformat()
        entry = {
            "date": now_iso,
            "type": poll_type,
            **state["answers"]
        }
        
        # Сохраняем в базу
        user_data = db.get_user(user_id)
        answers = user_data.get("answers", [])
        answers.append(entry)
        # Обновляем last_poll_time только для daily опросов? Для статистики можно обновлять всегда, но для расписания важно daily.
        updates = {"answers": answers}
        if poll_type == "daily":
            updates["last_poll_time"] = now_iso
        db.update_user(user_id, updates)
        
        # Удаляем состояние
        del poll_states[user_id]
        
        # Простой анализ и рекомендация (только для daily, для deep можно свой)
        if poll_type == "daily":
            feeling = state["answers"].get("feeling", 3)
            anxiety = state["answers"].get("anxiety", 3)
            aggression = state["answers"].get("aggression", 0)
            
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
        else:
            # Для глубокого опроса можно дать общую обратную связь (по желанию)
            await message.answer(
                "Спасибо за прохождение глубокого опроса! Ваши ответы сохранены.",
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
