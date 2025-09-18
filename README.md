# Telegram Bot для мониторинга редактируемых сообщений

Бот отслеживает редактирование сообщений в групповых чатах и пересылает их в указанные каналы.

## Функционал

- Отслеживание редактируемых сообщений в чатах
- Пересылка оригинального и отредактированного сообщения в канал
- Удаление отредактированного сообщения из группы
- Игнорирование сообщений администраторов
- Поддержка нескольких администраторов

## Установка и запуск

### 1. Требования
- Python 3.8+
- MySQL 5.7+
- Telegram Bot Token

### 2. Клонирование и установка
```bash
git clone <repository-url>
cd FinalWord
python3 -m venv venv
source venv/bin/activate  # для Linux/Mac
# или venv\Scripts\activate для Windows
pip install -r requirements.txt
```

### 3. Настройка базы данных
```sql
CREATE DATABASE final CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Конфигурация
```bash
cp .env.example .env
```

Заполните `.env` файл:
```env
TELEGRAM_BOT_TOKEN=ваш_токен_бота
DATABASE_URL=mysql://username:password@localhost/final?charset=utf8mb4
WEBHOOK_URL=https://your-domain.com/webhook
WEBHOOK_PORT=8000
```

### 5. Получение токена бота
1. Напишите @BotFather в Telegram
2. Создайте нового бота командой `/newbot`
3. Скопируйте токен в `.env`

### 6. Настройка webhook (для продакшена)
- Используйте публичный HTTPS URL
- Для разработки: `ngrok http 8000`

### 7. Запуск
```bash
python main.py
```

## Настройка бота

1. **Добавьте бота в групповой чат** как администратора с правами на удаление сообщений
2. **Добавьте бота в канал** как администратора с правами на отправку сообщений
3. **Свяжите чат с каналом**: напишите боту `/chats` в личные сообщения и следуйте инструкциям

## Команды
- `/start` - Информация о боте
- `/chats` - Настройка связи чат ↔ канал

## Структура проекта
```
FinalWord/
├── main.py          # Точка входа
├── .env             # Конфигурация
├── requirements.txt # Зависимости
├── bot/
│   ├── database/    # Работа с MySQL
│   ├── handlers/    # Обработчики команд и сообщений
│   └── utils/       # Утилиты и конфиг
└── logs/            # Логи бота
```

## Лицензия
MIT License