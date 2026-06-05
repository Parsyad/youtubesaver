import os
import logging
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from database import register_user, update_user_activity, increment_download_count, log_download, get_stats
from youtube_downloader import is_valid_youtube_url, get_video_info, download_video
from mega_handler import upload_to_mega, cleanup_expired_files, cleanup_local_files

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация планировщика для фоновых задач
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: cleanup_expired_files(), 'interval', hours=1)
scheduler.add_job(lambda: cleanup_local_files(None), 'interval', minutes=30)
scheduler.start()

# Словарь для хранения состояний пользователей
user_states = {}

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    
    # Регистрируем пользователя или обновляем информацию о нем
    is_new_user = register_user(
        user.id, 
        user.username, 
        user.first_name
    )
    
    welcome_message = (
        f"Привет, {user.first_name}! 👋\n\n"
        "Этот бот поможет скачать видео с YouTube и получить временную ссылку на него.\n\n"
        "Просто отправь мне ссылку на видео YouTube, и я помогу тебе скачать его в нужном качестве.\n\n"
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать справку"
    )
    
    await update.message.reply_text(welcome_message)

# Обработчик команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Как использовать этот бот:\n\n"
        "1. Отправь мне ссылку на видео YouTube\n"
        "2. Выбери качество видео (480p, 720p, 1080p или MP3)\n"
        "3. Дождись завершения загрузки и получи временную ссылку на скачивание\n\n"
        "Обрати внимание: ссылка действительна в течение 1 часа.\n\n"
        "Доступные команды:\n"
        "/start - Начать работу с ботом\n"
        "/help - Показать эту справку\n"
        "/stats - Статистика (только для администратора)"
    )
    
    await update.message.reply_text(help_text)

# Обработчик команды /stats (только для администратора)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    # Проверяем, является ли пользователь администратором
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    
    # Получаем статистику
    stats = get_stats()
    
    stats_text = (
        "📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📥 Всего загрузок: {stats['total_downloads']}\n"
        f"📥 Загрузок сегодня: {stats['downloads_today']}\n"
        f"👤 Активных пользователей сегодня: {stats['active_users_today']}\n\n"
        "🏆 Топ пользователей по загрузкам:\n"
    )
    
    for i, user in enumerate(stats['top_users']):
        username = user.get('username', 'Неизвестно')
        first_name = user.get('first_name', 'Неизвестно')
        downloads = user.get('total_downloads', 0)
        
        stats_text += f"{i+1}. {first_name} (@{username}): {downloads} загрузок\n"
    
    await update.message.reply_text(stats_text)

# Обработчик сообщений с URL
async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Обновляем активность пользователя
    update_user_activity(user_id)
    
    # Проверяем, является ли URL действительной ссылкой YouTube
    if not is_valid_youtube_url(url):
        await update.message.reply_text(
            "Это не похоже на ссылку YouTube. Пожалуйста, отправь корректную ссылку на видео YouTube."
        )
        return
    
    # Отправляем сообщение о начале обработки
    processing_message = await update.message.reply_text(
        "Получаю информацию о видео... ⏳"
    )
    
    # Получаем информацию о видео
    video_info = get_video_info(url)
    
    if not video_info:
        await processing_message.edit_text(
            "Не удалось получить информацию о видео. Пожалуйста, проверьте ссылку и попробуйте снова."
        )
        return
    
    # Сохраняем URL в контексте пользователя
    if not context.user_data:
        context.user_data = {}
    
    context.user_data['youtube_url'] = url
    context.user_data['video_title'] = video_info['title']
    
    # Создаем клавиатуру с вариантами разрешения
    keyboard = []
    
    # Добавляем доступные разрешения видео
    for res in sorted(video_info['resolutions']):
        keyboard.append([InlineKeyboardButton(f"📹 {res}p", callback_data=f"res_{res}")])
    
    # Добавляем опцию для аудио, если доступно
    if video_info['has_audio']:
        keyboard.append([InlineKeyboardButton("🎵 MP3 (только аудио)", callback_data="res_audio")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Форматируем длительность видео
    minutes, seconds = divmod(video_info['length'], 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        duration = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        duration = f"{minutes:02d}:{seconds:02d}"
    
    # Отправляем сообщение с информацией о видео и клавиатурой
    await processing_message.edit_text(
        f"📹 <b>{video_info['title']}</b>\n\n"
        f"👤 Автор: {video_info['author']}\n"
        f"⏱ Длительность: {duration}\n\n"
        "Выберите качество загрузки:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# Обработчик выбора качества видео
async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    # Получаем выбранное качество
    quality = query.data.split('_')[1]
    
    # Получаем ссылку YouTube из контекста пользователя
    youtube_url = context.user_data.get('youtube_url')
    
    if not youtube_url:
        await query.edit_message_text(
            "Произошла ошибка. Пожалуйста, отправьте ссылку на видео заново."
        )
        return
    
    # Отправляем сообщение о начале загрузки
    await query.edit_message_text(
        f"Загружаю {'аудио' if quality == 'audio' else f'видео в качестве {quality}p'}... ⏳\n"
        "Это может занять некоторое время в зависимости от размера видео."
    )
    
    # Загружаем видео
    download_result = download_video(youtube_url, quality)
    
    if not download_result:
        await query.edit_message_text(
            "Произошла ошибка при загрузке видео. Пожалуйста, попробуйте еще раз или выберите другое качество."
        )
        return
    
    # Отправляем сообщение о начале загрузки на MEGA
    await query.edit_message_text(
        f"Видео успешно загружено! 🎉\n"
        f"Размер файла: {download_result['file_size']:.2f} МБ\n\n"
        f"Загружаю на MEGA... ⏳"
    )
    
    # Загружаем файл на MEGA
    mega_result = upload_to_mega(download_result['file_path'], download_result['file_name'])
    
    if not mega_result:
        await query.edit_message_text(
            "Произошла ошибка при загрузке файла на MEGA. Пожалуйста, попробуйте еще раз."
        )
        return
    
    # Форматируем время истечения
    expiration_time = mega_result['expiration_time']
    expiration_formatted = expiration_time.strftime("%d.%m.%Y %H:%M:%S")
    
    # Увеличиваем счетчик загрузок пользователя
    increment_download_count(update.effective_user.id)
    
    # Логируем загрузку
    log_download(
        update.effective_user.id,
        youtube_url,
        quality,
        download_result['file_size'],
        download_result['format']
    )
    
    # Отправляем сообщение с ссылкой
    await query.edit_message_text(
        f"✅ Загрузка завершена!\n\n"
        f"📹 <b>{context.user_data.get('video_title')}</b>\n"
        f"📊 Качество: {'MP3 (аудио)' if quality == 'audio' else f'{quality}p'}\n"
        f"📦 Размер: {download_result['file_size']:.2f} МБ\n\n"
        f"🔗 <a href='{mega_result['link']}'>Скачать файл</a>\n\n"
        f"⚠️ Ссылка действительна до: {expiration_formatted} (1 час)",
        parse_mode='HTML',
        disable_web_page_preview=True
    )

# Основная функция
def main() -> None:
    # Создаем приложение и добавляем обработчики
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Обработчик URL YouTube
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.Entity("url"),
        handle_youtube_url
    ))
    
    # Обработчик выбора качества
    application.add_handler(CallbackQueryHandler(handle_quality_selection, pattern="^res_"))
    
    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    
    def main():
    # Initialize database tables
    from database import init_db
    init_db() main() 
