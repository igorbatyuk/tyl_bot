import os
import asyncio
import logging
import ssl
from datetime import datetime, timedelta
import aiohttp
from dotenv import load_dotenv
from db import add_balance, find_user_by_username, find_user_by_id, get_balance
from aiogram import Bot
import re

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONOBANK_API_TOKEN = os.getenv('MONOBANK_API_TOKEN')
CHECK_INTERVAL = int(os.getenv('MONOBANK_CHECK_INTERVAL', '60'))
CARD_NUMBER = os.getenv('MONOBANK_CARD_NUMBER', '4441114419905094')
GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', '-4647978421'))
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TELEGRAM_BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN не встановлено")
    bot = None
else:
    bot = Bot(token=TELEGRAM_BOT_TOKEN)

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

async def get_monobank_transactions():
    if not MONOBANK_API_TOKEN:
        logger.error("MONOBANK_API_TOKEN не встановлено")
        return []

    headers = {
        'X-Token': MONOBANK_API_TOKEN,
        'Content-Type': 'application/json'
    }
    
    now = int(datetime.now().timestamp())
    from_time = now - 60
    
    url = f'https://api.monobank.ua/personal/statement/0/{from_time}/{now}'
    
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    async with aiohttp.ClientSession(connector=connector) as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Помилка отримання транзакцій: {response.status} - {error_text}")
                    return []
        except Exception as e:
            logger.error(f"Помилка запиту до Monobank API: {e}")
            return []

def extract_user_identifier(comment):
    if not comment:
        return None, None
        
    if '@' in comment:
        username = comment.split('@')[-1].strip()
        return 'username', username
    else:
        username = comment.strip()
        if username.replace('_', '').isalnum():
            return 'username', username
    
    try:
        user_id = int(comment.strip())
        return 'id', user_id
    except ValueError:
        return None, None

async def notify_group(text: str):
    try:
        await bot.send_message(GROUP_CHAT_ID, text)
    except Exception as e:
        logging.error(f"Не вдалося надіслати повідомлення у групу: {e}")

def is_valid_username(username):
    return bool(re.fullmatch(r'[A-Za-z0-9_]{5,32}', username))

def is_valid_user_id(user_id):
    return isinstance(user_id, int) and len(str(user_id)) >= 6

async def notify_user_balance(user_id, amount):
    try:
        balance = get_balance(user_id)
        text = (
            f"Дякуємо! Ваш рахунок поповнено на {int(amount)} грн.\n"
            f"Поточний баланс: {balance} запитів.\n"
            f"Приємного користування!"
        )
        await bot.send_message(user_id, text)
    except Exception as e:
        logging.error(f"Не вдалося надіслати повідомлення користувачу {user_id}: {e}")

async def process_transactions(transactions):
    for transaction in transactions:
        if transaction.get('amount', 0) > 0:
            comment = transaction.get('comment', '').strip()
            sender = transaction.get('sender', '') or transaction.get('counterEdrpou', '') or transaction.get('description', '')
            amount = transaction.get('amount', 0) / 100
            time_str = transaction.get('time', '')
            description = transaction.get('description', '')
            txn_id = transaction.get('id', '')
            info_text = (
                f"💸 Новий платіж Monobank\n"
                f"Сума: {amount} грн\n"
                f"Час: {time_str}\n"
                f"ID транзакції: {txn_id}\n"
                f"Від кого: {sender}\n"
                f"Опис: {description}\n"
                f"Коментар: {comment if comment else '-'}"
            )
            if not comment:
                asyncio.create_task(notify_group(f"❗️ Платіж без коментаря!\n" + info_text))
                continue
            identifier_type, identifier = extract_user_identifier(comment)
            if identifier_type == 'username' and not is_valid_username(identifier):
                asyncio.create_task(notify_group(f"❗️ Платіж з невалідним username!\n" + info_text))
                continue
            if identifier_type == 'id' and not is_valid_user_id(identifier):
                asyncio.create_task(notify_group(f"❗️ Платіж з невалідним ID!\n" + info_text))
                continue
            if identifier_type and identifier:
                user = None
                if identifier_type == 'username':
                    user = find_user_by_username(identifier)
                elif identifier_type == 'id':
                    user = find_user_by_id(identifier)
                
                if user:
                    amount = transaction.get('amount', 0) / 100
                    if amount > 0:
                        logger.info(f"Поповнення балансу користувача {identifier} на {amount} грн")
                        add_balance(user[0], int(amount))
                        asyncio.create_task(notify_user_balance(user[0], amount))
                    else:
                        logger.warning(f"Сума платежу менше або дорівнює 0 для користувача {identifier}")
                else:
                    logger.warning(f"Користувач {identifier} не знайдений в базі даних")
                    asyncio.create_task(notify_group(f"❗️ Платіж з неіснуючим коментарем!\n" + info_text))
            else:
                logger.warning(f"Не вдалося визначити користувача для коментаря: {comment}")

async def check_payments():
    logger.info("Запущено перевірку платежів Monobank")
    last_check_time = datetime.now() - timedelta(minutes=1)
    
    while True:
        try:
            transactions = await get_monobank_transactions()
            if transactions:
                new_transactions = [
                    t for t in transactions 
                    if datetime.fromtimestamp(t.get('time', 0)) > last_check_time
                ]
                
                if new_transactions:
                    await process_transactions(new_transactions)
            
            last_check_time = datetime.now()
            await asyncio.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Помилка при перевірці платежів: {e}")
            await asyncio.sleep(CHECK_INTERVAL)

async def start_payment_checker():
    if not MONOBANK_API_TOKEN:
        logger.error("MONOBANK_API_TOKEN не знайдено в .env файлі")
        return
    
    await check_payments()

if __name__ == "__main__":
    asyncio.run(start_payment_checker()) 