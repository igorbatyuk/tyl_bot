from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel_action")
    ]])

def format_balance_message(balance: int, name: str = "Користувач") -> str:
    if balance == 0:
        emoji = "⚠️"
        status = "Баланс вичерпано"
    elif balance < 5:
        emoji = "🔶"
        status = "Баланс низький"
    elif balance < 20:
        emoji = "🔸"
        status = "Баланс середній"
    else:
        emoji = "✅"
        status = "Баланс достатній"
    
    return (
        f"{emoji} <b>Ваш баланс: {balance} запитів</b>\n"
        f"Статус: {status}\n\n"
        f"💡 <i>1 запит = 1 питання до служби</i>"
    )

def format_service_info(service_name: str, balance: int) -> str:
    service_emojis = {
        "⛽️ ПММ": "⛽️",
        "🍲 Продовольча": "🍲",
        "👕 Речова": "👕"
    }
    emoji = service_emojis.get(service_name, "📋")
    
    return (
        f"{emoji} <b>Ви обрали: {service_name}</b>\n\n"
        f"💰 Доступно запитів: <b>{balance}</b>\n\n"
        f"📝 Напишіть ваше питання нижче.\n"
        f"Бот надасть відповідь на основі нормативних документів.\n\n"
        f"💡 <i>Порада: Чим детальніше питання, тим точніша відповідь</i>"
    )

def get_help_tips() -> str:
    return (
        "💡 <b>Корисні поради:</b>\n\n"
        "✅ Формулюйте питання чітко та конкретно\n"
        "✅ Вказуйте тип техніки/майна\n"
        "✅ Згадуйте період (літо/зима/бойові дії)\n"
        "✅ Задавайте одне питання за раз\n\n"
        "❌ Уникайте загальних фраз\n"
        "❌ Не задавайте кілька питань одночасно"
    )

def format_user_stats(user_info) -> str:
    if not user_info:
        return "❌ Інформація не знайдена"
    
    join_date = user_info[5] if user_info[5] else "Невідомо"
    balance = user_info[6]
    used = user_info[11] if len(user_info) > 11 else 0
    total_payments = user_info[8] if len(user_info) > 8 else 0
    
    total_available = balance + used
    if total_available > 0:
        usage_percent = (used / total_available) * 100
    else:
        usage_percent = 0
    
    return (
        f"📊 <b>Ваша статистика:</b>\n\n"
        f"💰 Поточний баланс: <b>{balance}</b> запитів\n"
        f"📈 Використано: <b>{used}</b> запитів\n"
        f"💳 Поповнено всього: <b>{total_payments}</b> запитів\n"
        f"📉 Використано: <b>{usage_percent:.1f}%</b>\n\n"
        f"📅 Дата реєстрації: {join_date}\n\n"
        f"💡 <i>Поповніть баланс, якщо закінчились запити</i>"
    )

def get_quick_actions_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏢 Служби"), KeyboardButton(text="💳 Поповнити")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="ℹ️ Про бота"), KeyboardButton(text="👨‍💼 Оператор")]
        ],
        resize_keyboard=True
    )

def format_payment_instructions(card_number: str, identifier: str, has_username: bool) -> str:
    return (
        f"💳 <b>Поповнення балансу</b>\n\n"
        f"📱 <b>Номер картки:</b> <code>{card_number}</code>\n\n"
        f"🔄 <b>Автоматичне поповнення</b> (Monobank):\n"
        f"1️⃣ Переведіть суму зі свого Monobank\n"
        f"2️⃣ У призначенні платежу вкажіть:\n"
        f"   <code>{identifier}</code>\n"
        f"3️⃣ Система автоматично зарахує запити\n"
        f"   <i>1 грн = 1 запит</i>\n"
        f"⏱ Час зарахування: до 1 хвилини\n\n"
        f"👨‍💼 <b>Ручне поповнення</b> (інші банки):\n"
        f"1️⃣ Зробіть переказ\n"
        f"2️⃣ Напишіть оператору @TylBotOperator:\n"
        f"   • Ваш {('username' if has_username else 'ID')}: <code>{identifier}</code>\n"
        f"   • Сума переказу\n"
        f"   • Номер переказу\n"
        f"3️⃣ Оператор поповнить баланс\n"
        f"⏱ Час: 10-30 хвилин\n\n"
        f"ℹ️ <i>Автоматичне зарахування працює тільки для Monobank</i>"
    )

def get_processing_stages() -> list:
    return [
        "⏳ Аналізую ваше питання...",
        "🔍 Шукаю відповідь в документах...",
        "📝 Формую відповідь...",
        "✅ Майже готово..."
    ]


