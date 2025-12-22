from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router, F
from aiogram.filters import Command
from aiogram import types
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from db import get_users_page, get_total_users, get_user_full_info, find_user_by_username, find_user_by_id, add_balance, subtract_balance, block_user, unblock_user, get_balance
from aiogram import Bot
from os import getenv

OPERATOR_ID = 8133761847
operator_router = Router()

def get_profile_keyboard(user_id, page, is_blocked):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Поповнити", callback_data=f"op_add_{user_id}_{page}"),
         InlineKeyboardButton(text="➖ Списати", callback_data=f"op_sub_{user_id}_{page}")],
        [InlineKeyboardButton(text="🚫 Заблокувати" if not is_blocked else "✅ Розблокувати", callback_data=f"op_block_{user_id}_{page}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"op_users_{page}"),
         InlineKeyboardButton(text="🏠 Меню", callback_data="op_menu")]
    ])

async def show_user_profile(message_or_callback, user_id, page):
    user = get_user_full_info(user_id)
    if not user:
        await message_or_callback.answer("Користувача не знайдено")
        return
    text = f"👤 <b>Профіль користувача</b>\n"
    text += f"ID: <code>{user[1]}</code>\n"
    if user[2]:
        text += f"Username: @{user[2]}\n"
    text += f"Ім'я: {user[3]} {user[4]}\n"
    text += f"Дата приєднання: {user[5]}\n"
    text += f"Баланс: <b>{user[6]}</b> запитів\n"
    text += f"Використано запитів: <b>{user[11]}</b>\n"
    text += f"Сума поповнень: <b>{user[8]}</b> запитів\n"
    text += f"Останнє поповнення: {user[7] if user[7] else '—'}\n"
    text += f"Остання активність: {user[9] if user[9] else '—'}\n"
    text += f"Статус: {'🚫 Заблокований' if user[10] else '✅ Активний'}\n"
    keyboard = get_profile_keyboard(user[1], page, user[10])
    if isinstance(message_or_callback, types.Message):
        await message_or_callback.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message_or_callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

class SearchUser(StatesGroup):
    waiting_for_query = State()

class ChangeBalance(StatesGroup):
    waiting_for_amount = State()
    action = State()
    user_id = State()
    page = State()

def get_operator_inline_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Список користувачів", callback_data="op_users_1")],
        [InlineKeyboardButton(text="🔎 Пошук користувача", callback_data="op_search")],
        [InlineKeyboardButton(text="ℹ️ Інфо для оператора", callback_data="op_info")]
    ])

def get_users_list_keyboard(page, total_pages, users):
    keyboard = []
    for user in users:
        label = user[1] if user[1] else user[2] or str(user[0])  # username або first_name або id
        keyboard.append([InlineKeyboardButton(text=label, callback_data=f"op_profile_{user[0]}_{page}")])
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Попередня", callback_data=f"op_users_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Наступна", callback_data=f"op_users_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(text="🏠 Меню", callback_data="op_menu")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@operator_router.message(Command("start"))
async def operator_start(message: types.Message, state: FSMContext):
    if message.from_user.id == OPERATOR_ID:
        await state.clear()
        await message.answer(
            "Вітаю, операторе! Оберіть дію:",
            reply_markup=get_operator_inline_menu()
        )

@operator_router.message(F.text == "🏠 Меню")
async def operator_menu(message: types.Message, state: FSMContext):
    if message.from_user.id == OPERATOR_ID:
        await state.clear()
        await message.answer(
            "Меню оператора:",
            reply_markup=get_operator_inline_menu()
        )

@operator_router.callback_query(F.data == "op_search")
async def operator_user_search_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Введіть username (без @) або Telegram ID користувача:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="op_menu")]])
    )
    await state.set_state(SearchUser.waiting_for_query)
    await callback.answer()

@operator_router.message(SearchUser.waiting_for_query)
async def operator_user_search_query(message: types.Message, state: FSMContext):
    query = message.text.strip()
    user = None
    
    if query.startswith('@'):
        query = query[1:]
    
    if query.isdigit():
        user = find_user_by_id(int(query))
    else:
        user = find_user_by_username(query)
    
    if not user:
        await message.answer("Користувача не знайдено. Спробуйте ще раз або поверніться в меню.",
                             reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🏠 Меню", callback_data="op_menu")]]))
        return
    await state.clear()
    await show_user_profile(message, user[0], page=1)

@operator_router.callback_query(F.data.regexp(r"^op_add_\d+_\d+$"))
async def operator_add_balance(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    user_id = int(parts[2])
    page = int(parts[3])
    user = get_user_full_info(user_id)
    if user[10]:
        await callback.answer("Користувач заблокований. Спочатку розблокуйте акаунт.", show_alert=True)
        await show_user_profile(callback, user_id, page)
        return
    await state.set_state(ChangeBalance.waiting_for_amount)
    await state.update_data(action='add', user_id=user_id, page=page)
    await callback.message.edit_text(
        "Введіть суму для поповнення рахунку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"op_profile_{user_id}_{page}"), InlineKeyboardButton(text="🏠 Меню", callback_data="op_menu")]])
    )
    await callback.answer()

@operator_router.callback_query(F.data.regexp(r"^op_sub_\d+_\d+$"))
async def operator_sub_balance(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split('_')
    user_id = int(parts[2])
    page = int(parts[3])
    user = get_user_full_info(user_id)
    if user[10]:
        await callback.answer("Користувач заблокований. Спочатку розблокуйте акаунт.", show_alert=True)
        await show_user_profile(callback, user_id, page)
        return
    await state.set_state(ChangeBalance.waiting_for_amount)
    await state.update_data(action='sub', user_id=user_id, page=page)
    await callback.message.edit_text(
        "Введіть суму для списання з рахунку:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=f"op_profile_{user_id}_{page}"), InlineKeyboardButton(text="🏠 Меню", callback_data="op_menu")]])
    )
    await callback.answer()

@operator_router.message(ChangeBalance.waiting_for_amount)
async def operator_change_balance_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    action = data.get('action')
    user_id = data.get('user_id')
    page = data.get('page')
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введіть коректну суму (ціле число більше 0)")
        return
    if action == 'add':
        add_balance(user_id, amount)
        try:
            bot = Bot(token=getenv('TELEGRAM_BOT_TOKEN'))
            balance = get_balance(user_id)
            text = (
                f"Дякуємо! Ваш рахунок поповнено на {amount} запитів.\n"
                f"Поточний баланс: {balance} запитів.\n"
                f"Приємного користування!"
            )
            await bot.send_message(user_id, text)
        except Exception as e:
            print(f"Не вдалося надіслати повідомлення користувачу: {e}")
        await message.answer(f"✅ Баланс поповнено на {amount} запитів.")
    elif action == 'sub':
        subtract_balance(user_id, amount)
        await message.answer(f"✅ З рахунку списано {amount} запитів.")
    await state.clear()
    await show_user_profile(message, user_id, page)

@operator_router.callback_query(F.data.regexp(r"^op_block_\d+_\d+$"))
async def operator_block_user(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    user_id = int(parts[2])
    page = int(parts[3])
    user = get_user_full_info(user_id)
    bot = Bot(token=getenv('TELEGRAM_BOT_TOKEN'))
    operator_username = '@TylBotOperator'
    if user[10]:
        unblock_user(user_id)
        await callback.answer("Користувача розблоковано")
        try:
            await bot.send_message(user_id, f"✅ Ваш акаунт у боті розблоковано оператором {operator_username}.")
        except Exception:
            pass
    else:
        block_user(user_id)
        await callback.answer("Користувача заблоковано")
        try:
            await bot.send_message(
                user_id,
                f"🚫 Ваш акаунт у боті заблоковано оператором {operator_username}.\n\n"
                "Причина: Порушення правил користування ботом або підозріла активність.\n"
                "Якщо ви вважаєте це помилкою — зверніться до оператора для розблокування."
            )
        except Exception:
            pass
    await show_user_profile(callback, user_id, page)

@operator_router.callback_query(F.data.regexp(r"^op_users_\d+$"))
async def operator_user_list(callback: types.CallbackQuery):
    page = int(callback.data.split('_')[-1])
    per_page = 10
    total = get_total_users()
    total_pages = (total + per_page - 1) // per_page
    users = get_users_page(page, per_page)
    await callback.message.edit_text(
        f"Список користувачів (сторінка {page} з {total_pages}):",
        reply_markup=get_users_list_keyboard(page, total_pages, users)
    )
    await callback.answer()

@operator_router.callback_query(F.data.regexp(r"^op_profile_\d+_\d+$"))
async def operator_user_profile(callback: types.CallbackQuery):
    parts = callback.data.split('_')
    user_id = int(parts[2])
    page = int(parts[3])
    await show_user_profile(callback, user_id, page)
    await callback.answer()

@operator_router.callback_query(F.data == "op_menu")
async def operator_menu_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Меню оператора:",
        reply_markup=get_operator_inline_menu()
    )
    await callback.answer()

@operator_router.callback_query(F.data == "op_info")
async def operator_info(callback: types.CallbackQuery):
    await callback.message.edit_text("Тут буде інформація для оператора (функціонал у розробці)", reply_markup=get_operator_inline_menu())
    await callback.answer() 