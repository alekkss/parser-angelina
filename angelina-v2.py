import os
import time
import asyncio
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# --- Настраиваемые параметры из .env ---
LOGIN_URL = os.getenv("LOGIN_URL", "https://lk.eutd.ru/login")
NOMENCLATURES_URL = os.getenv("NOMENCLATURES_URL", "https://lk.eutd.ru/nomenclatures")
EMAIL = os.getenv("APP_EMAIL")
PASSWORD = os.getenv("APP_PASSWORD")

# Параметры ожидания
POST_LOGIN_WAIT = int(os.getenv("POST_LOGIN_WAIT", "10"))
POST_NAVIGATION_WAIT = int(os.getenv("POST_NAVIGATION_WAIT", "20"))
PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", "60000"))  # в миллисекундах

# Файлы
COOKIES_FILE = os.getenv("COOKIES_FILE", "session_cookies.json")
OUTPUT_EXCEL = os.getenv("OUTPUT_EXCEL", "table_container_html.xlsx")
TEMP_EXCEL = os.getenv("TEMP_EXCEL", "temp_table_container_html.xlsx")
LAST_POSITION_FILE = os.getenv("LAST_POSITION_FILE", "last_position.txt")
FINAL_EXCEL = os.getenv("FINAL_EXCEL", "результат.xlsx")

# Параметры прокрутки
SCROLL_STEP = int(os.getenv("SCROLL_STEP", "800"))
SCROLL_STEP_PAUSE = float(os.getenv("SCROLL_STEP_PAUSE", "0.5"))
CHECK_PAUSE = int(os.getenv("CHECK_PAUSE", "5"))
MAX_SCROLL_POSITION = int(os.getenv("MAX_SCROLL_POSITION", "725000"))
RESTART_THRESHOLD = int(os.getenv("RESTART_THRESHOLD", "100000"))

# Браузерные настройки
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
USER_AGENT = os.getenv("USER_AGENT", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.7049.52 Safari/537.36")

# Проверка обязательных переменных
if not EMAIL or not PASSWORD:
    raise ValueError("⚠️ EMAIL и PASSWORD должны быть указаны в .env файле!")

print(f"🔧 Настройки загружены:")
print(f"   📧 Email: {EMAIL}")
print(f"   🌐 Login URL: {LOGIN_URL}")
print(f"   📋 Nomenclatures URL: {NOMENCLATURES_URL}")
print(f"   👁️ Headless режим: {HEADLESS}")


# --- Функция чтения последней позиции прокрутки ---
def get_last_position():
    """Читает последнюю сохраненную позицию прокрутки из файла"""
    if os.path.exists(LAST_POSITION_FILE):
        with open(LAST_POSITION_FILE, "r") as f:
            try:
                return int(f.read().strip())
            except ValueError:
                print("⚠️ Ошибка чтения последней позиции, начинаем с 0.")
                return 0
    return 0


# --- Функция сохранения последней позиции прокрутки ---
def save_last_position(position):
    """Сохраняет текущую позицию прокрутки в файл"""
    with open(LAST_POSITION_FILE, "w") as f:
        f.write(str(position))
    print(f"💾 Сохранена последняя позиция прокрутки: {position}px")


# --- Функция сохранения данных в промежуточный Excel ---
def save_temp_excel(data_to_save):
    """Сохраняет промежуточные данные в Excel файл"""
    try:
        df = pd.DataFrame(data_to_save)
        df.to_excel(TEMP_EXCEL, index=False, engine="openpyxl")
        print(f"💾 Промежуточные данные сохранены в файл: {TEMP_EXCEL}")
    except Exception as e:
        print(f"❌ Ошибка при сохранении в промежуточный Excel: {e}")


# --- Функция объединения данных из промежуточного Excel в итоговый ---
def merge_temp_to_final():
    """Объединяет данные из временного файла с итоговым"""
    if os.path.exists(TEMP_EXCEL):
        try:
            temp_df = pd.read_excel(TEMP_EXCEL, engine="openpyxl")
            if os.path.exists(OUTPUT_EXCEL):
                final_df = pd.read_excel(OUTPUT_EXCEL, engine="openpyxl")
                combined_df = pd.concat([final_df, temp_df]).drop_duplicates().reset_index(drop=True)
            else:
                combined_df = temp_df
            combined_df.to_excel(OUTPUT_EXCEL, index=False, engine="openpyxl")
            print(f"✅ Данные объединены в итоговый файл: {OUTPUT_EXCEL}")
        except Exception as e:
            print(f"❌ Ошибка при объединении данных: {e}")


# --- Функция удаления временных файлов ---
def clear_temp_files():
    """Удаляет все временные файлы"""
    for file in [COOKIES_FILE, TEMP_EXCEL, LAST_POSITION_FILE]:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"🗑️ Удален файл: {file}")
            except Exception as e:
                print(f"⚠️ Ошибка при удалении файла {file}: {e}")


# --- Функция удаления folder_container из DOM ---
def remove_folder_container(page):
    """Удаляет элементы folder_container из DOM для оптимизации"""
    print("🧹 Удаление элементов с классом folder_container из DOM...")
    try:
        page.evaluate("""
            () => {
                const elements = document.getElementsByClassName('folder_container');
                while (elements.length > 0) {
                    elements[0].parentNode.removeChild(elements[0]);
                }
            }
        """)
        print("✅ Элементы с классом folder_container удалены.")
    except Exception as e:
        print(f"⚠️ Ошибка при удалении folder_container: {e}")


# --- Функция обработки HTML и создания финального Excel ---
def process_html_to_excel(input_file=None, output_file=None):
    """Обрабатывает HTML из промежуточного файла и создает финальный Excel"""
    if input_file is None:
        input_file = OUTPUT_EXCEL
    if output_file is None:
        output_file = FINAL_EXCEL
        
    print(f"🔄 Обработка HTML из {input_file} и создание финального файла {output_file}...")
    try:
        df = pd.read_excel(input_file, engine="openpyxl")
        html_column = df.iloc[:, 1]
        
        data = {
            'Код номенклатуры': [],
            'Наименование товара': [],
            'Полное наименование': [],
            'Остаток': [],
            'Цена (руб)': [],
            'НТД': [],
            'Марка стали': [],
            'Вес': []
        }
        
        def clean_price(price):
            """Очищает цену от запятых и преобразует в float"""
            try:
                return float(price.replace(',', '.'))
            except:
                return 0.0
        
        for html in html_column:
            soup = BeautifulSoup(html, 'html.parser')
            rows = soup.find_all('tr', id=True)
            
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 8:
                    data['Код номенклатуры'].append(cells[0].text.strip())
                    
                    shortname_div = cells[1].find('div', class_='row_width_copy')
                    data['Наименование товара'].append(
                        shortname_div.find('span').text.strip() 
                        if shortname_div and shortname_div.find('span') else ''
                    )
                    
                    fullname_div = cells[2].find('div', class_='row_width_copy')
                    data['Полное наименование'].append(
                        fullname_div.find('span').text.strip() 
                        if fullname_div and fullname_div.find('span') else ''
                    )
                    
                    try:
                        data['Остаток'].append(int(cells[3].text.strip()))
                    except:
                        data['Остаток'].append(0)
                    
                    price_div = cells[4].find('div', class_='row_width_copy')
                    price = price_div.find('span').text.strip() if price_div and price_div.find('span') else '0'
                    data['Цена (руб)'].append(clean_price(price))
                    
                    data['НТД'].append(cells[5].text.strip())
                    data['Марка стали'].append(cells[6].text.strip())
                    
                    try:
                        data['Вес'].append(float(cells[7].text.strip()))
                    except:
                        data['Вес'].append(0.0)
        
        result_df = pd.DataFrame(data)
        result_df.to_excel(output_file, index=False, engine='openpyxl')
        print(f"✅ Новая таблица сохранена в {output_file}")
        print(f"📊 Всего записей: {len(result_df)}")
        
        clear_temp_files()
        print("✅ Временные файлы удалены после создания финального Excel.")
        
    except Exception as e:
        print(f"❌ Ошибка при обработке HTML и создании финального Excel: {e}")


# --- Функция медленной прокрутки контейнера main_content_container ---
def scroll_to_load_table_container(page, start_position=0, scroll_step=None, max_empty_attempts=10000):
    """Постепенно прокручивает страницу и собирает данные"""
    if scroll_step is None:
        scroll_step = SCROLL_STEP
        
    print(f"🔄 Начинаем поэтапную прокрутку main_content_container с позиции {start_position}px...")
    data_to_save = []
    seen_ids = set()
    empty_attempts = 0
    scroll_position = start_position
    
    # Загрузка уже сохранённых id
    if os.path.exists(TEMP_EXCEL):
        try:
            temp_df = pd.read_excel(TEMP_EXCEL, engine="openpyxl")
            data_to_save = temp_df.to_dict("records")
            for html_content in temp_df['html_content']:
                soup = BeautifulSoup(html_content, 'html.parser')
                for tr in soup.find_all('tr', id=True):
                    seen_ids.add(tr['id'])
            print(f"📂 Загружено {len(seen_ids)} уникальных id из TEMP_EXCEL")
        except Exception as e:
            print(f"⚠️ Ошибка при загрузке TEMP_EXCEL: {e}")
    
    # Проверка наличия контейнера
    try:
        container = page.locator(".main_content_container").first
        if container.count() > 0:
            print("✅ Найден контейнер main_content_container")
            use_container = True
        else:
            print("⚠️ Контейнер не найден, используем прокрутку окна")
            use_container = False
    except:
        print("⚠️ Используем прокрутку окна вместо контейнера")
        use_container = False
    
    while empty_attempts < max_empty_attempts:
        # Получаем текущую высоту
        if use_container:
            max_height = page.evaluate("""
                () => {
                    const container = document.querySelector('.main_content_container');
                    return container ? container.scrollHeight : 0;
                }
            """)
        else:
            max_height = page.evaluate("() => document.body.scrollHeight")
        
        # Прокручиваем по шагу
        if use_container:
            page.evaluate(f"""
                () => {{
                    const container = document.querySelector('.main_content_container');
                    if (container) {{
                        container.scrollTop = {scroll_position};
                    }}
                }}
            """)
        else:
            page.evaluate(f"() => window.scrollTo(0, {scroll_position})")
        
        # Ждем подгрузки контента
        time.sleep(2)
        
        # Парсим новые строки
        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        table_container = soup.find('div', class_='table_container')
        
        new_trs = []
        if table_container:
            for tr in table_container.find_all('tr', id=True):
                tr_id = tr['id']
                if tr_id not in seen_ids:
                    seen_ids.add(tr_id)
                    new_trs.append(str(tr))
        
        if new_trs:
            html_content = "<table>" + "".join(new_trs) + "</table>"
            data_to_save.append({
                'position': scroll_position,
                'html_content': html_content
            })
            empty_attempts = 0
            print(f"✅ Найдено {len(new_trs)} новых строк на позиции {scroll_position}px (всего: {len(seen_ids)})")
            
            # Сохраняем промежуточные данные каждые 50 новых записей
            if len(data_to_save) % 50 == 0:
                save_temp_excel(data_to_save)
                save_last_position(scroll_position)
        else:
            empty_attempts += 1
            if empty_attempts % 10 == 0:
                print(f"⏳ Новых данных не найдено на позиции {scroll_position}px (попытка {empty_attempts}/{max_empty_attempts})")
        
        # Увеличиваем позицию прокрутки
        scroll_position += scroll_step
        
        # Проверяем достижение максимальной высоты или лимита
        if scroll_position >= max_height or scroll_position >= MAX_SCROLL_POSITION:
            print(f"🏁 Достигнут предел прокрутки: {scroll_position}px")
            break
        
        # Небольшая пауза между итерациями
        time.sleep(SCROLL_STEP_PAUSE)
    
    # Финальное сохранение данных
    if data_to_save:
        save_temp_excel(data_to_save)
        merge_temp_to_final()
        save_last_position(scroll_position)
        print(f"✅ Сбор данных завершен. Всего собрано {len(seen_ids)} уникальных записей.")
    
    return len(seen_ids)


# --- Основная функция авторизации ---
def login_and_navigate(page):
    """Выполняет авторизацию и переход на страницу номенклатур"""
    try:
        # Переход на страницу входа
        print("🌐 Переход на страницу входа...")
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        
        # Ожидание загрузки формы входа и ввод данных
        print("📝 Заполнение формы авторизации...")
        page.wait_for_selector('input[name="email"]', timeout=10000)
        
        page.fill('input[name="email"]', EMAIL)
        page.fill('input[name="password"]', PASSWORD)
        
        # Нажатие кнопки входа
        print("🔐 Отправка данных авторизации...")
        page.click('button[type="submit"]')
        
        # Ожидание после входа
        print(f"⏳ Ожидание {POST_LOGIN_WAIT} секунд после авторизации...")
        time.sleep(POST_LOGIN_WAIT)
        
        # Переход на страницу номенклатур
        print("📋 Переход на страницу номенклатур...")
        page.goto(NOMENCLATURES_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
        
        print(f"⏳ Ожидание {POST_NAVIGATION_WAIT} секунд для загрузки страницы...")
        time.sleep(POST_NAVIGATION_WAIT)
        
        print("✅ Авторизация успешна!")
        return True
        
    except PlaywrightTimeout as e:
        print(f"❌ Таймаут при авторизации: {e}")
        return False
    except Exception as e:
        print(f"❌ Ошибка при авторизации: {e}")
        return False


# --- Функция сохранения cookies ---
def save_cookies(context):
    """Сохраняет cookies в файл"""
    try:
        cookies = context.cookies()
        import json
        with open(COOKIES_FILE, 'w') as f:
            json.dump(cookies, f)
        print(f"💾 Cookies сохранены в {COOKIES_FILE}")
    except Exception as e:
        print(f"⚠️ Ошибка при сохранении cookies: {e}")


# --- Функция загрузки cookies ---
def load_cookies(context):
    """Загружает cookies из файла"""
    try:
        if os.path.exists(COOKIES_FILE):
            import json
            with open(COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            print(f"📂 Cookies загружены из {COOKIES_FILE}")
            return True
    except Exception as e:
        print(f"⚠️ Ошибка при загрузке cookies: {e}")
    return False


# --- Главная функция ---
def main():
    """Главная функция программы"""
    print("="*60)
    print("🚀 ЗАПУСК ПРОГРАММЫ СБОРА ДАННЫХ")
    print("="*60)
    
    with sync_playwright() as p:
        # Запуск браузера
        print(f"🌐 Запуск браузера (headless={HEADLESS})...")
        browser = p.chromium.launch(
            headless=HEADLESS,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        # Создание контекста браузера с настройками
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent=USER_AGENT,
            ignore_https_errors=True
        )
        
        # Создание новой страницы
        page = context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT)
        
        try:
            # Попытка загрузить cookies
            cookies_loaded = load_cookies(context)
            
            # Авторизация
            if not login_and_navigate(page):
                print("❌ Не удалось авторизоваться. Завершение работы.")
                return
            
            # Сохранение cookies после успешной авторизации
            save_cookies(context)
            
            # Удаление folder_container элементов
            remove_folder_container(page)
            
            # Получение последней позиции прокрутки
            start_position = get_last_position()
            print(f"📍 Начинаем с позиции: {start_position}px")
            
            # Запуск процесса сбора данных
            print("="*60)
            print("📊 НАЧАЛО СБОРА ДАННЫХ")
            print("="*60)
            total_records = scroll_to_load_table_container(page, start_position)
            
            print("="*60)
            print(f"✅ Сбор данных завершен. Всего собрано {total_records} записей.")
            print("="*60)
            
            # Обработка собранных данных
            print("🔄 Начинаем обработку собранных данных...")
            process_html_to_excel()
            print("="*60)
            print(f"✅ ПРОГРАММА ЗАВЕРШЕНА УСПЕШНО")
            print(f"📁 Результат сохранен в файл: {FINAL_EXCEL}")
            print("="*60)
            
        except KeyboardInterrupt:
            print("\n⚠️ Программа прервана пользователем")
            save_last_position(0)
        except Exception as e:
            print(f"❌ Критическая ошибка в main(): {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Закрытие браузера
            print("🛑 Закрытие браузера...")
            context.close()
            browser.close()
            print("✅ Браузер закрыт.")


if __name__ == "__main__":
    main()
