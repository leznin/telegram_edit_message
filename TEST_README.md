# Тесты для логики обработки пересланных сообщений

## Обзор исправлений

Проблема была в том, что Telegram ввел новый формат пересылки сообщений (`forward_origin`), но версия python-telegram-bot 20.7 не поддерживает его в объектах Message. Вместо этого информация хранится в `api_kwargs`.

## Исправления

1. **Кастомный фильтр пересланных сообщений** (`CustomForwardedFilter` в `main.py`):
   - Проверяет как старый формат (`forward_from`, `forward_from_chat`), так и новый (`forward_origin` в `api_kwargs`)

2. **Обработка каналов** (`handle_channel_setup` в `commands.py`):
   - Извлекает информацию о канале из `api_kwargs['forward_origin']['chat']`
   - Создает объект `Chat` из данных в `api_kwargs`

3. **Обработка модераторов** (`handle_moderator_forward` в `commands.py`):
   - Извлекает информацию о пользователе из `api_kwargs['forward_origin']['sender_user']`

4. **Порядок обработчиков**:
   - `handle_channel_setup` теперь регистрируется ПЕРЕД `handle_moderator_forward`
   - Это предотвращает конфликты между обработчиками

## Запуск тестов

```bash
cd /Users/s3s3s/Desktop/FinalWord
source venv/bin/activate
python3 test_forward_logic.py
```

## Тесты

### 1. test_forward_origin_parsing
Проверяет корректность парсинга `forward_origin` из `api_kwargs`.

### 2. test_custom_forwarded_filter
Проверяет логику кастомного фильтра пересланных сообщений.

### 3. test_channel_setup_logic
Проверяет логику настройки канала с mock-объектами.

### 4. test_full_channel_setup_flow
Проверяет полный процесс с реальными JSON данными от Telegram.

## Результаты тестирования

```
✅ test_forward_origin_parsing passed
✅ test_custom_forwarded_filter passed
✅ test_channel_setup_logic passed
✅ test_full_channel_setup_flow passed

🎉 All tests passed!
```

## JSON пример для тестирования

```json
{
    "update_id": 277109992,
    "message": {
        "message_id": 463,
        "from": {
            "id": 415409454,
            "is_bot": false,
            "first_name": "Qwerty",
            "username": "s3s3s",
            "language_code": "ru",
            "is_premium": true
        },
        "chat": {
            "id": 415409454,
            "first_name": "Qwerty",
            "username": "s3s3s",
            "type": "private"
        },
        "date": 1758436069,
        "forward_origin": {
            "type": "channel",
            "chat": {
                "id": -1003008079966,
                "title": "тест канал",
                "type": "channel"
            },
            "message_id": 14,
            "date": 1758436066
        },
        "forward_from_chat": {
            "id": -1003008079966,
            "title": "тест канал",
            "type": "channel"
        },
        "forward_from_message_id": 14,
        "forward_date": 1758436066,
        "text": "V"
    }
}
```

Этот JSON теперь корректно обрабатывается ботом для настройки канала пересылки.
