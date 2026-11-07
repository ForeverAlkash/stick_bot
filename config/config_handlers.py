import logging
import os
import asyncio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def cleanup_temp_files():
    """Удаляет все временные файлы"""
    import glob
    temp_patterns = ['temp_sticker*', '*.webp']
    for pattern in temp_patterns:
        try:
            for file in glob.glob(pattern):
                try:
                    # Закрываем файл если он открыт
                    import gc
                    gc.collect()
                    
                    # Пытаемся удалить несколько раз
                    for attempt in range(3):
                        try:
                            os.remove(file)
                            logger.info(f'🗑️ Удалён временный файл: {file}')
                            break
                        except (OSError, PermissionError) as e:
                            if attempt < 2:
                                asyncio.sleep(0.1)
                            else:
                                logger.warning(f'Не удалось удалить {file} после 3 попыток: {e}')
                except Exception as e:
                    logger.warning(f'Ошибка при удалении {file}: {e}')
        except Exception as e:
            logger.warning(f'Ошибка при очистке {pattern}: {e}')


async def delete_message_after(message, delay=5):
    """Удаляет сообщение через указанное количество секунд"""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception as e:
        logger.warning(f'Не удалось удалить сообщение об ошибке: {e}')


