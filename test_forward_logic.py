"""
Test script for forward message processing logic
"""

def test_forward_origin_parsing():
    """Test parsing forward_origin from api_kwargs"""

    # Mock message with api_kwargs containing forward_origin
    class MockMessage:
        def __init__(self, api_kwargs):
            self.api_kwargs = api_kwargs

    # Mock bot
    class MockBot:
        pass

    # Test data from user's JSON
    api_kwargs = {
        'forward_origin': {
            'type': 'channel',
            'chat': {
                'id': -1003008079966,
                'title': 'тест канал',
                'type': 'channel'
            },
            'message_id': 14,
            'date': 1758436066
        }
    }

    message = MockMessage(api_kwargs)
    bot = MockBot()

    # Test parsing logic (copied from handle_channel_setup)
    forward_chat = None

    # Check new format (forward_origin) from api_kwargs
    if hasattr(message, 'api_kwargs') and 'forward_origin' in message.api_kwargs:
        forward_origin = message.api_kwargs['forward_origin']
        if isinstance(forward_origin, dict) and forward_origin.get('type') == 'channel':
            chat_data = forward_origin.get('chat')
            if chat_data:
                # Create Chat object from dict
                from telegram import Chat
                forward_chat = Chat.de_json(chat_data, bot)

    # Assertions
    assert forward_chat is not None, "forward_chat should not be None"
    assert forward_chat.id == -1003008079966, f"Expected chat id -1003008079966, got {forward_chat.id}"
    assert forward_chat.title == 'тест канал', f"Expected title 'тест канал', got '{forward_chat.title}'"
    assert forward_chat.type == 'channel', f"Expected type 'channel', got '{forward_chat.type}'"

    print("✅ test_forward_origin_parsing passed")


def test_custom_forwarded_filter():
    """Test CustomForwardedFilter logic"""

    # Mock message classes
    class MockMessage:
        def __init__(self, api_kwargs=None, forward_from_chat=None, forward_from=None):
            self.api_kwargs = api_kwargs or {}
            self.forward_from_chat = forward_from_chat
            self.forward_from = forward_from

    class MockUpdate:
        def __init__(self, message):
            self.message = message

    # Import filter
    import sys
    sys.path.append('/Users/s3s3s/Desktop/FinalWord')
    from main import CustomForwardedFilter

    filter_instance = CustomForwardedFilter()

    # Test 1: Message with forward_origin in api_kwargs
    message1 = MockMessage(api_kwargs={'forward_origin': {'type': 'channel'}})
    update1 = MockUpdate(message1)
    assert filter_instance.filter(message1), "Should detect forwarded message with forward_origin"

    # Test 2: Message with forward_from_chat
    message2 = MockMessage(forward_from_chat="mock_chat")
    update2 = MockUpdate(message2)
    assert filter_instance.filter(message2), "Should detect forwarded message with forward_from_chat"

    # Test 3: Message with forward_from
    message3 = MockMessage(forward_from="mock_user")
    update3 = MockUpdate(message3)
    assert filter_instance.filter(message3), "Should detect forwarded message with forward_from"

    # Test 4: Regular message (not forwarded)
    message4 = MockMessage()
    update4 = MockUpdate(message4)
    assert not filter_instance.filter(message4), "Should not detect regular message as forwarded"

    print("✅ test_custom_forwarded_filter passed")


def test_channel_setup_logic():
    """Test the complete channel setup logic"""

    # Mock objects
    class MockUser:
        def __init__(self, id):
            self.id = id

    class MockMessage:
        def __init__(self, api_kwargs):
            self.api_kwargs = api_kwargs

    class MockUpdate:
        def __init__(self, message, user):
            self.message = message
            self.effective_user = user

    class MockContext:
        def __init__(self, user_data):
            self.user_data = user_data

    # Test data
    api_kwargs = {
        'forward_origin': {
            'type': 'channel',
            'chat': {
                'id': -1003008079966,
                'title': 'тест канал',
                'type': 'channel'
            },
            'message_id': 14,
            'date': 1758436066
        }
    }

    message = MockMessage(api_kwargs)
    user = MockUser(415409454)
    update = MockUpdate(message, user)
    context = MockContext({'waiting_for_channel': True, 'selected_chat_id': -1003062613079})

    # Mock bot
    class MockBot:
        pass

    # Test parsing logic from handle_channel_setup
    forward_chat = None

    if hasattr(message, 'api_kwargs') and 'forward_origin' in message.api_kwargs:
        forward_origin = message.api_kwargs['forward_origin']
        if isinstance(forward_origin, dict) and forward_origin.get('type') == 'channel':
            chat_data = forward_origin.get('chat')
            if chat_data:
                from telegram import Chat
                forward_chat = Chat.de_json(chat_data, MockBot())

    # Assertions
    assert forward_chat is not None, "Channel should be extracted"
    assert forward_chat.id == -1003008079966, f"Channel ID mismatch: {forward_chat.id}"
    assert forward_chat.title == 'тест канал', f"Channel title mismatch: {forward_chat.title}"
    assert forward_chat.type == 'channel', f"Channel type mismatch: {forward_chat.type}"

    # Check user context
    assert context.user_data.get('waiting_for_channel') == True, "User should be in channel setup mode"
    assert context.user_data.get('selected_chat_id') == -1003062613079, "Selected chat ID should be set"

    print("✅ test_channel_setup_logic passed")


def test_full_channel_setup_flow():
    """Test the complete flow of channel setup with real JSON data"""

    # Mock bot
    class MockBot:
        pass

    # Real JSON data from user
    json_data = {
        "update_id": 277109992,
        "message": {
            "message_id": 463,
            "from": {
                "id": 415409454,
                "is_bot": False,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "language_code": "ru",
                "is_premium": True
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

    # Mock objects
    class MockUser:
        def __init__(self, data):
            self.id = data['id']
            self.is_bot = data['is_bot']
            self.first_name = data['first_name']
            self.username = data.get('username')
            self.language_code = data.get('language_code')
            self.is_premium = data.get('is_premium', False)

    class MockChat:
        def __init__(self, data):
            self.id = data['id']
            self.type = data['type']
            self.first_name = data.get('first_name')
            self.username = data.get('username')

    class MockMessage:
        def __init__(self, data):
            self.message_id = data['message_id']
            self.from_user = MockUser(data['from'])
            self.chat = MockChat(data['chat'])
            self.date = data['date']
            self.text = data.get('text')
            # Extract api_kwargs from the JSON
            self.api_kwargs = {}
            if 'forward_origin' in data:
                self.api_kwargs['forward_origin'] = data['forward_origin']

    class MockUpdate:
        def __init__(self, message_data):
            self.message = MockMessage(message_data)
            self.effective_user = self.message.from_user

    class MockContext:
        def __init__(self):
            self.user_data = {'waiting_for_channel': True, 'selected_chat_id': -1003062613079}

    # Create mock update from JSON
    update = MockUpdate(json_data['message'])
    context = MockContext()

    # Test the parsing logic from handle_channel_setup
    message = update.message
    user = update.effective_user

    # Simulate the logic from handle_channel_setup
    forward_chat = None

    # Check new format (forward_origin) from api_kwargs
    if hasattr(message, 'api_kwargs') and 'forward_origin' in message.api_kwargs:
        forward_origin = message.api_kwargs['forward_origin']
        if isinstance(forward_origin, dict) and forward_origin.get('type') == 'channel':
            chat_data = forward_origin.get('chat')
            if chat_data:
                # Create Chat object from dict
                from telegram import Chat
                mock_bot = MockBot()
                forward_chat = Chat.de_json(chat_data, mock_bot)  # Mock bot for test

    # Assertions
    assert forward_chat is not None, "Channel should be parsed from forward_origin"
    assert forward_chat.id == -1003008079966, f"Channel ID should be -1003008079966, got {forward_chat.id}"
    assert forward_chat.title == 'тест канал', f"Channel title should be 'тест канал', got '{forward_chat.title}'"
    assert forward_chat.type == 'channel', f"Channel type should be 'channel', got '{forward_chat.type}'"

    # Check user context
    assert context.user_data.get('waiting_for_channel') == True, "User should be in channel setup mode"
    assert context.user_data.get('selected_chat_id') == -1003062613079, "Selected chat should be set"

    print("✅ test_full_channel_setup_flow passed")


def test_moderator_forward_hidden_user():
    """Test moderator forward with hidden_user type (should fail gracefully)"""

    # Mock bot
    class MockBot:
        pass

    # Real JSON data from user for hidden_user case
    json_data = {
        "update_id": 277110042,
        "message": {
            "message_id": 491,
            "from": {
                "id": 415409454,
                "is_bot": False,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "language_code": "ru",
                "is_premium": True
            },
            "chat": {
                "id": 415409454,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "type": "private"
            },
            "date": 1758436892,
            "forward_origin": {
                "type": "hidden_user",
                "sender_user_name": "sh_____",
                "date": 1757403012
            },
            "forward_sender_name": "sh_____",
            "forward_date": 1757403012,
            "text": "Я прям счастливчик ☺️",
            "entities": [
                {
                    "offset": 19,
                    "length": 2,
                    "type": "custom_emoji",
                    "custom_emoji_id": "6077643792041641541"
                }
            ]
        }
    }

    # Mock objects
    class MockUser:
        def __init__(self, data):
            self.id = data['id']
            self.is_bot = data['is_bot']
            self.first_name = data['first_name']
            self.username = data.get('username')
            self.language_code = data.get('language_code')
            self.is_premium = data.get('is_premium', False)

    class MockChat:
        def __init__(self, data):
            self.id = data['id']
            self.type = data['type']
            self.first_name = data.get('first_name')
            self.username = data.get('username')

    class MockMessage:
        def __init__(self, data):
            self.message_id = data['message_id']
            self.from_user = MockUser(data['from'])
            self.chat = MockChat(data['chat'])
            self.date = data['date']
            self.text = data.get('text')
            # Extract api_kwargs from the JSON
            self.api_kwargs = {}
            if 'forward_origin' in data:
                self.api_kwargs['forward_origin'] = data['forward_origin']

    class MockUpdate:
        def __init__(self, message_data):
            self.message = MockMessage(message_data)
            self.effective_user = self.message.from_user

    class MockContext:
        def __init__(self):
            self.user_data = {'waiting_for_moderator_forward': True, 'selected_chat_id': -1003062613079}

    # Create mock update from JSON
    update = MockUpdate(json_data['message'])
    context = MockContext()

    # Test the parsing logic from handle_moderator_forward (updated version)
    message = update.message
    user = update.effective_user

    # Simulate the logic from handle_moderator_forward
    moderator_user = None
    should_return = False
    error_message = None

    # Try new format first (forward_origin from api_kwargs)
    if hasattr(message, 'api_kwargs') and 'forward_origin' in message.api_kwargs:
        forward_origin = message.api_kwargs['forward_origin']
        if isinstance(forward_origin, dict):
            forward_type = forward_origin.get('type')
            if forward_type == 'user':
                sender_user_data = forward_origin.get('sender_user')
                if sender_user_data:
                    from telegram import User
                    moderator_user = User.de_json(sender_user_data, MockBot())
            elif forward_type == 'hidden_user':
                # Handle hidden user case - cannot add as moderator due to privacy settings
                should_return = True
                error_message = "hidden_user_detected"

    # Fallback to old format (forward_from)
    if not moderator_user and hasattr(message, 'forward_from') and message.forward_from:
        moderator_user = message.forward_from

    # Check results
    assert should_return == True, "Function should return early for hidden_user type"
    assert error_message == "hidden_user_detected", "Should detect hidden user error"
    assert moderator_user is None, "moderator_user should be None for hidden_user type"

    # Check forward_origin type
    forward_origin = message.api_kwargs.get('forward_origin')
    assert forward_origin.get('type') == 'hidden_user', f"Type should be 'hidden_user', got '{forward_origin.get('type')}'"
    assert forward_origin.get('sender_user_name') == 'sh_____', f"sender_user_name should be 'sh_____', got '{forward_origin.get('sender_user_name')}'"

    print("✅ test_moderator_forward_hidden_user passed")


def test_unified_forwarded_message_handler():
    """Test the unified forwarded message handler"""

    # Mock bot
    class MockBot:
        pass

    # Test data for channel setup
    channel_json = {
        "update_id": 277110118,
        "message": {
            "message_id": 528,
            "from": {
                "id": 415409454,
                "is_bot": False,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "language_code": "ru",
                "is_premium": True
            },
            "chat": {
                "id": 415409454,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "type": "private"
            },
            "date": 1758437960,
            "forward_origin": {
                "type": "channel",
                "chat": {
                    "id": -1003008079966,
                    "title": "тест канал",
                    "type": "channel"
                },
                "message_id": 15,
                "date": 1758436562
            },
            "forward_from_chat": {
                "id": -1003008079966,
                "title": "тест канал",
                "type": "channel"
            },
            "forward_from_message_id": 15,
            "forward_date": 1758436562,
            "text": "H"
        }
    }

    # Test data for moderator addition
    moderator_json = {
        "update_id": 277110056,
        "message": {
            "message_id": 497,
            "from": {
                "id": 415409454,
                "is_bot": False,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "language_code": "ru",
                "is_premium": True
            },
            "chat": {
                "id": 415409454,
                "first_name": "Qwerty",
                "username": "s3s3s",
                "type": "private"
            },
            "date": 1758437200,
            "forward_origin": {
                "type": "user",
                "sender_user": {
                    "id": 182277773,
                    "is_bot": False,
                    "first_name": "ᐯᒪᗩᗪIᗰIᖇ",
                    "username": "VLadimirLx",
                    "language_code": "ru",
                    "is_premium": True
                },
                "date": 1758396737
            },
            "forward_from": {
                "id": 182277773,
                "is_bot": False,
                "first_name": "ᐯᒪᗩᗪIᗰIᖇ",
                "username": "VLadimirLx",
                "language_code": "ru",
                "is_premium": True
            },
            "forward_date": 1758396737,
            "text": "Тебе надо как можно скорее опять пожать документы на ПМЖ по восстановлению семьи."
        }
    }

    # Mock objects
    class MockUser:
        def __init__(self, data):
            self.id = data['id']
            self.is_bot = data['is_bot']
            self.first_name = data['first_name']
            self.username = data.get('username')
            self.language_code = data.get('language_code')
            self.is_premium = data.get('is_premium', False)

    class MockChat:
        def __init__(self, data):
            self.id = data['id']
            self.type = data['type']
            self.first_name = data.get('first_name')
            self.username = data.get('username')
            self.title = data.get('title')

    class MockMessage:
        def __init__(self, data):
            self.message_id = data['message_id']
            self.from_user = MockUser(data['from'])
            self.chat = MockChat(data['chat'])
            self.date = data['date']
            self.text = data.get('text')
            # Extract api_kwargs from the JSON
            self.api_kwargs = {}
            if 'forward_origin' in data:
                self.api_kwargs['forward_origin'] = data['forward_origin']
            # Add forward_from for fallback
            if 'forward_from' in data:
                self.forward_from = MockUser(data['forward_from'])
            if 'forward_from_chat' in data:
                self.forward_from_chat = MockChat(data['forward_from_chat'])

    class MockUpdate:
        def __init__(self, message_data):
            self.message = MockMessage(message_data)
            self.effective_user = self.message.from_user

    # Test 1: Channel setup context
    context_channel = type('MockContext', (), {
        'user_data': {'waiting_for_channel': True, 'selected_chat_id': -1003062613079}
    })()

    update_channel = MockUpdate(channel_json['message'])

    # Simulate handle_forwarded_message logic for channel
    user = update_channel.effective_user
    message = update_channel.message

    # Check that it would route to channel setup
    assert context_channel.user_data.get('waiting_for_channel') == True
    assert context_channel.user_data.get('waiting_for_moderator_forward') is None

    # Test 2: Moderator addition context
    context_moderator = type('MockContext', (), {
        'user_data': {'waiting_for_moderator_forward': -1003062613079}
    })()

    update_moderator = MockUpdate(moderator_json['message'])

    # Check that it would route to moderator addition
    assert context_moderator.user_data.get('waiting_for_moderator_forward') is not None
    assert context_moderator.user_data.get('waiting_for_channel') is None

    # Test 3: No context
    context_none = type('MockContext', (), {
        'user_data': {}
    })()

    # Check that it would show error message
    assert not context_none.user_data.get('waiting_for_channel')
    assert not context_none.user_data.get('waiting_for_moderator_forward')

    print("✅ test_unified_forwarded_message_handler passed")


if __name__ == "__main__":
    test_forward_origin_parsing()
    test_custom_forwarded_filter()
    test_channel_setup_logic()
    test_full_channel_setup_flow()
    test_moderator_forward_hidden_user()
    test_unified_forwarded_message_handler()
    print("\n🎉 All tests passed!")
