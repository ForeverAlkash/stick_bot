from telethon import TelegramClient, events
import os
import asyncio
import logging
from dotenv import load_dotenv

# Load configuration from environment variables
load_dotenv()
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH')
STICKERSET_NAME = os.getenv('STICKERSET_NAME', '')
STICKERSET_TITLE = os.getenv('STICKERSET_TITLE', '')

from config.config_handlers import logger, cleanup_temp_files, delete_message_after

# Optional: Telegram channel ID to forward stickers to (set in .env)
CHANNEL_ID = os.getenv('CHANNEL_ID')
if CHANNEL_ID:
    try:
        CHANNEL_ID = int(CHANNEL_ID)
    except ValueError:
        logger.warning(f'Invalid CHANNEL_ID value: {CHANNEL_ID}')
        CHANNEL_ID = None
else:
    CHANNEL_ID = None


client = TelegramClient('session', API_ID, API_HASH)

@client.on(events.NewMessage(from_users='me', pattern=r'!стик'))
async def handle_sticker_command(event):
    """Обработчик команды !стик"""
    from handlers.sticker_control import add_sticker_to_set
    stickerset_name = STICKERSET_NAME
    stickerset_title = STICKERSET_TITLE
    channel_id = CHANNEL_ID
    await add_sticker_to_set(event, client, stickerset_name, stickerset_title, channel_id=channel_id)

async def main():
    """Главная функция бота."""
    # Очистка временных файлов
    logger.info('🧹 Очистка старых временных файлов...')
    cleanup_temp_files()

    logger.info('Подключение к Telegram...')
    try:
        # Автоматическое соединение и аутентификация
        await client.start()
        me = await client.get_me()
        logger.info('✅ Клиент запущен и готов к работе!')
        logger.info(f'Пользователь: {me.first_name} ({me.id})')

        # Запуск прослушивания входящих сообщений
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f'Ошибка при запуске бота: {e}', exc_info=True)
        raise
    finally:
        if client.is_connected():
            await client.disconnect()
            logger.info('🔌 Клиент отключён.')

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info('Бот остановлен пользователем.')
    except Exception as e:
        logger.error(f'Критическая ошибка: {e}', exc_info=True)
