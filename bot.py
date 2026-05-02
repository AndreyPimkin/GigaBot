import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from dotenv import load_dotenv

from database import Database
from llm_client import LLMClient, LLMError

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not found in .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()
llm = LLMClient()

# 🔘 Кнопка внизу чата
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="📜 История")]],
    resize_keyboard=True
)


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 Привет! Я чат-бот на базе GigaChat.\n"
        "Просто напиши сообщение, или нажми кнопку ниже.",
        reply_markup=main_keyboard
    )


@dp.message(Command("history"))
@dp.message(lambda msg: msg.text == "📜 История")
async def cmd_history(message: types.Message):
    chat_id = str(message.chat.id)
    history = await db.get_history(chat_id, limit=10)
    if not history:
        await message.answer("📭 История переписки пуста.", reply_markup=main_keyboard)
        return

    text = "📜 Ваша история:\n\n"
    for h in history:
        user_msg = h["user_message"][:60] + ("..." if len(h["user_message"]) > 60 else "")
        bot_msg = h["bot_response"][:100] + ("..." if len(h["bot_response"]) > 100 else "")
        text += f"👤 Вы: {user_msg}\n🤖 Бот: {bot_msg}\n\n"

    await message.answer(text[:4000], reply_markup=main_keyboard)


@dp.message()
async def handle_user_message(message: types.Message):
    if not message.text:
        return

    chat_id = str(message.chat.id)
    username = message.from_user.username or "User"
    user_text = message.text.strip()

    await bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        history = await db.get_history(chat_id, limit=10)
        response = await llm.generate_response(user_text, history)
        await db.save_message(chat_id, username, user_text, response)
        await message.answer(response, reply_markup=main_keyboard)
    except LLMError as e:
        await message.answer(f"⚠️ Ошибка нейросети: {e}", reply_markup=main_keyboard)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.answer("❌ Произошла внутренняя ошибка. Попробуйте позже.", reply_markup=main_keyboard)


async def main():
    await db.connect()
    logger.info("Bot is starting...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())