import os
import logging
from datetime import datetime, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from apscheduler.schedulers.background import BackgroundScheduler

from config import TELEGRAM_BOT_TOKEN, ADMIN_USER_ID
from database import register_user, update_user_activity, increment_download_count, log_download, get_stats, init_db
from youtube_downloader import is_valid_youtube_url, get_video_info, download_video
from mega_handler import upload_to_mega, cleanup_expired_files, cleanup_local_files

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize database tables
init_db()

# Initialize scheduler for background tasks
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: cleanup_expired_files(), 'interval', hours=1)
scheduler.add_job(lambda: cleanup_local_files(None), 'interval', minutes=30)
scheduler.start()

# Dictionary for user states
user_states = {}

# /start command handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    
    # Register user or update their info
    is_new_user = register_user(
        user.id, 
        user.username, 
        user.first_name
    )
    
    welcome_message = (
        f"Hello, {user.first_name}! 👋\n\n"
        "This bot helps you download videos from YouTube and get a temporary download link.\n\n"
        "Just send me a YouTube video link, and I'll help you download it in your preferred quality.\n\n"
        "Available commands:\n"
        "/start - Start working with the bot\n"
        "/help - Show help information"
    )
    
    await update.message.reply_text(welcome_message)

# /help command handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "How to use this bot:\n\n"
        "1. Send me a YouTube video link\n"
        "2. Choose the video quality (480p, 720p, 1080p, or MP3)\n"
        "3. Wait for the download to complete and get a temporary download link\n\n"
        "Note: The download link is valid for 1 hour.\n\n"
        "Available commands:\n"
        "/start - Start working with the bot\n"
        "/help - Show this help message\n"
        "/stats - Statistics (admin only)"
    )
    
    await update.message.reply_text(help_text)

# /stats command handler (admin only)
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    
    # Check if user is admin
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("You don't have access to this command.")
        return
    
    # Get statistics
    stats = get_stats()
    
    stats_text = (
        "📊 Bot Statistics:\n\n"
        f"👥 Total users: {stats['total_users']}\n"
        f"📥 Total downloads: {stats['total_downloads']}\n"
        f"📥 Downloads today: {stats['downloads_today']}\n"
        f"👤 Active users today: {stats['active_users_today']}\n\n"
        "🏆 Top users by downloads:\n"
    )
    
    for i, user in enumerate(stats['top_users']):
        username = user.get('username', 'Unknown')
        first_name = user.get('first_name', 'Unknown')
        downloads = user.get('total_downloads', 0)
        
        stats_text += f"{i+1}. {first_name} (@{username}): {downloads} downloads\n"
    
    await update.message.reply_text(stats_text)

# URL message handler
async def handle_youtube_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    url = update.message.text.strip()
    user_id = update.effective_user.id
    
    # Update user activity
    update_user_activity(user_id)
    
    # Check if URL is a valid YouTube link
    if not is_valid_youtube_url(url):
        await update.message.reply_text(
            "This doesn't look like a YouTube link. Please send a valid YouTube video URL."
        )
        return
    
    # Send processing message
    processing_message = await update.message.reply_text(
        "Getting video information... ⏳"
    )
    
    # Get video information
    video_info = get_video_info(url)
    
    if not video_info:
        await processing_message.edit_text(
            "Failed to get video information. Please check the link and try again."
        )
        return
    
    # Save URL in user context
if context.user_data is None:
    context.user_data.clear()
    
    context.user_data['youtube_url'] = url
    context.user_data['video_title'] = video_info['title']
    
    # Create keyboard with resolution options
    keyboard = []
    
    # Add available video resolutions
    for res in sorted(video_info['resolutions']):
        keyboard.append([InlineKeyboardButton(f"📹 {res}p", callback_data=f"res_{res}")])
    
    # Add audio option if available
    if video_info['has_audio']:
        keyboard.append([InlineKeyboardButton("🎵 MP3 (audio only)", callback_data="res_audio")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Format video duration
    minutes, seconds = divmod(video_info['length'], 60)
    hours, minutes = divmod(minutes, 60)
    
    if hours > 0:
        duration = f"{hours}:{minutes:02d}:{seconds:02d}"
    else:
        duration = f"{minutes:02d}:{seconds:02d}"
    
    # Send message with video info and keyboard
    await processing_message.edit_text(
        f"📹 <b>{video_info['title']}</b>\n\n"
        f"👤 Author: {video_info['author']}\n"
        f"⏱ Duration: {duration}\n\n"
        "Choose download quality:",
        reply_markup=reply_markup,
        parse_mode='HTML'
    )

# Quality selection handler
async def handle_quality_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    # Get selected quality
    quality = query.data.split('_')[1]
    
    # Get YouTube URL from user context
    youtube_url = context.user_data.get('youtube_url')
    
    if not youtube_url:
        await query.edit_message_text(
            "An error occurred. Please send the YouTube link again."
        )
        return
    
    # Send download start message
    if quality == 'audio':
        await query.edit_message_text(
            "Downloading audio... ⏳\nThis may take some time depending on the file size."
        )
    else:
        await query.edit_message_text(
            f"Downloading video in {quality}p quality... ⏳\nThis may take some time depending on the file size."
        )
    
    # Download video
    download_result = download_video(youtube_url, quality)
    
    if not download_result:
        await query.edit_message_text(
            "An error occurred while downloading. Please try again or choose a different quality."
        )
        return
    
    # Send upload to MEGA message
    await query.edit_message_text(
        f"Video downloaded successfully! 🎉\n"
        f"File size: {download_result['file_size']:.2f} MB\n\n"
        f"Uploading to MEGA... ⏳"
    )
    
    # Upload file to MEGA
    mega_result = upload_to_mega(download_result['file_path'], download_result['file_name'])
    
    if not mega_result:
        await query.edit_message_text(
            "An error occurred while uploading to MEGA. Please try again."
        )
        return
    
    # Format expiration time
    expiration_time = mega_result['expiration_time']
    expiration_formatted = expiration_time.strftime("%d.%m.%Y %H:%M:%S")
    
    # Increment user download count
    increment_download_count(update.effective_user.id)
    
    # Log download
    log_download(
        update.effective_user.id,
        youtube_url,
        quality,
        download_result['file_size'],
        download_result['format']
    )
    
    # Send message with download link
    quality_text = 'MP3 (audio)' if quality == 'audio' else f'{quality}p'
    await query.edit_message_text(
        f"✅ Download complete!\n\n"
        f"📹 <b>{context.user_data.get('video_title')}</b>\n"
        f"📊 Quality: {quality_text}\n"
        f"📦 Size: {download_result['file_size']:.2f} MB\n\n"
        f"🔗 <a href='{mega_result['link']}'>Download file</a>\n\n"
        f"⚠️ Link expires on: {expiration_formatted} (1 hour)",
        parse_mode='HTML',
        disable_web_page_preview=True
    )

# Main function
def main() -> None:
    # Create application and add handlers
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # YouTube URL handler
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_youtube_url
    ))
    
    # Quality selection handler
    application.add_handler(CallbackQueryHandler(handle_quality_selection, pattern="^res_"))
    
    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
