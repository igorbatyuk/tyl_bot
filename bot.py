import logging
import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from dotenv import load_dotenv
from db import init_db, add_or_update_user, get_user_full_info, subtract_balance
from operator_menu import operator_menu, OPERATOR_ID, operator_router, get_operator_inline_menu
from monobank_payments import start_payment_checker
from openai_service import get_service_response, clear_user_thread, validate_message
from rate_limiter import message_rate_limiter, service_rate_limiter
from additional_improvements import (
    user_request_lock, 
    balance_cache, 
    deduction_tracker
)
from ux_improvements import (
    format_balance_message,
    format_service_info,
    format_user_stats,
    format_payment_instructions,
    get_quick_actions_keyboard,
    get_help_tips
)
import uuid

load_dotenv()

API_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', '-4647978421'))

if not API_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не встановлено в .env файлі")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
dp.include_router(operator_router)

try:
    init_db()
    logger.info("База даних ініціалізована успішно")
except Exception as e:
    logger.error(f"Помилка ініціалізації БД: {e}")
    raise

class ServiceStates(StatesGroup):
    waiting_for_question = State()
    in_conversation = State()

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏢 Служби"), KeyboardButton(text="💳 Поповнити")],
        [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="ℹ️ Про бота"), KeyboardButton(text="👨‍💼 Оператор")]
    ],
    resize_keyboard=True
)

services_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⛽️ ПММ"), KeyboardButton(text="👕 Речова"), KeyboardButton(text="🍲 Продовольча")],
        [KeyboardButton(text="🏠 Меню")]
    ],
    resize_keyboard=True
)

exit_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏠 Меню")]
    ],
    resize_keyboard=True
)

info_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📖 Як користуватись"), KeyboardButton(text="📚 Джерела")],
        [KeyboardButton(text="🏠 Меню")]
    ],
    resize_keyboard=True
)

async def notify_group(text: str):
    try:
        await bot.send_message(GROUP_CHAT_ID, text)
    except Exception as e:
        logger.error(f"Не вдалося надіслати повідомлення у групу: {e}")

def is_user_blocked(user_id):
    if not isinstance(user_id, int) or user_id <= 0:
        return False
    user = get_user_full_info(user_id)
    return user and user[10] == 1

async def check_rate_limit(user_id: int, limiter) -> tuple[bool, str]:
    is_allowed, wait_time = limiter.is_allowed(user_id)
    if not is_allowed:
        return False, f"⏳ Ви надто часто надсилаєте запити. Спробуйте через {wait_time} секунд."
    return True, ""

@dp.message(Command("start"))
async def send_welcome(message: types.Message, state: FSMContext):
    is_allowed, error_msg = await check_rate_limit(message.from_user.id, message_rate_limiter)
    if not is_allowed:
        await message.answer(error_msg)
        return
    
    await state.clear()
    try:
        is_new = add_or_update_user(message.from_user)
        name = message.from_user.first_name or "користувач"
        if is_new:
            user = message.from_user
            from datetime import datetime
            reg_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            new_user_text = (
                f"👤 Новий користувач\n"
                f"ID: {user.id}\n"
                f"Username: @{user.username if user.username else '-'}\n"
                f"Ім'я: {user.first_name} {user.last_name or ''}\n"
                f"Час: {reg_time}"
            )
            await notify_group(new_user_text)
        if message.from_user.id == OPERATOR_ID:
            await message.answer(
                f"Вітаю, операторе! Оберіть дію:",
                reply_markup=get_operator_inline_menu()
            )
        else:
            if is_user_blocked(message.from_user.id):
                await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
                return
            from db import get_balance
            balance = get_balance(message.from_user.id)
            
            await message.answer(
                f"Вітаю, {name}! 👋\n\n"
                "Я ваш помічник у тиловому забезпеченні ЗСУ.\n\n"
                "Я допоможу швидко знайти відповіді на питання щодо:\n"
                "⛽️ ПММ (пальне та мастильні матеріали)\n"
                "🍲 Продовольчого забезпечення\n"
                "👕 Речового забезпечення\n\n"
                f"{format_balance_message(balance)}\n\n"
                "Обирайте дію нижче ⬇️",
                reply_markup=main_menu,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Помилка в send_welcome для користувача {message.from_user.id}: {e}", exc_info=True)
        await message.answer("❌ Помилка при обробці запиту. Спробуйте пізніше.")

@dp.message(lambda m: m.text == "🏠 Меню")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    add_or_update_user(message.from_user)
    if message.from_user.id == OPERATOR_ID:
        await message.answer("Меню оператора:", reply_markup=get_operator_inline_menu())
    else:
        if is_user_blocked(message.from_user.id):
            await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
            return
        from db import get_balance
        balance = get_balance(message.from_user.id)
        await message.answer(
            f"🏠 <b>Головне меню</b>\n\n{format_balance_message(balance)}",
            reply_markup=main_menu,
            parse_mode="HTML"
        )

@dp.message(lambda m: m.text == "🏢 Служби")
async def choose_service(message: types.Message, state: FSMContext):
    await state.clear()
    add_or_update_user(message.from_user)
    if is_user_blocked(message.from_user.id):
        await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
        return
    await message.answer(
        "Оберіть службу:\n\n"
        "⛽️ <b>ПММ</b> - питання щодо палива та мастильних матеріалів\n"
        "🍲 <b>Продовольча</b> - питання щодо харчування та продовольства\n"
        "👕 <b>Речова</b> - питання щодо речового забезпечення",
        reply_markup=services_menu,
        parse_mode="HTML"
    )

@dp.message(lambda m: m.text in ["⛽️ ПММ", "👕 Речова", "🍲 Продовольча"])
async def service_selected(message: types.Message, state: FSMContext):
    add_or_update_user(message.from_user)
    if is_user_blocked(message.from_user.id):
        await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
        return
    
    user = get_user_full_info(message.from_user.id)
    if user[6] <= 0:
        await message.answer(
            "❌ У вас недостатньо запитів для використання служби.\n"
            "Будь ласка, поповніть баланс через меню '💳 Поповнити'",
            reply_markup=main_menu
        )
        return
    
    await state.set_state(ServiceStates.waiting_for_question)
    await state.update_data(service=message.text, balance=user[6])
    
    await message.answer(
        format_service_info(message.text, user[6]),
        reply_markup=exit_menu,
        parse_mode="HTML"
    )
    
    await message.answer(
        get_help_tips(),
        reply_markup=exit_menu,
        parse_mode="HTML"
    )

@dp.message(ServiceStates.waiting_for_question)
async def handle_question(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    request_id = str(uuid.uuid4())
    
    try:
        if not await user_request_lock.acquire(user_id):
            await message.answer(
                "⏳ Ваш попередній запит ще обробляється. Будь ласка, зачекайте."
            )
            return
        
        try:
            is_allowed, error_msg = await check_rate_limit(user_id, service_rate_limiter)
            if not is_allowed:
                await message.answer(error_msg)
                return
            
            if message.text == "🏠 Меню":
                await state.clear()
                await clear_user_thread(user_id)
                await back_to_main(message, state)
                return

            if not message.text:
                await message.answer("❌ Будь ласка, надішліть текстове повідомлення.")
                return
            
            is_valid, validation_error = validate_message(message.text)
            if not is_valid:
                await message.answer(f"❌ {validation_error}")
                return

            data = await state.get_data()
            service = data.get('service')

            cached_balance = balance_cache.get(user_id)
            if cached_balance is not None:
                balance = cached_balance
            else:
                user = get_user_full_info(user_id)
                if not user or user[6] <= 0:
                    await message.answer(
                        "❌ У вас закінчились запити. Будь ласка, поповніть баланс.",
                        reply_markup=InlineKeyboardMarkup(
                            inline_keyboard=[[
                                InlineKeyboardButton(text="💳 Поповнити баланс", callback_data="top_up_balance")
                            ]]
                        )
                    )
                    return
                balance = user[6]
                balance_cache.set(user_id, balance)

            if balance <= 0:
                await message.answer(
                    "❌ У вас закінчились запити. Будь ласка, поповніть баланс.",
                    reply_markup=InlineKeyboardMarkup(
                        inline_keyboard=[[
                            InlineKeyboardButton(text="💳 Поповнити баланс", callback_data="top_up_balance")
                        ]]
                    )
                )
                return

            if not deduction_tracker.start_deduction(user_id, request_id):
                await message.answer("⏳ Ваш попередній запит ще обробляється. Будь ласка, зачекайте.")
                return

            processing_msg = await message.answer(
                f"⏳ <b>Обробляю ваш запит...</b>\n\n"
                f"📋 Служба: {service}\n"
                f"⏱ Це може зайняти 10-30 секунд\n"
                f"💡 Будь ласка, зачекайте...",
                parse_mode="HTML"
            )

            response = await get_service_response(service, message.text, user_id)

            try:
                await processing_msg.delete()
            except Exception:
                pass

            max_response_length = 4000
            if len(response) > max_response_length:
                response = response[:max_response_length] + "\n\n... (відповідь обрізано)"
            
            final_response = (
                f"📋 <b>Відповідь від служби {service}:</b>\n\n"
                f"{response.strip()}\n\n"
                f"💬 <i>Якщо бажаєте продовжити — напишіть нове питання</i>\n"
                f"🏠 <i>Або поверніться в меню</i>"
            )
            
            if len(final_response) > 4000:
                chunks = [final_response[i:i+4000] for i in range(0, len(final_response), 4000)]
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        await message.answer(chunk, parse_mode="HTML")
                    else:
                        await message.answer(chunk, parse_mode="HTML")
            else:
                await message.answer(final_response, parse_mode="HTML")

            if not response.startswith("❌"):
                try:
                    subtract_balance(user_id, 1)
                    new_balance = balance - 1
                    balance_cache.set(user_id, new_balance)
                    deduction_tracker.complete_deduction(user_id, request_id)
                    await state.update_data(balance=new_balance)
                    
                    await message.answer(
                        format_balance_message(new_balance),
                        parse_mode="HTML"
                    )
                except ValueError as e:
                    logger.warning(f"Не вдалося списати баланс для {user_id}: {e}")
                    deduction_tracker.cancel_deduction(user_id)
                    await message.answer(
                        "❌ Не вдалося списати баланс. Можливо, баланс змінився. Перевірте баланс."
                    )
            else:
                deduction_tracker.cancel_deduction(user_id)
        
        finally:
            user_request_lock.release(user_id)
    except Exception as e:
        logger.error(f"Помилка при обробці запиту для користувача {message.from_user.id}: {e}", exc_info=True)
        user = message.from_user
        error_text = (
            f"❗️ Помилка у користувача\n"
            f"ID: {user.id}\n"
            f"Username: @{user.username if user.username else '-'}\n"
            f"Ім'я: {user.first_name} {user.last_name or ''}\n"
            f"Текст: {message.text[:200] if message.text else 'N/A'}\n"
            f"Помилка: {e}"
        )
        await notify_group(error_text)
        await message.answer(
            "❌ Помилка при обробці запиту. Спробуйте пізніше.",
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="🏠 Меню")]],
                resize_keyboard=True
            )
        )

@dp.message(lambda m: m.text == "💳 Поповнити")
async def top_up(message: types.Message):
    is_allowed, error_msg = await check_rate_limit(message.from_user.id, message_rate_limiter)
    if not is_allowed:
        await message.answer(error_msg)
        return
    
    try:
        add_or_update_user(message.from_user)
        if is_user_blocked(message.from_user.id):
            await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
            return
        user_id = message.from_user.id
        username = message.from_user.username
        identifier = f"@{username}" if username else str(user_id)
        
        card_number = os.getenv('MONOBANK_CARD_NUMBER', '4441 1144 1990 5094')
        
        await message.answer(
            format_payment_instructions(card_number, identifier, bool(username)),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в top_up для користувача {message.from_user.id}: {e}", exc_info=True)
        await message.answer("❌ Помилка при обробці запиту. Спробуйте пізніше.")

@dp.message(lambda m: m.text == "💰 Баланс")
async def check_balance(message: types.Message):
    is_allowed, error_msg = await check_rate_limit(message.from_user.id, message_rate_limiter)
    if not is_allowed:
        await message.answer(error_msg)
        return
    
    try:
        add_or_update_user(message.from_user)
        if is_user_blocked(message.from_user.id):
            await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
            return
        
        cached_balance = balance_cache.get(message.from_user.id)
        if cached_balance is not None:
            balance = cached_balance
        else:
            from db import get_balance
            balance = get_balance(message.from_user.id)
            balance_cache.set(message.from_user.id, balance)
        
        user = get_user_full_info(message.from_user.id)
        name = message.from_user.first_name or "Користувач"
        username = message.from_user.username or "немає"
        join_date = user[5] if user and user[5] else "Невідомо"
        
        await message.answer(
            format_balance_message(balance, name),
            parse_mode="HTML"
        )
        
        await message.answer(
            f"👤 <b>Інформація про акаунт:</b>\n"
            f"• Ім'я: {name}\n"
            f"• Username: @{username}\n"
            f"• Дата приєднання: {join_date}",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в check_balance для користувача {message.from_user.id}: {e}", exc_info=True)
        await message.answer("❌ Помилка при отриманні балансу. Спробуйте пізніше.")

@dp.message(lambda m: m.text == "ℹ️ Про бота")
async def about_bot(message: types.Message):
    add_or_update_user(message.from_user)
    if is_user_blocked(message.from_user.id):
        await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
        return
    await message.answer(
        "📌 Що таке 'Тиловий Асистент'?\n"
        "'Тиловий Асистент' — це чат-бот для військовослужбовців, які працюють у сфері тилового забезпечення.\n"
        "Він допомагає орієнтуватися в нормативних документах та швидко знаходити відповіді на службові питання по таких напрямках:\n\n"
        "🛢 Служба ПММ (пальне та мастильні матеріали)\n"
        "🍞 Продовольча служба\n"
        "🧥 Речове забезпечення\n\n"
        "Бот працює 24/7 та надає відповіді виключно на основі чинних офіційних документів.\n\n"
        "Оберіть розділ:",
        reply_markup=info_menu
    )

@dp.message(lambda m: m.text == "📖 Як користуватись")
async def how_to_use(message: types.Message):
    await message.answer(
        "🔍 Як працює бот?\n"
        "Ви ставите запитання у звичній, зрозумілій вам формі.\n"
        "Бот аналізує ваше питання та знаходить відповідь згідно з нормативними актами.\n"
        "Якщо потрібно — бот надає пояснення, приклад або алгоритм дій.\n\n"
        "✅ Як ставити питання правильно?\n"
        "Щоб бот дав найточнішу відповідь, дотримуйтесь таких порад:\n\n"
        "💡 1. Формулюйте чітко\n"
        "Добре: Яка норма видачі пального для ЗІЛ-131?\n"
        "Погано: Скільки солярки?\n\n"
        "💡 2. Додавайте деталі\n"
        "Тип майна / техніки / ситуації\n"
        "Період (літо / зима / навчання / бойові дії)\n"
        "Вашу роль (комірник, начальник служби тощо)\n\n"
        "Приклад:\n"
        "Як списати пальне в підрозділі які документи потрібно оформити розпиши повну процедуру зсилаючись на джерела відповідно якого наказу я маю це робити?\n\n"
        "💡 3. Уникайте загальних фраз\n"
        "Питання типу 'Що по речовці?' — не дають змоги дати корисну відповідь.\n\n"
        "💬 Що ще варто знати:\n"
        "Бот не вигадує — відповідає лише за документами.\n"
        "Якщо щось не зрозуміло — можна переформулювати питання, уточнити деталі.\n"
        "Якщо відповідь не отримана — спробуйте задати більш конкретне або інше формулювання.",
        reply_markup=info_menu
    )

@dp.message(lambda m: m.text == "📚 Джерела")
async def sources(message: types.Message):
    await message.answer(
        "📚 <b>Джерела інформації</b>\n\n"
        "Бот надає відповіді на основі чинних нормативних документів:\n\n"
        "📋 Накази Міністерства оборони України\n"
        "📋 Інструкції та положення\n"
        "📋 Нормативи та стандарти\n"
        "📋 Офіційні методичні рекомендації\n\n"
        "ℹ️ <i>Список конкретних документів буде додано найближчим часом</i>",
        reply_markup=info_menu,
        parse_mode="HTML"
    )

@dp.message(Command("help"))
async def help_command(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "📖 <b>Довідка по боту</b>\n\n"
        "🔹 <b>Основні команди:</b>\n"
        "/start - Початок роботи з ботом\n"
        "/help - Ця довідка\n"
        "/cancel - Скасувати поточну дію\n\n"
        "🔹 <b>Як користуватись:</b>\n"
        "1. Оберіть службу (ПММ, Продовольча, Речова)\n"
        "2. Напишіть ваше питання\n"
        "3. Отримайте відповідь на основі документів\n\n"
        "💡 <b>Поради:</b>\n"
        "• Формулюйте питання чітко та конкретно\n"
        "• Вказуйте деталі (тип техніки, період тощо)\n"
        "• Одне питання за раз\n\n"
        "💰 <b>Баланс:</b>\n"
        "1 запит = 1 питання = 1 грн\n"
        "Поповнюйте баланс через меню '💳 Поповнити'\n\n"
        "👨‍💼 <b>Підтримка:</b>\n"
        "Якщо виникли питання - зверніться до оператора",
        reply_markup=main_menu,
        parse_mode="HTML"
    )

@dp.message(Command("cancel"))
async def cancel_command(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await clear_user_thread(message.from_user.id)
        await message.answer(
            "✅ Дію скасовано. Повертаємось до головного меню.",
            reply_markup=main_menu
        )
    else:
        await message.answer(
            "ℹ️ Немає активної дії для скасування.",
            reply_markup=main_menu
        )

@dp.message(lambda m: m.text == "👨‍💼 Оператор")
async def contact_operator(message: types.Message):
    add_or_update_user(message.from_user)
    if is_user_blocked(message.from_user.id):
        await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
        return
    await message.answer(
        "👨‍💼 <b>Звʼязатись з оператором</b>\n\n"
        "📧 Telegram: @TylBotOperator\n\n"
        "⏰ <b>Графік роботи:</b>\n"
        "Пн-Пт: 8:00 — 17:00\n"
        "Відповідаємо протягом години\n\n"
        "💬 <b>Коли звертатись:</b>\n"
        "• Складні чи нестандартні питання\n"
        "• Проблеми з поповненням балансу\n"
        "• Пропозиції щодо покращення бота\n"
        "• Технічні проблеми\n\n"
        "💡 <i>Маєте ідеї? Обовʼязково діліться!</i>",
        parse_mode="HTML"
    )

@dp.message(lambda m: m.text == "📊 Статистика")
async def show_statistics(message: types.Message):
    is_allowed, error_msg = await check_rate_limit(message.from_user.id, message_rate_limiter)
    if not is_allowed:
        await message.answer(error_msg)
        return
    
    try:
        add_or_update_user(message.from_user)
        if is_user_blocked(message.from_user.id):
            await message.answer("🚫 Ваш акаунт заблоковано оператором. Зверніться до оператора для розблокування.")
            return
        
        user = get_user_full_info(message.from_user.id)
        if not user:
            await message.answer("❌ Помилка отримання статистики. Спробуйте пізніше.")
            return
        
        await message.answer(
            format_user_stats(user),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Помилка в show_statistics для користувача {message.from_user.id}: {e}", exc_info=True)
        await message.answer("❌ Помилка при отриманні статистики. Спробуйте пізніше.")

@dp.callback_query(lambda c: c.data == "top_up_balance")
async def top_up_balance_callback(callback: types.CallbackQuery):
    await callback.answer("Переходимо до поповнення балансу")
    user_id = callback.from_user.id
    username = callback.from_user.username
    identifier = f"@{username}" if username else str(user_id)
    card_number = os.getenv('MONOBANK_CARD_NUMBER', '4441 1144 1990 5094')
    
    await callback.message.answer(
        format_payment_instructions(card_number, identifier, bool(username)),
        parse_mode="HTML"
    )

async def main():
    asyncio.create_task(start_payment_checker())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main()) 