# Nail Salon Telegram Bot

Бот для записи клиентов в салон красоты с интеграцией Google Sheets.

## Установка на Heroku

1. Клонируйте репозиторий
2. Создайте приложение в Heroku
3. Установите переменные окружения:
   - `BOT_TOKEN` - токен от @BotFather
   - `SPREADSHEET_ID` - ID Google таблицы
   - `MASTER_CHAT_ID` - ID чата мастера для уведомлений
   - `MASTER_USER_ID` - ID пользователя мастера
   - `GOOGLE_CREDENTIALS` - JSON с ключами сервисного аккаунта

4. Деплой:
```bash
git push heroku main
heroku ps:scale worker=1
