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
        'extract_flat': 'in_playlist',
        'geo_bypass': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if info is None:
                return None
            
            resolutions = set()
            formats = info.get('formats', [])
            for f in formats:
                height = f.get('height')
                if height and height <= 1080:
                    resolutions.add(height)
            
            if not resolutions:
                resolutions = [360, 720]
            
            return {
                'title': info.get('title', 'Unknown'),
                'author': info.get('uploader', 'Unknown'),
                'length': info.get('duration', 0),
                'resolutions': sorted(resolutions),
                'has_audio': True
            }
    except Exception as e:
        print(f"Error getting video info: {e}")
        return None

def download_video(url, quality):
    """Download video using yt-dlp"""
    
    os.makedirs('downloads', exist_ok=True)
    
    if quality == 'audio':
        format_spec = 'bestaudio/best'
        output_template = 'downloads/%(title)s.%(ext)s'
        ydl_opts = {
            'format': format_spec,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
    else:
        format_spec = f'bestvideo[height<={quality}]+bestaudio/best'
        output_template = f'downloads/%(title)s_{quality}p.%(ext)s'
        ydl_opts = {
            'format': format_spec,
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'merge_output_format': 'mp4',
        }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            if quality == 'audio':
                filename = ydl.prepare_filename(info).replace('.webm', '.mp3').replace('.m4a', '.mp3')
                if not os.path.exists(filename):
                    base = ydl.prepare_filename(info)
                    for ext in ['.mp3', '.m4a', '.webm']:
                        test_file = base + ext
                        if os.path.exists(test_file):
                            filename = test_file
                            break
            else:
                filename = ydl.prepare_filename(info)
                if not os.path.exists(filename):
                    test_file = filename + '.mp4'
                    if os.path.exists(test_file):
                        filename = test_file
            
            if not os.path.exists(filename):
                return None
                
            file_size = os.path.getsize(filename) / (1024 * 1024)
            
            return {
                'file_path': filename,
                'file_name': os.path.basename(filename),
                'file_size': file_size,
                'format': quality
            }
    except Exception as e:
        print(f"Download error: {e}")
        return None
