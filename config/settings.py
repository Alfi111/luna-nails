import os

# Настройки бота
BOT_TOKEN = os.environ.get('BOT_TOKEN')
SPREADSHEET_ID = os.environ.get('SPREADSHEET_ID')
MASTER_CHAT_ID = os.environ.get('MASTER_CHAT_ID', '')
MASTER_USER_ID = os.environ.get('MASTER_USER_ID', '')

# Проверка обязательных переменных
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен")
if not SPREADSHEET_ID:
    raise ValueError("SPREADSHEET_ID не установлен")

# Настройки времени работы
WORK_START = 9
WORK_END = 21
SLOT_DURATION = 60

# Этапы разговора
(
    START, NAME, PHONE, PHONE_CHOICE, PHONE_MANUAL,
    SERVICE, DATE, TIME, CONFIRMATION,
    MASTER_MENU, VIEW_BOOKINGS, CANCEL_BOOKING
) = range(12)
