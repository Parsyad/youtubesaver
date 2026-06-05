import subprocess
import os
import time

def upload_to_mega(file_path, mega_email, mega_password):
    """
    Upload a file to MEGA using mega-cli command line tool
    """
    try:
        # Create a temporary folder for uploaded files
        mega_folder = "/YouTubeDownloads"
        
        # Login and upload using mega-cli
        cmd = f'mega-login {mega_email} {mega_password} && mega-mkdir {mega_folder} 2>/dev/null || true && mega-put "{file_path}" {mega_folder}/ && mega-export -a "{mega_folder}/$(basename {file_path})"'
        
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        
        # Extract the public link from output
        output = result.stdout
        # Look for a line with the export link (mega.nz/#F! or mega.nz/file/)
        for line in output.split('\n'):
            if 'mega.nz/' in line:
                return line.strip()
        
        # If no link found, login again and try export
        export_cmd = f'mega-login {mega_email} {mega_password} && mega-export -a "{mega_folder}/$(basename {file_path})"'
        export_result = subprocess.run(export_cmd, shell=True, capture_output=True, text=True, timeout=60)
        
        for line in export_result.stdout.split('\n'):
            if 'mega.nz/' in line:
                return line.strip()
                
        return None
        
    except Exception as e:
        print(f"Upload error: {e}")
        return None

def cleanup_expired_files():
    """Placeholder function - mega-cli doesn't auto-cleanup, but you can manually manage files"""
    pass

def cleanup_local_files(file_path):
    """Remove local file after upload"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Cleanup error: {e}")
