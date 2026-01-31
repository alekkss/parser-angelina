import os
import asyncio
import subprocess
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, FSInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramBadRequest
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Токен бота
BOT_TOKEN = "8355347947:AAFxrMBymwnkx-sXhPGMnq4_uqnOjojD_5w"

# Пути к файлам
BASE_DIR = "/root/Angelina"
MAIN_SCRIPT = os.path.join(BASE_DIR, "angelina-v2.py")
RESULT_FILE = os.path.join(BASE_DIR, "результат.xlsx")
PYTHON_PATH = os.path.join(BASE_DIR, ".venv/bin/python")
TMUX_SESSION = "Angelina"

# Файл-маркер для отслеживания статуса
PID_FILE = os.path.join(BASE_DIR, ".parsing_pid")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Состояния
class ParsingStates(StatesGroup):
    idle = State()
    parsing = State()

# Флаг для блокировки повторных запусков
is_parsing = False


# Клавиатура
def get_main_keyboard(parsing: bool = False):
    """Создает основную клавиатуру"""
    if parsing:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="⏸️ Идет парсинг...")],
                [KeyboardButton(text="🚫 Недоступно")]
            ],
            resize_keyboard=True
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="🚀 Запустить парсинг")],
                [KeyboardButton(text="🗑️ Удалить прошлый файл")]
            ],
            resize_keyboard=True
        )
    return keyboard


async def safe_edit_message(message: Message, text: str, **kwargs):
    """Безопасное редактирование сообщения - только редактирование, без создания нового"""
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "message is not modified" in error_msg:
            # Сообщение не изменилось - это нормально, игнорируем
            return True
        elif "message can't be edited" in error_msg:
            # Сообщение слишком старое - ничего не делаем
            return False
        else:
            # Другая ошибка - логируем
            print(f"⚠️ Ошибка редактирования: {e}")
            return False
    except Exception as e:
        print(f"⚠️ Неожиданная ошибка: {e}")
        return False


def check_tmux_session_exists():
    """Проверяет существование tmux сессии"""
    try:
        result = subprocess.run(
            ["tmux", "has-session", "-t", TMUX_SESSION],
            capture_output=True,
            timeout=5
        )
        return result.returncode == 0
    except:
        return False


def is_process_running(pid):
    """Проверяет, запущен ли процесс с указанным PID"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


async def run_in_tmux():
    """Запускает парсинг в tmux сессии"""
    try:
        # Проверяем существование сессии
        if not check_tmux_session_exists():
            # Создаем новую сессию если не существует
            subprocess.run(
                ["tmux", "new-session", "-d", "-s", TMUX_SESSION],
                check=True,
                timeout=10
            )
            await asyncio.sleep(1)
        
        # Очищаем экран в tmux
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_SESSION, "clear", "C-m"],
            check=True,
            timeout=5
        )
        await asyncio.sleep(0.5)
        
        # Переходим в нужную директорию
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_SESSION, f"cd {BASE_DIR}", "C-m"],
            check=True,
            timeout=5
        )
        await asyncio.sleep(0.5)
        
        # Активируем виртуальное окружение
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_SESSION, "source .venv/bin/activate", "C-m"],
            check=True,
            timeout=5
        )
        await asyncio.sleep(0.5)
        
        # Запускаем программу и сохраняем PID
        command = f"python angelina-v2.py & echo $! > {PID_FILE}"
        subprocess.run(
            ["tmux", "send-keys", "-t", TMUX_SESSION, command, "C-m"],
            check=True,
            timeout=5
        )
        
        # Ждем создания PID файла
        for _ in range(10):
            if os.path.exists(PID_FILE):
                break
            await asyncio.sleep(0.5)
        
        # Читаем PID
        if os.path.exists(PID_FILE):
            with open(PID_FILE, 'r') as f:
                pid = int(f.read().strip())
            return pid
        
        return None
        
    except Exception as e:
        print(f"Ошибка запуска в tmux: {e}")
        return None


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start"""
    await state.set_state(ParsingStates.idle)
    
    session_status = "✅ Найдена" if check_tmux_session_exists() else "⚠️ Не найдена (будет создана)"
    
    welcome_text = (
        "👋 <b>Добро пожаловать в бот управления парсингом!</b>\n\n"
        f"📺 Tmux сессия: <code>{TMUX_SESSION}</code> - {session_status}\n"
        f"📂 Директория: <code>{BASE_DIR}</code>\n\n"
        "🔹 <b>Запустить парсинг</b> - начать сбор данных в tmux сессии\n"
        "🔹 <b>Удалить прошлый файл</b> - очистить результаты\n\n"
        f"💡 <i>Подключиться к процессу:</i> <code>tmux attach -t {TMUX_SESSION}</code>\n\n"
        "📊 Выберите действие:"
    )
    
    await message.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


@dp.message(F.text == "🚀 Запустить парсинг")
async def start_parsing(message: Message, state: FSMContext):
    """Запуск парсинга"""
    global is_parsing
    
    if is_parsing:
        await message.answer(
            "⚠️ <b>Парсинг уже запущен!</b>\n"
            "Пожалуйста, дождитесь завершения текущего процесса.",
            parse_mode="HTML"
        )
        return
    
    # Проверяем существование tmux сессии
    if not check_tmux_session_exists():
        status_info = f"📺 Создаю tmux сессию <code>{TMUX_SESSION}</code>...\n\n"
    else:
        status_info = f"📺 Использую существующую сессию <code>{TMUX_SESSION}</code>\n\n"
    
    is_parsing = True
    await state.set_state(ParsingStates.parsing)
    
    # Отправляем сообщение о начале
    status_msg = await message.answer(
        f"🔄 <b>Запускаю парсинг...</b>\n\n"
        f"{status_info}"
        f"⏳ Запуск программы в tmux...\n\n"
        f"💡 Подключиться: <code>tmux attach -t {TMUX_SESSION}</code>",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(parsing=True)
    )
    
    start_time = datetime.now()
    
    try:
        # Запуск в tmux
        pid = await run_in_tmux()
        
        if not pid:
            raise Exception("Не удалось получить PID процесса")
        
        # Обновляем сообщение что программа запущена
        await safe_edit_message(
            status_msg,
            f"✅ <b>Программа запущена в tmux!</b>\n\n"
            f"📺 Сессия: <code>{TMUX_SESSION}</code>\n"
            f"🆔 PID процесса: <code>{pid}</code>\n\n"
            f"🔄 Начинаю мониторинг...\n\n"
            f"💡 Подключиться: <code>tmux attach -t {TMUX_SESSION}</code>",
            parse_mode="HTML"
        )
        
        await asyncio.sleep(2)
        
        # Мониторим процесс
        update_interval = 30  # секунд
        last_update_time = datetime.now()
        
        while is_process_running(pid):
            # Проверяем каждую секунду, но обновляем раз в 30 секунд
            await asyncio.sleep(1)
            
            current_time = datetime.now()
            if (current_time - last_update_time).total_seconds() >= update_interval:
                # Обновляем статус
                elapsed = (current_time - start_time).total_seconds()
                minutes = int(elapsed // 60)
                seconds = int(elapsed % 60)
                
                status_text = (
                    f"🔄 <b>Парсинг в процессе...</b>\n\n"
                    f"📺 Сессия: <code>{TMUX_SESSION}</code>\n"
                    f"🆔 PID: <code>{pid}</code>\n"
                    f"⏱️ Прошло времени: {minutes}м {seconds}с\n\n"
                    f"📊 Процесс активен, данные собираются...\n\n"
                    f"💡 Подключиться: <code>tmux attach -t {TMUX_SESSION}</code>"
                )
                
                await safe_edit_message(status_msg, status_text, parse_mode="HTML")
                last_update_time = current_time
        
        # Процесс завершился
        elapsed = (datetime.now() - start_time).total_seconds()
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        # Удаляем PID файл
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
        
        # Обновляем сообщение о завершении
        await safe_edit_message(
            status_msg,
            f"✅ <b>Парсинг завершен!</b>\n\n"
            f"⏱️ Время выполнения: {minutes}м {seconds}с\n"
            f"📺 Сессия: <code>{TMUX_SESSION}</code>\n\n"
            f"📤 Проверяю файл результатов...",
            parse_mode="HTML"
        )
        
        # Небольшая задержка
        await asyncio.sleep(2)
        
        # Отправка файла
        if os.path.exists(RESULT_FILE):
            file_size = os.path.getsize(RESULT_FILE) / (1024 * 1024)  # MB
            
            try:
                document = FSInputFile(RESULT_FILE)
                await message.answer_document(
                    document=document,
                    caption=(
                        f"📊 <b>Результаты парсинга</b>\n\n"
                        f"📁 Размер файла: {file_size:.2f} МБ\n"
                        f"⏱️ Время выполнения: {minutes}м {seconds}с\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"📺 Логи в сессии: <code>tmux attach -t {TMUX_SESSION}</code>"
                    ),
                    parse_mode="HTML"
                )
                
                await message.answer(
                    "✅ <b>Готово!</b>\n\n"
                    "Вы можете запустить новый парсинг или удалить файл результатов.",
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard()
                )
            except Exception as e:
                await message.answer(
                    f"❌ <b>Ошибка при отправке файла:</b>\n"
                    f"<code>{str(e)}</code>\n\n"
                    f"Файл находится на сервере: <code>{RESULT_FILE}</code>",
                    parse_mode="HTML",
                    reply_markup=get_main_keyboard()
                )
        else:
            await message.answer(
                "⚠️ <b>Файл результатов не найден!</b>\n\n"
                "Возможно, произошла ошибка во время парсинга.\n"
                f"Проверьте логи: <code>tmux attach -t {TMUX_SESSION}</code>",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
    
    except Exception as e:
        error_message = (
            f"❌ <b>Критическая ошибка:</b>\n"
            f"<code>{str(e)}</code>\n\n"
            f"Тип: {type(e).__name__}\n\n"
            f"Проверьте tmux: <code>tmux attach -t {TMUX_SESSION}</code>"
        )
        
        await safe_edit_message(status_msg, error_message, parse_mode="HTML")
        
        await message.answer(
            "Произошла критическая ошибка. Проверьте логи в tmux.",
            reply_markup=get_main_keyboard()
        )
    
    finally:
        is_parsing = False
        await state.set_state(ParsingStates.idle)
        # Очищаем PID файл
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except:
                pass


@dp.message(F.text == "🗑️ Удалить прошлый файл")
async def delete_result(message: Message):
    """Удаление файла результатов"""
    global is_parsing
    
    if is_parsing:
        await message.answer(
            "⚠️ <b>Невозможно удалить файл во время парсинга!</b>\n"
            "Дождитесь завершения процесса.",
            parse_mode="HTML"
        )
        return
    
    if os.path.exists(RESULT_FILE):
        try:
            file_size = os.path.getsize(RESULT_FILE) / (1024 * 1024)  # MB
            os.remove(RESULT_FILE)
            
            await message.answer(
                f"✅ <b>Файл успешно удален!</b>\n\n"
                f"📁 Удален файл: <code>результат.xlsx</code>\n"
                f"📊 Размер: {file_size:.2f} МБ\n\n"
                f"Теперь можете запустить новый парсинг.",
                parse_mode="HTML",
                reply_markup=get_main_keyboard()
            )
        except Exception as e:
            await message.answer(
                f"❌ <b>Ошибка при удалении файла:</b>\n"
                f"<code>{str(e)}</code>",
                parse_mode="HTML"
            )
    else:
        await message.answer(
            "ℹ️ <b>Файл результатов не найден</b>\n\n"
            "Возможно, он уже был удален или еще не создан.",
            parse_mode="HTML",
            reply_markup=get_main_keyboard()
        )


@dp.message(F.text.in_(["⏸️ Идет парсинг...", "🚫 Недоступно"]))
async def parsing_in_progress(message: Message):
    """Обработчик нажатий во время парсинга"""
    await message.answer(
        "⏳ <b>Парсинг уже выполняется!</b>\n\n"
        f"Процесс запущен в tmux сессии <code>{TMUX_SESSION}</code>\n\n"
        f"💡 Подключиться: <code>tmux attach -t {TMUX_SESSION}</code>\n"
        f"💡 Отключиться: <code>Ctrl+B</code>, затем <code>D</code>\n\n"
        "Вы получите файл автоматически после окончания парсинга.",
        parse_mode="HTML"
    )


@dp.message()
async def unknown_command(message: Message):
    """Обработчик неизвестных команд"""
    await message.answer(
        "❓ <b>Неизвестная команда</b>\n\n"
        "Используйте кнопки меню для управления ботом.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(parsing=is_parsing)
    )


async def main():
    """Главная функция"""
    print("=" * 60)
    print("🤖 TELEGRAM BOT - ANGELINA PARSER (TMUX MODE)")
    print("=" * 60)
    print(f"📂 Рабочая директория: {BASE_DIR}")
    print(f"🐍 Python: {PYTHON_PATH}")
    print(f"📄 Скрипт: {MAIN_SCRIPT}")
    print(f"📊 Файл результатов: {RESULT_FILE}")
    print(f"📺 Tmux сессия: {TMUX_SESSION}")
    print("=" * 60)
    print("✅ Проверка окружения...")
    
    # Проверки
    if not os.path.exists(BASE_DIR):
        print(f"❌ Директория не найдена: {BASE_DIR}")
        return
    
    if not os.path.exists(PYTHON_PATH):
        print(f"❌ Python не найден: {PYTHON_PATH}")
        return
    
    if not os.path.exists(MAIN_SCRIPT):
        print(f"❌ Скрипт не найден: {MAIN_SCRIPT}")
        return
    
    # Проверка tmux
    try:
        subprocess.run(["tmux", "-V"], capture_output=True, check=True, timeout=5)
        print("✅ Tmux установлен")
    except:
        print("❌ Tmux не найден! Установите: apt install tmux")
        return
    
    if check_tmux_session_exists():
        print(f"✅ Tmux сессия '{TMUX_SESSION}' найдена")
    else:
        print(f"⚠️ Tmux сессия '{TMUX_SESSION}' не найдена (будет создана при запуске)")
    
    print("✅ Все проверки пройдены!")
    print("🚀 Запуск бота...")
    print("=" * 60)
    
    # Удаляем вебхуки (если были)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⚠️ Бот остановлен пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
