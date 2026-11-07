from telethon.tl.types import (
    InputStickerSetItem, 
    InputStickerSetShortName,
    InputMediaUploadedDocument,
    InputDocument,
    DocumentAttributeImageSize,
    DocumentAttributeVideo,
)
from telethon.tl.functions.stickers import (
    CreateStickerSetRequest, 
    AddStickerToSetRequest
)
from telethon.tl.functions.messages import GetStickerSetRequest, UploadMediaRequest, SendMessageRequest
from config.config_handlers import logger, cleanup_temp_files, delete_message_after
import os
import subprocess
import asyncio


def is_animated_sticker(file_path):
    """Проверяет, является ли файл GIF, видео или анимированный стикер по расширению и магическим байтам"""
    try:
        # Проверяем расширение файла для видеофайлов и GIF
        file_lower = file_path.lower()
        video_extensions = {'.mp4', '.webm', '.avi', '.mkv', '.mov', '.flv', '.m4v', '.3gp', '.wmv'}
        gif_extensions = {'.gif'}
        
        if any(file_lower.endswith(ext) for ext in gif_extensions):
            logger.info(f'Определён формат: GIF по расширению')
            return True
        
        if any(file_lower.endswith(ext) for ext in video_extensions):
            logger.info(f'Определён формат: видеофайл по расширению')
            return True
        
        with open(file_path, 'rb') as f:
            header = f.read(12)
        
        logger.info(f'Магические байты: {header[:4].hex()}')
        
        # Проверяем GIF
        if header[:3] == b'GIF':
            logger.info('Определён формат: GIF')
            return True
        
        # Проверяем WebP
        if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
            logger.info('Определён формат: WebP анимированный')
            return True
        
        # Проверяем MP4/MOV (видеофайлы)
        if b'ftyp' in header:
            logger.info('Определён формат: видеофайл (MP4/MOV) по магическим байтам')
            return True
        
        logger.info('Определён формат: статичное изображение (PNG/JPG/etc)')
        return False
    
    except Exception as e:
        logger.warning(f'Ошибка при определении типа файла: {e}')
        return False


def convert_to_webm(source_path, output_path='temp_sticker.webm'):
    """Конвертирует видео, GIF, WebP или другие форматы в WEBM VP9 для стикера (512x512, максимум 256KB)"""
    try:
        logger.info(f'Начинаем конвертацию файла {source_path} в WEBM VP9')
        
        # Конвертируем в WEBM с кодеком VP9 согласно Telegram рекомендациям
        # Максимум 256 KB для анимированного стикера
        cmd = [
            'ffmpeg',
            '-i', source_path,
            '-c:v', 'libvpx-vp9',
            '-pix_fmt', 'yuva420p',
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
            '-b:v', '200k',  # Битрейт для ограничения размера до 256KB
            '-maxrate', '200k',
            '-bufsize', '400k',
            '-crf', '40',  # Quality (0-63, меньше = лучше качество, но больше размер)
            '-deadline', 'realtime',  # Ускоренное кодирование
            '-cpu-used', '8',  # Максимальная скорость кодирования (0-8, 8 = самое быстрое)
            '-y',
            output_path
        ]
        
        logger.info(f'Запускаем ffmpeg команду: {" ".join(cmd)}')
        
        # Увеличиваем timeout до 5 минут из-за медленного VP9
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode != 0:
            logger.error(f'ffmpeg stderr: {result.stderr[:500]}')
            raise Exception(f'ffmpeg ошибка (код {result.returncode}): {result.stderr[:200]}')
        
        if not os.path.exists(output_path):
            raise Exception('ffmpeg не создал выходной файл')
        
        file_size = os.path.getsize(output_path)
        logger.info(f'WEBM VP9 успешно создан: {output_path} ({file_size} байт)')
        
        # Проверяем размер (максимум 256 KB для анимированного стикера)
        max_size = 256 * 1024
        if file_size > max_size:
            logger.warning(f'Файл слишком большой ({file_size} байт), оптимизируем дальше...')
            
            cmd_optimize = [
                'ffmpeg',
                '-i', source_path,
                '-c:v', 'libvpx-vp9',
                '-pix_fmt', 'yuva420p',
                '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2:color=0x00000000',
                '-b:v', '100k',  # Ещё меньше битрейт
                '-maxrate', '100k',
                '-bufsize', '200k',
                '-crf', '50',  # Ещё ниже качество
                '-deadline', 'realtime',
                '-cpu-used', '8',
                '-y',
                output_path
            ]
            
            logger.info(f'Повторная конвертация с большей компрессией...')
            result = subprocess.run(cmd_optimize, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f'Ошибка оптимизации: {result.stderr[:200]}')
            
            file_size = os.path.getsize(output_path)
            logger.info(f'Оптимизированный WEBM: {file_size} байт')
            
            if file_size > max_size:
                raise Exception(f'Файл слишком большой для стикера ({file_size} байт > 256KB). Попробуйте более короткое видео.')
        
        logger.info(f'WEBM VP9 готов: {output_path} ({file_size} байт)')
        return output_path
    
    except subprocess.TimeoutExpired:
        logger.error('Timeout при конвертации в WEBM (более 5 минут)')
        raise Exception('Конвертация заняла слишком много времени. Попробуйте более короткое видео.')
    except Exception as e:
        logger.error(f'Ошибка при конвертации в WEBM: {e}', exc_info=True)
        raise Exception(f'Не удалось конвертировать файл в WEBM VP9: {str(e)}')


async def add_sticker_to_set(event, client, stickerset_name, stickerset_title, channel_id=None):
    """Добавляет стикер (статичный или анимированный WEBM VP9) в стикерпак
    
    Args:
        event: событие NewMessage
        client: TelegramClient
        stickerset_name: имя стикерпака
        stickerset_title: название стикерпака
        channel_id: ID канала для отправки 'от канала' (если None, отправляется от юзера)
    """
    try:
        if not event.reply_to_msg_id:
            error_msg = await event.reply('Пожалуйста, ответьте на сообщение с изображением/стикером!')
            asyncio.create_task(delete_message_after(error_msg, 5))
            return
        
        replied_msg = await client.get_messages(event.chat_id, ids=event.reply_to_msg_id)
        
        if not replied_msg.media:
            error_msg = await event.reply('В сообщении нет изображения или стикера!')
            asyncio.create_task(delete_message_after(error_msg, 5))
            return
        
        file_path = await client.download_media(replied_msg.media)
        logger.info(f'Скачан файл: {file_path}')
        
        try:
            is_animated = is_animated_sticker(file_path)
            
            if is_animated:
                logger.info('Обнаружен анимированный файл, конвертируем в WEBM VP9')
                
                webm_path = 'temp_sticker.webm'
                converted_path = convert_to_webm(file_path, webm_path)
                
                input_file = await client.upload_file(webm_path)
                logger.info(f'Загруженный WEBM VP9: {input_file}')
                
                # Для WEBM VP9 стикера используем видео атрибут
                media = InputMediaUploadedDocument(
                    file=input_file,
                    mime_type='video/webm',
                    attributes=[
                        DocumentAttributeVideo(
                            duration=0,
                            w=512,
                            h=512,
                            supports_streaming=True
                        )
                    ]
                )
                
                result = await client(
                    UploadMediaRequest(
                        peer=event.chat_id,
                        media=media
                    )
                )
                logger.info(f'Результат UploadMedia для WEBM: {type(result)}')
                
                sticker_doc = result.document if hasattr(result, 'document') else None
                
                if not sticker_doc:
                    raise Exception(f'Не удалось получить документ из UploadMedia: {result}')
                
                logger.info(f'Готовый документ WEBM: id={sticker_doc.id}, access_hash={sticker_doc.access_hash}')
                
                input_sticker_doc = InputDocument(
                    id=sticker_doc.id,
                    access_hash=sticker_doc.access_hash,
                    file_reference=sticker_doc.file_reference
                )
                
                try:
                    await client(
                        AddStickerToSetRequest(
                            stickerset=InputStickerSetShortName(short_name=stickerset_name),
                            sticker=InputStickerSetItem(
                                document=input_sticker_doc,
                                emoji='😀'
                            )
                        )
                    )
                    logger.info(f'WEBM стикер добавлен в {stickerset_name}')
                    
                    try:
                        stickerset = await client(
                            GetStickerSetRequest(
                                stickerset=InputStickerSetShortName(short_name=stickerset_name),
                                hash=0
                            )
                        )
                        
                        if stickerset.documents:
                            sticker_from_pack = stickerset.documents[-1]
                            await client.send_message(
                                entity=event.chat_id,
                                file=sticker_from_pack,
                                reply_to=event.reply_to_msg_id
                            )
                            logger.info(f'✅ WEBM стикер отправлен')
                    except Exception as send_err:
                        logger.warning(f'Не удалось отправить стикер из пака: {send_err}')
                
                except Exception as e:
                    error_str = str(e)
                    logger.error(f'Ошибка при добавлении WEBM стикера: {error_str}')
                    
                    if 'STICKERSET_NOT_FOUND' in error_str:
                        try:
                            input_file = await client.upload_file(webm_path)
                            
                            media = InputMediaUploadedDocument(
                                file=input_file,
                                mime_type='video/webm',
                                attributes=[
                                    DocumentAttributeVideo(
                                        duration=0,
                                        w=512,
                                        h=512,
                                        supports_streaming=True
                                    )
                                ]
                            )
                            
                            sticker_set = await client(
                                CreateStickerSetRequest(
                                    user_id='me',
                                    title=stickerset_title,
                                    short_name=stickerset_name,
                                    stickers=[
                                        InputStickerSetItem(
                                            document=media,
                                            emoji='😀'
                                        )
                                    ]
                                )
                            )
                            logger.info(f'Создан новый WEBM стикерпак: {stickerset_name}')
                            
                            try:
                                stickerset = await client(
                                    GetStickerSetRequest(
                                        stickerset=InputStickerSetShortName(short_name=stickerset_name),
                                        hash=0
                                    )
                                )
                                
                                if stickerset.documents:
                                    sticker_from_pack = stickerset.documents[0]
                                    await client.send_message(
                                        entity=event.chat_id,
                                        file=sticker_from_pack,
                                        reply_to=event.reply_to_msg_id
                                    )
                                    logger.info(f'✅ WEBM стикер отправлен из нового пака')
                            except Exception as send_err:
                                logger.warning(f'Не удалось отправить стикер: {send_err}')
                        
                        except Exception as create_err:
                            logger.error(f'Ошибка создания пака: {create_err}', exc_info=True)
                            error_msg = await event.reply(f'Ошибка: {str(create_err)}')
                            asyncio.create_task(delete_message_after(error_msg, 5))
                            raise
                    else:
                        raise
            
            else:
                logger.info('Обнаружено статичное изображение, конвертируем в WEBM')
                
                webm_path = 'temp_sticker.webm'
                converted_path = convert_to_webm(file_path, webm_path)
                
                input_file = await client.upload_file(webm_path)
                logger.info(f'Загруженный WEBM: {input_file}')
                
                media = InputMediaUploadedDocument(
                    file=input_file,
                    mime_type='video/webm',
                    attributes=[
                        DocumentAttributeVideo(
                            duration=0,
                            w=512,
                            h=512,
                            supports_streaming=True
                        )
                    ]
                )
                
                result = await client(
                    UploadMediaRequest(
                        peer=event.chat_id,
                        media=media
                    )
                )
                logger.info(f'Результат UploadMedia: {type(result)}')
                
                sticker_doc = result.document if hasattr(result, 'document') else None
                
                if not sticker_doc:
                    raise Exception(f'Не удалось получить документ из UploadMedia: {result}')
                
                logger.info(f'Готовый документ: id={sticker_doc.id}, access_hash={sticker_doc.access_hash}')
                
                input_sticker_doc = InputDocument(
                    id=sticker_doc.id,
                    access_hash=sticker_doc.access_hash,
                    file_reference=sticker_doc.file_reference
                )
                
                try:
                    await client(
                        AddStickerToSetRequest(
                            stickerset=InputStickerSetShortName(short_name=stickerset_name),
                            sticker=InputStickerSetItem(
                                document=input_sticker_doc,
                                emoji='😀'
                            )
                        )
                    )
                    logger.info(f'Стикер добавлен в {stickerset_name}')
                    
                    try:
                        stickerset = await client(
                            GetStickerSetRequest(
                                stickerset=InputStickerSetShortName(short_name=stickerset_name),
                                hash=0
                            )
                        )
                        
                        if stickerset.documents:
                            sticker_from_pack = stickerset.documents[-1]
                            await client.send_message(
                                entity=event.chat_id,
                                file=sticker_from_pack,
                                reply_to=event.reply_to_msg_id
                            )
                            logger.info(f'✅ Стикер отправлен')
                    except Exception as send_err:
                        logger.warning(f'Не удалось отправить стикер из пака: {send_err}')
                
                except Exception as e:
                    error_str = str(e)
                    logger.error(f'Ошибка при добавлении стикера: {error_str}')
                    
                    if 'STICKERSET_NOT_FOUND' in error_str:
                        try:
                            input_file = await client.upload_file(webm_path)
                            
                            media = InputMediaUploadedDocument(
                                file=input_file,
                                mime_type='video/webm',
                                attributes=[
                                    DocumentAttributeVideo(
                                        duration=0,
                                        w=512,
                                        h=512,
                                        supports_streaming=True
                                    )
                                ]
                            )
                            
                            sticker_set = await client(
                                CreateStickerSetRequest(
                                    user_id='me',
                                    title=stickerset_title,
                                    short_name=stickerset_name,
                                    stickers=[
                                        InputStickerSetItem(
                                            document=media,
                                            emoji='😀'
                                        )
                                    ]
                                )
                            )
                            logger.info(f'Создан новый стикерпак: {stickerset_name}')
                            
                            try:
                                stickerset = await client(
                                    GetStickerSetRequest(
                                        stickerset=InputStickerSetShortName(short_name=stickerset_name),
                                        hash=0
                                    )
                                )
                                
                                if stickerset.documents:
                                    sticker_from_pack = stickerset.documents[0]
                                    await client.send_message(
                                        entity=event.chat_id,
                                        file=sticker_from_pack,
                                        reply_to=event.reply_to_msg_id
                                    )
                                    logger.info(f'✅ Стикер отправлен из нового пака')
                            except Exception as send_err:
                                logger.warning(f'Не удалось отправить стикер: {send_err}')
                        
                        except Exception as create_err:
                            logger.error(f'Ошибка создания пака: {create_err}', exc_info=True)
                            error_msg = await event.reply(f'Ошибка: {str(create_err)}')
                            asyncio.create_task(delete_message_after(error_msg, 5))
                            raise
                    else:
                        raise
        
        finally:
            for temp_file in [file_path, 'temp_sticker.webm']:
                if temp_file:
                    try:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                            logger.info(f'🗑️ Удалён файл: {temp_file}')
                    except Exception as file_err:
                        logger.warning(f'Не удалось удалить {temp_file}: {file_err}')
    
    except Exception as e:
        logger.error(f'Ошибка при добавлении стикера: {e}', exc_info=True)
        cleanup_temp_files()
        error_msg = await event.reply(f'Ошибка: {str(e)}')
        asyncio.create_task(delete_message_after(error_msg, 5))
