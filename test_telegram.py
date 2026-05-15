from notifications.telegram_service import send_telegram_message

response = send_telegram_message(
    "🚀 AI Email Agent connected successfully!"
)

print(response)