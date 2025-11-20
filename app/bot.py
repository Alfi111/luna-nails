import os
import logging
import json
from datetime import datetime, timedelta
from telegram import (
    Update, 
    ReplyKeyboardMarkup, 
    ReplyKeyboardRemove, 
    InlineKeyboardMarkup, 
    InlineKeyboardButton,
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    JobQueue
)
import gspread
from google.oauth2.service_account import Credentials
from config.settings import (
    BOT_TOKEN, SPREADSHEET_ID, MASTER_CHAT_ID, MASTER_USER_ID,
    WORK_START, WORK_END, SLOT_DURATION,
    START, NAME, PHONE, PHONE_CHOICE, PHONE_MANUAL,
    SERVICE, DATE, TIME, CONFIRMATION,
    MASTER_MENU, VIEW_BOOKINGS, CANCEL_BOOKING
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка доступа к Google Sheets
def get_google_sheet(sheet_name="clients"):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Для Heroku используем переменные окружения
    if os.environ.get('GOOGLE_CREDENTIALS'):
        creds_info = json.loads(os.environ['GOOGLE_CREDENTIALS'])
        creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    else:
        raise ValueError("GOOGLE_CREDENTIALS не установлены")
    
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).worksheet(sheet_name)

class NailSalonBot:
    def __init__(self):
        self.user_data = {}
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начало работы с ботом - регистрация или меню"""
        user = update.message.from_user
        user_id = str(user.id)
        
        # Проверяем, есть ли клиент в базе
        try:
            sheet = get_google_sheet("clients")
            clients = sheet.get_all_records()
            existing_client = next((c for c in clients if str(c.get('user_id')) == user_id), None)
            
            if existing_client:
                # Клиент уже зарегистрирован
                await self.show_main_menu(update, context)
                return ConversationHandler.END
            else:
                # Новый клиент - начинаем регистрацию
                context.user_data['user_id'] = user_id
                context.user_data['username'] = user.username
                context.user_data['first_name'] = user.first_name
                context.user_data['last_name'] = user.last_name
                
                await update.message.reply_text(
                    f"👋 Привет, {user.first_name}!\n"
                    "Я - бот салона красоты 'Ваш Мастер'!\n"
                    "Для начала давай познакомимся.\n\n"
                    "Как тебя зовут? (Укажи имя, которое будет в записи)"
                )
                return NAME
                
        except Exception as e:
            logging.error(f"Ошибка при проверке клиента: {e}")
            await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте позже.")
            return ConversationHandler.END

    async def get_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получаем имя клиента"""
        context.user_data['client_name'] = update.message.text
        
        # Создаем клавиатуру для выбора способа ввода телефона
        keyboard = [
            [KeyboardButton("📱 Отправить мой номер", request_contact=True)],
            [KeyboardButton("Ввести номер вручную")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        
        await update.message.reply_text(
            "Отлично! Теперь нужен твой номер телефона для связи и напоминаний.",
            reply_markup=reply_markup
        )
        return PHONE_CHOICE

    async def handle_phone_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора способа ввода телефона"""
        if update.message.contact:
            # Пользователь отправил контакт
            context.user_data['phone'] = update.message.contact.phone_number
            return await self.save_client_data(update, context)
        else:
            # Пользователь хочет ввести номер вручную
            await update.message.reply_text(
                "Введи свой номер телефона в формате:\n"
                "+7XXXYYYZZWW или 8XXXYYYZZWW",
                reply_markup=ReplyKeyboardRemove()
            )
            return PHONE_MANUAL

    async def get_phone_manual(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Получаем телефон, введенный вручную"""
        phone = update.message.text
        # Простая валидация номера
        if len(phone) >= 10 and any(char.isdigit() for char in phone):
            context.user_data['phone'] = phone
            return await self.save_client_data(update, context)
        else:
            await update.message.reply_text("Пожалуйста, введите корректный номер телефона:")
            return PHONE_MANUAL

    async def save_client_data(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Сохраняем данные клиента в таблицу"""
        try:
            sheet = get_google_sheet("clients")
            
            client_data = [
                context.user_data.get('user_id', ''),
                context.user_data.get('client_name', ''),
                context.user_data.get('phone', ''),
                context.user_data.get('username', ''),
                context.user_data.get('first_name', ''),
                context.user_data.get('last_name', ''),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ]
            
            sheet.append_row(client_data)
            
            await update.message.reply_text(
                "✅ Регистрация завершена!\n\n"
                f"Имя: {context.user_data['client_name']}\n"
                f"Телефон: {context.user_data['phone']}\n\n"
                "Теперь ты можешь записываться на услуги!",
                reply_markup=ReplyKeyboardRemove()
            )
            
            await self.show_main_menu(update, context)
            return ConversationHandler.END
            
        except Exception as e:
            logging.error(f"Ошибка при сохранении клиента: {e}")
            await update.message.reply_text("Произошла ошибка при сохранении данных. Попробуйте позже.")
            return ConversationHandler.END

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показываем главное меню"""
        keyboard = [
            ["💅 Записаться на услугу"],
            ["📋 Мои записи", "❌ Отменить запись"],
            ["👨‍💼 Режим мастера"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        if update.message:
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.message.reply_text(
                "Выберите действие:",
                reply_markup=reply_markup
            )

    async def start_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинаем процесс записи на услугу"""
        user_id = str(update.effective_user.id)
        
        # Проверяем, зарегистрирован ли пользователь
        try:
            sheet = get_google_sheet("clients")
            clients = sheet.get_all_records()
            client = next((c for c in clients if str(c.get('user_id')) == user_id), None)
            
            if not client:
                await update.message.reply_text("Сначала нужно завершить регистрацию. Напишите /start")
                return ConversationHandler.END
                
            context.user_data['booking_client'] = client
            
        except Exception as e:
            logging.error(f"Ошибка при проверке клиента: {e}")
            await update.message.reply_text("Произошла ошибка. Попробуйте позже.")
            return ConversationHandler.END
        
        # Получаем список услуг
        try:
            services_sheet = get_google_sheet("services")
            services = services_sheet.get_all_records()
            
            if not services:
                keyboard = [[InlineKeyboardButton("Маникюр", callback_data="service_Маникюр")],
                          [InlineKeyboardButton("Педикюр", callback_data="service_Педикюр")],
                          [InlineKeyboardButton("Покрытие", callback_data="service_Покрытие")]]
            else:
                keyboard = []
                for service in services:
                    service_name = service.get('name', 'Услуга')
                    service_price = service.get('price', '')
                    button_text = f"{service_name} - {service_price}₽" if service_price else service_name
                    keyboard.append([InlineKeyboardButton(button_text, callback_data=f"service_{service_name}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Выберите услугу:", reply_markup=reply_markup)
            return SERVICE
            
        except Exception as e:
            logging.error(f"Ошибка при получении услуг: {e}")
            await update.message.reply_text("Произошла ошибка при загрузке услуг.")
            return ConversationHandler.END

    async def select_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора услуги"""
        query = update.callback_query
        await query.answer()
        
        service = query.data.replace("service_", "")
        context.user_data['service'] = service
        
        # Показываем календарь на 2 недели вперед
        await self.show_calendar(query.message, context)
        return DATE

    async def show_calendar(self, message, context: ContextTypes.DEFAULT_TYPE, month_offset=0):
        """Показываем инлайн-календарь"""
        today = datetime.now()
        target_date = today.replace(day=1) + timedelta(days=32 * month_offset)
        target_date = target_date.replace(day=1)
        
        # Создаем календарь
        keyboard = []
        
        # Заголовок с месяцем и годом
        month_name = target_date.strftime("%B %Y")
        header = [
            InlineKeyboardButton("←", callback_data=f"prev_month_{month_offset}"),
            InlineKeyboardButton(month_name, callback_data="ignore"),
            InlineKeyboardButton("→", callback_data=f"next_month_{month_offset}")
        ]
        keyboard.append(header)
        
        # Дни недели
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in week_days])
        
        # Ячейки календаря
        first_day = target_date.replace(day=1)
        last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        
        current_row = []
        # Пустые ячейки до первого дня
        for _ in range((first_day.weekday()) % 7):
            current_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
        
        current_day = first_day
        while current_day <= last_day:
            if len(current_row) == 7:
                keyboard.append(current_row)
                current_row = []
            
            if current_day >= today.date():
                date_str = current_day.strftime("%Y-%m-%d")
                current_row.append(InlineKeyboardButton(str(current_day.day), callback_data=f"date_{date_str}"))
            else:
                current_row.append(InlineKeyboardButton(" ", callback_data="ignore"))
            
            current_day += timedelta(days=1)
        
        # Добавляем последнюю строку если нужно
        if current_row:
            keyboard.append(current_row)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(message, 'edit_text'):
            await message.edit_text("Выберите дату:", reply_markup=reply_markup)
        else:
            await message.reply_text("Выберите дату:", reply_markup=reply_markup)

    async def handle_calendar_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий в календаре"""
        query = update.callback_query
        data = query.data
        
        if data.startswith("date_"):
            selected_date = data.replace("date_", "")
            context.user_data['selected_date'] = selected_date
            await self.show_available_times(query.message, context)
            return TIME
            
        elif data.startswith("prev_month_"):
            month_offset = int(data.replace("prev_month_", "")) - 1
            await self.show_calendar(query.message, context, month_offset)
            
        elif data.startswith("next_month_"):
            month_offset = int(data.replace("next_month_", "")) + 1
            await self.show_calendar(query.message, context, month_offset)
        
        await query.answer()

    async def show_available_times(self, message, context: ContextTypes.DEFAULT_TYPE):
        """Показываем доступное время"""
        selected_date = context.user_data['selected_date']
        date_obj = datetime.strptime(selected_date, "%Y-%m-%d")
        
        # Получаем занятые слоты на эту дату
        try:
            appointments_sheet = get_google_sheet("appointments")
            appointments = appointments_sheet.get_all_records()
            
            booked_times = []
            for appt in appointments:
                appt_date = appt.get('date', '')
                appt_time = appt.get('time', '')
                appt_status = appt.get('status', '')
                
                if appt_date == selected_date and appt_status != 'cancelled':
                    booked_times.append(appt_time)
                    
        except Exception as e:
            logging.error(f"Ошибка при получении записей: {e}")
            booked_times = []
        
        # Создаем клавиатуру со свободными слотами
        keyboard = []
        current_time = datetime.strptime(f"{WORK_START}:00", "%H:%M")
        end_time = datetime.strptime(f"{WORK_END}:00", "%H:%M")
        
        while current_time <= end_time:
            time_str = current_time.strftime("%H:%M")
            if time_str not in booked_times:
                keyboard.append([InlineKeyboardButton(time_str, callback_data=f"time_{time_str}")])
            
            current_time += timedelta(minutes=SLOT_DURATION)
        
        if not keyboard:
            await message.edit_text("На эту дату нет свободных слотов. Выберите другую дату.")
            await self.show_calendar(message, context)
            return DATE
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(
            f"Выберите время на {date_obj.strftime('%d.%m.%Y')}:",
            reply_markup=reply_markup
        )

    async def select_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка выбора времени"""
        query = update.callback_query
        await query.answer()
        
        time_str = query.data.replace("time_", "")
        context.user_data['time'] = time_str
        
        # Подтверждение записи
        client = context.user_data['booking_client']
        service = context.user_data['service']
        date_str = context.user_data['selected_date']
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_yes"),
                InlineKeyboardButton("❌ Отменить", callback_data="confirm_no")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.message.edit_text(
            f"📋 Подтвердите запись:\n\n"
            f"👤 Клиент: {client.get('client_name', '')}\n"
            f"📞 Телефон: {client.get('phone', '')}\n"
            f"💅 Услуга: {service}\n"
            f"📅 Дата: {date_obj.strftime('%d.%m.%Y')}\n"
            f"⏰ Время: {time_str}",
            reply_markup=reply_markup
        )
        return CONFIRMATION

    async def confirm_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Подтверждение или отмена записи"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "confirm_yes":
            # Сохраняем запись
            try:
                appointments_sheet = get_google_sheet("appointments")
                client = context.user_data['booking_client']
                
                appointment_data = [
                    context.user_data.get('user_id', ''),
                    client.get('client_name', ''),
                    client.get('phone', ''),
                    context.user_data.get('service', ''),
                    context.user_data.get('selected_date', ''),
                    context.user_data.get('time', ''),
                    'confirmed',
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ''  # для заметок мастера
                ]
                
                appointments_sheet.append_row(appointment_data)
                
                # Получаем ID записи (последняя добавленная строка)
                all_records = appointments_sheet.get_all_records()
                appointment_id = len(all_records)
                
                context.user_data['appointment_id'] = appointment_id
                
                await query.message.edit_text(
                    "✅ Запись подтверждена!\n\n"
                    "Мы ждем вас в салоне! За день до визита пришлем напоминание."
                )
                
                # Уведомление мастеру
                if MASTER_CHAT_ID:
                    try:
                        await context.bot.send_message(
                            MASTER_CHAT_ID,
                            f"📥 Новая запись!\n"
                            f"Клиент: {client.get('client_name', '')}\n"
                            f"Телефон: {client.get('phone', '')}\n"
                            f"Услуга: {context.user_data.get('service', '')}\n"
                            f"Дата: {context.user_data.get('selected_date', '')}\n"
                            f"Время: {context.user_data.get('time', '')}"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка при отправке уведомления мастеру: {e}")
                
            except Exception as e:
                logging.error(f"Ошибка при сохранении записи: {e}")
                await query.message.edit_text("Произошла ошибка при сохранении записи. Попробуйте позже.")
        else:
            await query.message.edit_text("Запись отменена.")
        
        await self.show_main_menu(update, context)
        return ConversationHandler.END

    async def show_my_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показываем активные записи пользователя"""
        user_id = str(update.effective_user.id)
        
        try:
            appointments_sheet = get_google_sheet("appointments")
            appointments = appointments_sheet.get_all_records()
            
            user_appointments = []
            for i, appt in enumerate(appointments, 1):
                if (str(appt.get('user_id')) == user_id and 
                    appt.get('status') == 'confirmed'):
                    user_appointments.append((i, appt))
            
            if not user_appointments:
                await update.message.reply_text("У вас нет активных записей.")
                return
            
            message = "📋 Ваши активные записи:\n\n"
            for idx, (row_num, appt) in enumerate(user_appointments, 1):
                date_obj = datetime.strptime(appt.get('date', ''), "%Y-%m-%d")
                message += (
                    f"{idx}. 💅 {appt.get('service', '')}\n"
                    f"   📅 {date_obj.strftime('%d.%m.%Y')}\n"
                    f"   ⏰ {appt.get('time', '')}\n"
                    f"   ID: {row_num}\n\n"
                )
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logging.error(f"Ошибка при получении записей: {e}")
            await update.message.reply_text("Произошла ошибка при загрузке записей.")

    async def start_cancel_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Начинаем процесс отмены записи"""
        user_id = str(update.effective_user.id)
        
        try:
            appointments_sheet = get_google_sheet("appointments")
            appointments = appointments_sheet.get_all_records()
            
            user_appointments = []
            for i, appt in enumerate(appointments, 1):
                if (str(appt.get('user_id')) == user_id and 
                    appt.get('status') == 'confirmed'):
                    user_appointments.append((i, appt))
            
            if not user_appointments:
                await update.message.reply_text("У вас нет активных записей для отмены.")
                return ConversationHandler.END
            
            # Создаем клавиатуру с записями для отмены
            keyboard = []
            for idx, (row_num, appt) in enumerate(user_appointments, 1):
                date_obj = datetime.strptime(appt.get('date', ''), "%Y-%m-%d")
                button_text = f"{idx}. {date_obj.strftime('%d.%m')} {appt.get('time', '')} - {appt.get('service', '')}"
                keyboard.append([InlineKeyboardButton(button_text, callback_data=f"cancel_{row_num}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Выберите запись для отмены:",
                reply_markup=reply_markup
            )
            return CANCEL_BOOKING
            
        except Exception as e:
            logging.error(f"Ошибка при получении записей: {e}")
            await update.message.reply_text("Произошла ошибка.")
            return ConversationHandler.END

    async def cancel_booking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена выбранной записи"""
        query = update.callback_query
        await query.answer()
        
        appointment_id = int(query.data.replace("cancel_", ""))
        
        try:
            appointments_sheet = get_google_sheet("appointments")
            # Обновляем статус записи
            appointments_sheet.update_cell(appointment_id + 1, 7, 'cancelled')  # Столбец статуса
            
            # Получаем данные отмененной записи для уведомления мастера
            appointments = appointments_sheet.get_all_records()
            cancelled_appt = appointments[appointment_id - 1]
            
            await query.message.edit_text("✅ Запись отменена.")
            
            # Уведомление мастеру
            if MASTER_CHAT_ID:
                try:
                    await context.bot.send_message(
                        MASTER_CHAT_ID,
                        f"❌ Отмена записи!\n"
                        f"Клиент: {cancelled_appt.get('client_name', '')}\n"
                        f"Телефон: {cancelled_appt.get('phone', '')}\n"
                        f"Услуга: {cancelled_appt.get('service', '')}\n"
                        f"Дата: {cancelled_appt.get('date', '')}\n"
                        f"Время: {cancelled_appt.get('time', '')}"
                    )
                except Exception as e:
                    logging.error(f"Ошибка при отправке уведомления мастеру: {e}")
                    
        except Exception as e:
            logging.error(f"Ошибка при отмене записи: {e}")
            await query.message.edit_text("Произошла ошибка при отмене записи.")
        
        return ConversationHandler.END

    # Функции для мастера
    async def master_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Меню мастера (только для авторизованных пользователей)"""
        user_id = str(update.effective_user.id)
        
        # Проверяем, является ли пользователь мастером
        if user_id != MASTER_USER_ID:
            await update.message.reply_text("У вас нет доступа к этой функции.")
            return
        
        keyboard = [
            ["📊 Записи на сегодня", "📅 Записи на завтра"],
            ["🗓️ Все активные записи", "📈 Статистика"],
            ["🔙 Главное меню"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text("👨‍💼 Режим мастера:", reply_markup=reply_markup)
        return MASTER_MENU

    async def show_today_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показываем записи на сегодня"""
        await self.show_date_bookings(update, context, datetime.now().strftime("%Y-%m-%d"), "сегодня")

    async def show_tomorrow_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показываем записи на завтра"""
        tomorrow = datetime.now() + timedelta(days=1)
        await self.show_date_bookings(update, context, tomorrow.strftime("%Y-%m-%d"), "завтра")

    async def show_date_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str, date_display: str):
        """Показываем записи на указанную дату"""
        try:
            appointments_sheet = get_google_sheet("appointments")
            appointments = appointments_sheet.get_all_records()
            
            date_appointments = [
                appt for appt in appointments 
                if appt.get('date') == date_str and appt.get('status') == 'confirmed'
            ]
            
            if not date_appointments:
                await update.message.reply_text(f"На {date_display} записей нет.")
                return
            
            message = f"📋 Записи на {date_display}:\n\n"
            for i, appt in enumerate(sorted(date_appointments, key=lambda x: x.get('time', '')), 1):
                message += (
                    f"{i}. ⏰ {appt.get('time', '')}\n"
                    f"   👤 {appt.get('client_name', '')}\n"
                    f"   📞 {appt.get('phone', '')}\n"
                    f"   💅 {appt.get('service', '')}\n\n"
                )
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logging.error(f"Ошибка при получении записей: {e}")
            await update.message.reply_text("Произошла ошибка при загрузке записей.")

    async def show_all_active_bookings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показываем все активные записи"""
        try:
            appointments_sheet = get_google_sheet("appointments")
            appointments = appointments_sheet.get_all_records()
            
            active_appointments = [
                appt for appt in appointments 
                if appt.get('status') == 'confirmed' 
                and datetime.strptime(appt.get('date', ''), "%Y-%m-%d") >= datetime.now().date()
            ]
            
            if not active_appointments:
                await update.message.reply_text("Активных записей нет.")
                return
            
            # Группируем по датам
            appointments_by_date = {}
            for appt in active_appointments:
                date = appt.get('date', '')
                if date not in appointments_by_date:
                    appointments_by_date[date] = []
                appointments_by_date[date].append(appt)
            
            message = "🗓️ Все активные записи:\n\n"
            for date in sorted(appointments_by_date.keys()):
                date_obj = datetime.strptime(date, "%Y-%m-%d")
                message += f"📅 {date_obj.strftime('%d.%m.%Y')}:\n"
                
                for appt in sorted(appointments_by_date[date], key=lambda x: x.get('time', '')):
                    message += (
                        f"   ⏰ {appt.get('time', '')} - {appt.get('client_name', '')} "
                        f"({appt.get('phone', '')}) - {appt.get('service', '')}\n"
                    )
                message += "\n"
            
            await update.message.reply_text(message)
            
        except Exception as e:
            logging.error(f"Ошибка при получении записей: {e}")
            await update.message.reply_text("Произошла ошибка при загрузке записей.")

    # Функции напоминаний
    async def send_reminders(self, context: ContextTypes.DEFAULT_TYPE):
        """Отправка напоминаний за день до визита"""
        try:
            appointments_sheet = get_google_sheet("appointments")
            appointments = appointments_sheet.get_all_records()
            
            tomorrow = datetime.now() + timedelta(days=1)
            tomorrow_str = tomorrow.strftime("%Y-%m-%d")
            
            tomorrow_appointments = [
                appt for appt in appointments 
                if appt.get('date') == tomorrow_str and appt.get('status') == 'confirmed'
            ]
            
            for appt in tomorrow_appointments:
                user_id = appt.get('user_id', '')
                if user_id:
                    try:
                        await context.bot.send_message(
                            user_id,
                            f"🔔 Напоминание о записи!\n\n"
                            f"Завтра, {tomorrow.strftime('%d.%m.%Y')} в {appt.get('time', '')}\n"
                            f"У вас запись на: {appt.get('service', '')}\n\n"
                            f"Ждем вас в салоне! 🎉"
                        )
                    except Exception as e:
                        logging.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")
            
            # Уведомление мастеру о завтрашних записях
            if MASTER_CHAT_ID and tomorrow_appointments:
                message = f"📋 Записи на завтра ({tomorrow.strftime('%d.%m.%Y')}):\n\n"
                for i, appt in enumerate(sorted(tomorrow_appointments, key=lambda x: x.get('time', '')), 1):
                    message += (
                        f"{i}. ⏰ {appt.get('time', '')} - {appt.get('client_name', '')} "
                        f"({appt.get('phone', '')}) - {appt.get('service', '')}\n"
                    )
                
                try:
                    await context.bot.send_message(MASTER_CHAT_ID, message)
                except Exception as e:
                    logging.error(f"Ошибка при отправке напоминания мастеру: {e}")
                    
        except Exception as e:
            logging.error(f"Ошибка в функции напоминаний: {e}")

def main():
    """Запуск бота"""
    application = Application.builder().token(BOT_TOKEN).build()
    bot = NailSalonBot()
    
    # Добавляем job для ежедневных напоминаний
    job_queue = application.job_queue
    job_queue.run_daily(bot.send_reminders, time=datetime.time(hour=19, minute=0))  # Напоминания в 19:00
    
    # Обработчик регистрации нового пользователя
    reg_conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', bot.start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_name)],
            PHONE_CHOICE: [MessageHandler(filters.TEXT | filters.CONTACT, bot.handle_phone_choice)],
            PHONE_MANUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.get_phone_manual)],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_booking)]
    )
    
    # Обработчик записи на услугу
    booking_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^💅 Записаться на услугу$'), bot.start_booking)],
        states={
            SERVICE: [CallbackQueryHandler(bot.select_service, pattern='^service_')],
            DATE: [CallbackQueryHandler(bot.handle_calendar_callback, pattern='^(date_|prev_month_|next_month_)')],
            TIME: [CallbackQueryHandler(bot.select_time, pattern='^time_')],
            CONFIRMATION: [CallbackQueryHandler(bot.confirm_booking, pattern='^confirm_')],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_booking)]
    )
    
    # Обработчик отмены записи
    cancel_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^❌ Отменить запись$'), bot.start_cancel_booking)],
        states={
            CANCEL_BOOKING: [CallbackQueryHandler(bot.cancel_booking, pattern='^cancel_')],
        },
        fallbacks=[CommandHandler('cancel', bot.cancel_booking)]
    )
    
    # Обработчик меню мастера
    master_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^👨‍💼 Режим мастера$'), bot.master_menu)],
        states={
            MASTER_MENU: [
                MessageHandler(filters.Regex('^📊 Записи на сегодня$'), bot.show_today_bookings),
                MessageHandler(filters.Regex('^📅 Записи на завтра$'), bot.show_tomorrow_bookings),
                MessageHandler(filters.Regex('^🗓️ Все активные записи$'), bot.show_all_active_bookings),
                MessageHandler(filters.Regex('^🔙 Главное меню$'), bot.show_main_menu),
            ]
        },
        fallbacks=[]
    )
    
    # Добавляем все обработчики
    application.add_handler(reg_conv_handler)
    application.add_handler(booking_conv_handler)
    application.add_handler(cancel_conv_handler)
    application.add_handler(master_conv_handler)
    
    # Простые обработчики сообщений
    application.add_handler(MessageHandler(filters.Regex('^📋 Мои записи$'), bot.show_my_bookings))
    application.add_handler(MessageHandler(filters.Regex('^🔙 Главное меню$'), bot.show_main_menu))
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main()
