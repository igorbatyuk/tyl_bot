import sqlite3
import threading
from datetime import datetime
from contextlib import contextmanager
import logging

logger = logging.getLogger(__name__)

_local = threading.local()

DB_PATH = 'users.db'
DB_TIMEOUT = 10.0

def get_connection():
    if not hasattr(_local, 'connection') or _local.connection is None:
        _local.connection = sqlite3.connect(
            DB_PATH,
            timeout=DB_TIMEOUT,
            check_same_thread=False
        )
        _local.connection.execute('PRAGMA journal_mode=WAL')
        _local.connection.execute('PRAGMA synchronous=NORMAL')
        _local.connection.execute('PRAGMA foreign_keys=ON')
        _local.connection.row_factory = sqlite3.Row
    return _local.connection

@contextmanager
def db_transaction():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Помилка транзакції: {e}")
        raise
    finally:
        pass

def close_connection():
    if hasattr(_local, 'connection') and _local.connection:
        _local.connection.close()
        _local.connection = None

def init_db():
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    join_date TEXT,
                    balance INTEGER DEFAULT 0,
                    last_payment_date TEXT,
                    total_payments INTEGER DEFAULT 0,
                    last_active TEXT,
                    is_blocked INTEGER DEFAULT 0,
                    used_requests INTEGER DEFAULT 0
                )
            ''')
            c.execute('''
                CREATE INDEX IF NOT EXISTS idx_telegram_id ON users(telegram_id)
            ''')
            c.execute('''
                CREATE INDEX IF NOT EXISTS idx_username ON users(username)
            ''')
            try:
                c.execute('ALTER TABLE users ADD COLUMN used_requests INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass
        logger.info("База даних ініціалізована успішно")
    except Exception as e:
        logger.error(f"Помилка ініціалізації БД: {e}")
        raise

def add_or_update_user(user):
    if not user or not hasattr(user, 'id'):
        raise ValueError("Невірний об'єкт користувача")
    
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            now = datetime.now().isoformat()
            c.execute('SELECT telegram_id FROM users WHERE telegram_id=?', (user.id,))
            exists = c.fetchone()
            if not exists:
                c.execute('''
                    INSERT INTO users (telegram_id, username, first_name, last_name, join_date, last_active, balance)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user.id,
                    user.username,
                    user.first_name,
                    user.last_name,
                    now,
                    now,
                    5
                ))
                return True
            else:
                c.execute('''
                    UPDATE users SET
                        username=?,
                        first_name=?,
                        last_name=?,
                        last_active=?
                    WHERE telegram_id=?
                ''', (
                    user.username,
                    user.first_name,
                    user.last_name,
                    now,
                    user.id
                ))
                return False
    except sqlite3.IntegrityError as e:
        logger.error(f"Помилка цілісності БД при додаванні користувача {user.id}: {e}")
        raise
    except Exception as e:
        logger.error(f"Помилка при додаванні/оновленні користувача {user.id}: {e}")
        raise

def get_balance(telegram_id):
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT balance FROM users WHERE telegram_id=?', (telegram_id,))
        row = c.fetchone()
        return row[0] if row else 0
    except Exception as e:
        logger.error(f"Помилка отримання балансу для {telegram_id}: {e}")
        return 0

def set_balance(telegram_id, new_balance):
    if not isinstance(new_balance, int) or new_balance < 0:
        raise ValueError("Баланс повинен бути невід'ємним цілим числом")
    
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET balance=? WHERE telegram_id=?', (new_balance, telegram_id))
    except Exception as e:
        logger.error(f"Помилка встановлення балансу для {telegram_id}: {e}")
        raise

def add_balance(telegram_id, amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("Сума повинна бути додатним числом")
    
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE users 
                SET balance = balance + ?, 
                    last_payment_date=?, 
                    total_payments = total_payments + ? 
                WHERE telegram_id=?
            ''', (int(amount), datetime.now().isoformat(), int(amount), telegram_id))
            _invalidate_balance_cache(telegram_id)
    except Exception as e:
        logger.error(f"Помилка додавання балансу для {telegram_id}: {e}")
        raise

def _invalidate_balance_cache(telegram_id):
    try:
        from additional_improvements import balance_cache
        balance_cache.invalidate(telegram_id)
    except ImportError:
        pass

def subtract_balance(telegram_id, amount):
    if not isinstance(amount, (int, float)) or amount <= 0:
        raise ValueError("Сума повинна бути додатним числом")
    
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            c.execute('SELECT balance FROM users WHERE telegram_id=?', (telegram_id,))
            row = c.fetchone()
            if not row:
                raise ValueError(f"Користувач {telegram_id} не знайдений")
            
            current_balance = row[0]
            if current_balance < amount:
                logger.warning(f"Недостатньо балансу для {telegram_id}: {current_balance} < {amount}")
                raise ValueError(f"Недостатньо балансу: {current_balance} < {amount}")
            
            c.execute('''
                UPDATE users 
                SET balance = balance - ?, 
                    used_requests = used_requests + ? 
                WHERE telegram_id=? AND balance >= ?
            ''', (int(amount), int(amount), telegram_id, int(amount)))
            
            if c.rowcount == 0:
                raise ValueError(f"Не вдалося списати баланс для {telegram_id}")
            
            return True
    except Exception as e:
        logger.error(f"Помилка віднімання балансу для {telegram_id}: {e}")
        raise

def block_user(telegram_id):
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET is_blocked=1 WHERE telegram_id=?', (telegram_id,))
    except Exception as e:
        logger.error(f"Помилка блокування користувача {telegram_id}: {e}")
        raise

def unblock_user(telegram_id):
    try:
        with db_transaction() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET is_blocked=0 WHERE telegram_id=?', (telegram_id,))
    except Exception as e:
        logger.error(f"Помилка розблокування користувача {telegram_id}: {e}")
        raise

def get_users_page(page=1, per_page=10):
    if page < 1:
        page = 1
    if per_page < 1 or per_page > 100:
        per_page = 10
    
    try:
        conn = get_connection()
        c = conn.cursor()
        offset = (page - 1) * per_page
        c.execute('''
            SELECT telegram_id, username, first_name, last_name 
            FROM users 
            ORDER BY id 
            LIMIT ? OFFSET ?
        ''', (per_page, offset))
        users = c.fetchall()
        return users
    except Exception as e:
        logger.error(f"Помилка отримання сторінки користувачів: {e}")
        return []

def get_total_users():
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        count = c.fetchone()[0]
        return count
    except Exception as e:
        logger.error(f"Помилка підрахунку користувачів: {e}")
        return 0

def find_user_by_username(username):
    if not username or not isinstance(username, str):
        return None
    
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT telegram_id, username, first_name, last_name FROM users WHERE username=?', (username,))
        user = c.fetchone()
        return user
    except Exception as e:
        logger.error(f"Помилка пошуку користувача за username {username}: {e}")
        return None

def find_user_by_id(telegram_id):
    if not isinstance(telegram_id, int) or telegram_id <= 0:
        return None
    
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT telegram_id, username, first_name, last_name FROM users WHERE telegram_id=?', (telegram_id,))
        user = c.fetchone()
        return user
    except Exception as e:
        logger.error(f"Помилка пошуку користувача за ID {telegram_id}: {e}")
        return None

def get_user_full_info(telegram_id):
    if not isinstance(telegram_id, int) or telegram_id <= 0:
        return None
    
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE telegram_id=?', (telegram_id,))
        user = c.fetchone()
        return user
    except Exception as e:
        logger.error(f"Помилка отримання інформації про користувача {telegram_id}: {e}")
        return None
