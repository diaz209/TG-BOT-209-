import asyncio
import os
import datetime
import aiohttp
import aiosqlite
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

# ================== ЗАГРУЗКА ПЕРЕМЕННЫХ ==================

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
NINJA_API_KEY = os.getenv("OMrT2Uay7xpjuTcK6aFTOZzT0DKHNrNcZaw1bL7v")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

DB_NAME = "fitness.db"

# ================== СОСТОЯНИЯ ==================

class FoodState(StatesGroup):
    waiting_for_food = State()

class GoalState(StatesGroup):
    waiting_for_goal = State()

class WeightState(StatesGroup):
    waiting_for_weight = State()

# ================== КЛАВИАТУРА ==================

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/add_food"), KeyboardButton(text="/my_calories")],
            [KeyboardButton(text="/set_goal"), KeyboardButton(text="/add_weight")],
            [KeyboardButton(text="/profile"), KeyboardButton(text="/bmi")],
            [KeyboardButton(text="/help")]
        ],
        resize_keyboard=True
    )

# ================== БАЗА ДАННЫХ ==================

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            goal INTEGER DEFAULT 2500
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS food_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            food TEXT,
            calories REAL,
            date TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS weight_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            weight REAL,
            date TEXT
        )
        """)
        await db.commit()

async def add_user(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def set_goal_db(user_id, goal):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET goal=? WHERE user_id=?", (goal, user_id))
        await db.commit()

async def get_goal(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT goal FROM users WHERE user_id=?", (user_id,))
        result = await cursor.fetchone()
        return result[0] if result else 2500

async def add_food_db(user_id, food, calories):
    date = str(datetime.date.today())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO food_log (user_id, food, calories, date) VALUES (?, ?, ?, ?)",
            (user_id, food, calories, date)
        )
        await db.commit()

async def get_today_calories(user_id):
    date = str(datetime.date.today())
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT SUM(calories) FROM food_log WHERE user_id=? AND date=?",
            (user_id, date)
        )
        result = await cursor.fetchone()
        return result[0] if result[0] else 0

async def add_weight_db(user_id, weight):
    date = str(datetime.date.today())
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO weight_log (user_id, weight, date) VALUES (?, ?, ?)",
            (user_id, weight, date)
        )
        await db.commit()

# ================== ВНЕШНИЙ API ==================

async def get_food_data(food_name):
    url = "https://api.api-ninjas.com/v1/nutrition"
    headers = {"X-Api-Key": NINJA_API_KEY}
    params = {"query": food_name}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                if not data:
                    return None

                food = data[0]

                return {
                    "calories": food.get("calories", 0),
                    "protein": food.get("protein_g", 0),
                    "fat": food.get("fat_total_g", 0),
                    "carbs": food.get("carbohydrates_total_g", 0)
                }
    except:
        return None

# ================== КОМАНДЫ ==================

@dp.message(Command("start"))
async def start(message: Message):
    await add_user(message.from_user.id)
    await message.answer("💪 Fitness Bot запущен!", reply_markup=main_menu())

@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("""
/add_food – добавить еду
/my_calories – калории за сегодня
/set_goal – установить цель
/add_weight – записать вес
/profile – профиль
/bmi – расчет BMI
""")

@dp.message(Command("set_goal"))
async def set_goal(message: Message, state: FSMContext):
    await message.answer("Введите цель калорий:")
    await state.set_state(GoalState.waiting_for_goal)

@dp.message(GoalState.waiting_for_goal)
async def process_goal(message: Message, state: FSMContext):
    try:
        goal = int(message.text)
        await set_goal_db(message.from_user.id, goal)
        await message.answer("🎯 Цель обновлена!")
    except:
        await message.answer("Введите число.")
    await state.clear()

@dp.message(Command("add_food"))
async def add_food(message: Message, state: FSMContext):
    await message.answer("Введите продукт (например: 200g chicken)")
    await state.set_state(FoodState.waiting_for_food)

@dp.message(FoodState.waiting_for_food)
async def process_food(message: Message, state: FSMContext):
    data = await get_food_data(message.text)

    if data is None:
        await message.answer("Ошибка API или продукт не найден.")
    else:
        await add_food_db(message.from_user.id, message.text, data["calories"])
        await message.answer(
            f"🍽 {message.text}\n"
            f"🔥 Калории: {data['calories']}\n"
            f"🥩 Белки: {data['protein']} г\n"
            f"🥑 Жиры: {data['fat']} г\n"
            f"🍞 Углеводы: {data['carbs']} г"
        )
    await state.clear()

@dp.message(Command("my_calories"))
async def my_calories(message: Message):
    total = await get_today_calories(message.from_user.id)
    goal = await get_goal(message.from_user.id)
    await message.answer(f"Сегодня: {total} ккал\nЦель: {goal} ккал")

@dp.message(Command("add_weight"))
async def add_weight(message: Message, state: FSMContext):
    await message.answer("Введите ваш вес:")
    await state.set_state(WeightState.waiting_for_weight)

@dp.message(WeightState.waiting_for_weight)
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text)
        await add_weight_db(message.from_user.id, weight)
        await message.answer("Вес сохранён ✅")
    except:
        await message.answer("Введите число.")
    await state.clear()

@dp.message(Command("profile"))
async def profile(message: Message):
    goal = await get_goal(message.from_user.id)
    await message.answer(f"Ваш ID: {message.from_user.id}\nЦель: {goal} ккал")

@dp.message(Command("bmi"))
async def bmi(message: Message):
    await message.answer("Введите вес и рост через пробел (пример: 70 175)")

@dp.message(F.text.regexp(r"^\d+\s\d+$"))
async def calculate_bmi(message: Message):
    weight, height = map(int, message.text.split())
    height = height / 100
    bmi_value = weight / (height ** 2)
    await message.answer(f"Ваш BMI: {round(bmi_value, 2)}")

# ================== ЗАПУСК ==================

async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
