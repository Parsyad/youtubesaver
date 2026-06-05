import yt_dlp
import os
import re

def is_valid_youtube_url(url):
    """Check if URL is a valid YouTube link"""
    youtube_regex = (
        r'(https?://)?(www\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    return re.match(youtube_regex, url) is not None

def get_video_info(url):
    """Extract video information using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract available resolutions
            resolutions = set()
            formats = info.get('formats', [])
            for f in formats:
                height = f.get('height')
                if height and height <= 1080:  # Limit to 1080p max
                    resolutions.add(height)
            
            # Check if audio-only formats available
            has_audio = any(f.get('acodec') != 'none' for f in formats)
            
            return {
                'title': info.get('title', 'Unknown'),
                'author': info.get('uploader', 'Unknown'),
                'length': info.get('duration', 0),
                'resolutions': sorted(resolutions),
                'has_audio': has_audio
            }
    except Exception as e:
        print(f"Error getting video info: {e}")
        return None

def download_video(url, quality):
    """Download video using yt-dlp"""
    
    # Map quality selection to format code
    if quality == 'audio':
        format_spec = 'bestaudio/best'
        output_template = 'downloads/%(title)s.%(ext)s'
    else:
        format_spec = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
        output_template = 'downloads/%(title)s_%(height)sp.%(ext)s'
    
    # Ensure downloads directory exists
    os.makedirs('downloads', exist_ok=True)
    
    ydl_opts = {
        'format': format_spec,
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4' if quality != 'audio' else None,
    }
    
    # For audio downloads, add post-processor
    if quality == 'audio':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Get the downloaded file path
            if quality == 'audio':
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
                if not os.path.exists(filename):
                    filename = ydl.prepare_filename(info) + '.mp3'
            else:
                filename = ydl.prepare_filename(info)
            
            file_size = os.path.getsize(filename) / (1024 * 1024)  # Size in MB
            
            return {
                'file_path': filename,
                'file_name': os.path.basename(filename),
                'file_size': file_size,
                'format': quality
            }
    except Exception as e:
        print(f"Download error: {e}")
        return None
