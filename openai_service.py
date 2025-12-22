import os
import logging
import asyncio
from openai import OpenAI
from openai import RateLimitError, APIError
from dotenv import load_dotenv
import re
from typing import Optional, Tuple
from functools import lru_cache
import time

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PMM_ASSISTANT_ID = os.getenv('PMM_ASSISTANT_ID')
FOOD_ASSISTANT_ID = os.getenv('FOOD_ASSISTANT_ID')
SUPPLY_ASSISTANT_ID = os.getenv('SUPPLY_ASSISTANT_ID')

MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_MESSAGE_LENGTH = 4000

if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY не встановлено")
    client = None
else:
    client = OpenAI(api_key=OPENAI_API_KEY)

SERVICE_ASSISTANTS = {
    "⛽️ ПММ": PMM_ASSISTANT_ID,
    "🍲 Продовольча": FOOD_ASSISTANT_ID,
    "👕 Речова": SUPPLY_ASSISTANT_ID
}

user_threads: dict[int, str] = {}

def validate_message(message: str) -> Tuple[bool, Optional[str]]:
    if not message or not isinstance(message, str):
        return False, "Повідомлення не може бути порожнім"
    
    if len(message.strip()) == 0:
        return False, "Повідомлення не може містити тільки пробіли"
    
    if len(message) > MAX_MESSAGE_LENGTH:
        return False, f"Повідомлення занадто довге (максимум {MAX_MESSAGE_LENGTH} символів)"
    
    suspicious_patterns = [
        r'<script',
        r'javascript:',
        r'onerror=',
        r'onload=',
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, message, re.IGNORECASE):
            return False, "Повідомлення містить недозволені символи"
    
    return True, None

def format_markdown(text: str) -> str:
    if not text:
        return ""
    
    circled_numbers = {
        '①': '1.', '②': '2.', '③': '3.', '④': '4.', '⑤': '5.', 
        '⑥': '6.', '⑦': '7.', '⑧': '8.', '⑨': '9.', '⑩': '10.'
    }
    for k, v in circled_numbers.items():
        text = text.replace(k, v)

    text = re.sub(r'\[\d+(:\d+)?[†]?(source|джерело)?\.?\]', '', text)
    text = re.sub(r'\[\d+\]', '', text)
    text = re.sub(r'【.*?】', '', text)

    text = re.sub(r'\*\*(.*?)\*\*', r'*\1*', text)
    text = re.sub(r'__(.*?)__', r'_\1_', text)
    text = re.sub(r'^\s*-\s*', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s*', lambda m: f"{m.group(0)} ", text, flags=re.MULTILINE)
    text = re.sub(r'\n([•\d])', r'\n\n\1', text)
    text = re.sub(r' +', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    return text

async def get_service_response(
    service_name: str, 
    user_message: str, 
    user_id: int,
    retry_count: int = 0
) -> str:
    if not client:
        logger.error("OpenAI клієнт не ініціалізований")
        return "❌ Помилка: сервіс тимчасово недоступний."
    
    is_valid, error_msg = validate_message(user_message)
    if not is_valid:
        logger.warning(f"Невалідне повідомлення від користувача {user_id}: {error_msg}")
        return f"❌ {error_msg}"
    
    try:
        assistant_id = SERVICE_ASSISTANTS.get(service_name)
        if not assistant_id:
            logger.error(f"Не знайдено ID асистента для служби: {service_name}")
            return "❌ Помилка: не знайдено відповідного асистента для цієї служби."

        thread_id = None
        if user_id in user_threads:
            thread_id = user_threads[user_id]
            logger.info(f"Використовуємо існуючий тред {thread_id} для користувача {user_id}")
        else:
            thread = client.beta.threads.create()
            thread_id = thread.id
            user_threads[user_id] = thread_id
            logger.info(f"Створено новий тред {thread_id} для користувача {user_id}")
        
        message = client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )
        logger.info(f"Додано повідомлення користувача до треду {thread_id}")
        
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=assistant_id
        )
        logger.info(f"Запущено асистента {assistant_id} для треду {thread_id}")
        
        max_wait_time = 60
        start_time = time.time()
        
        while True:
            if time.time() - start_time > max_wait_time:
                logger.error(f"Таймаут очікування відповіді для треду {thread_id}")
                return "❌ Помилка: час очікування відповіді перевищено. Спробуйте пізніше."
            
            run_status = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )
            
            if run_status.status == 'completed':
                logger.info(f"Асистент завершив роботу для треду {thread_id}")
                break
            elif run_status.status in ['failed', 'cancelled', 'expired']:
                error_msg = getattr(run_status, 'last_error', None)
                logger.error(f"Помилка виконання: {run_status.status}, деталі: {error_msg}")
                return "❌ Помилка при отриманні відповіді від асистента."
            
            await asyncio.sleep(1)
        
        messages = client.beta.threads.messages.list(
            thread_id=thread_id,
            order="desc",
            limit=1
        )
        
        if messages.data and messages.data[0].role == 'assistant':
            response = messages.data[0].content[0].text.value
            logger.info(f"Отримано відповідь від асистента для треду {thread_id}")
            
            formatted_response = format_markdown(response)
            return formatted_response
        
        logger.error(f"Не знайдено відповіді асистента в треді {thread_id}")
        return "❌ Не вдалося отримати відповідь від асистента."
        
    except RateLimitError as e:
        logger.warning(f"Rate limit досягнуто для користувача {user_id}, спроба {retry_count + 1}")
        if retry_count < MAX_RETRIES:
            wait_time = RETRY_DELAY * (2 ** retry_count)
            await asyncio.sleep(wait_time)
            return await get_service_response(service_name, user_message, user_id, retry_count + 1)
        return "❌ Перевищено ліміт запитів. Спробуйте через кілька хвилин."
    
    except APIError as e:
        logger.error(f"Помилка OpenAI API для користувача {user_id}: {e}")
        if retry_count < MAX_RETRIES and e.status_code and e.status_code >= 500:
            wait_time = RETRY_DELAY * (2 ** retry_count)
            await asyncio.sleep(wait_time)
            return await get_service_response(service_name, user_message, user_id, retry_count + 1)
        return "❌ Помилка при обробці запиту. Спробуйте пізніше або зверніться до оператора."
    
    except Exception as e:
        logger.error(f"Неочікувана помилка при роботі з OpenAI API для користувача {user_id}: {e}", exc_info=True)
        return "❌ Помилка при обробці запиту. Спробуйте пізніше або зверніться до оператора."

def clear_user_thread(user_id: int):
    if user_id in user_threads:
        thread_id = user_threads[user_id]
        logger.info(f"Видалено тред {thread_id} для користувача {user_id}")
        del user_threads[user_id]

def get_thread_id(user_id: int) -> Optional[str]:
    return user_threads.get(user_id)
