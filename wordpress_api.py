import os
import requests
import base64
from datetime import datetime
import random
import time

# Configuration
WP_API_URL = os.getenv('WP_API_URL') # e.g., https://your-site.com/wp-json/wp/v2/media
WP_USER = os.getenv('WP_USER')
WP_PASS = os.getenv('WP_PASS')

def _get_auth_header():
    if not all([WP_USER, WP_PASS]):
        return None
    credentials = f"{WP_USER}:{WP_PASS}"
    token = base64.b64encode(credentials.encode()).decode('utf-8')
    return {'Authorization': f'Basic {token}'}

def upload_media(file_storage):
    """
    Uploads a file to the WordPress Media Library or returns a mock response
    if credentials are not set.
    """
    if not all([WP_API_URL, WP_USER, WP_PASS]):
        print("⚠️  Warning: WordPress credentials missing. Using MOCK MODE.")
        return _mock_upload_response(file_storage)

    filename = file_storage.filename
    mime_type = file_storage.mimetype
    file_content = file_storage.read()

    headers = {
        'Content-Disposition': f'attachment; filename={filename}',
        'Content-Type': mime_type,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    headers.update(_get_auth_header())

    try:
        response = requests.post(
            WP_API_URL,
            headers=headers,
            data=file_content,
            timeout=90 
        )
        
        if not response.ok:
            print(f"❌ WordPress Error {response.status_code}: {response.text[:200]}")

        response.raise_for_status()
        data = response.json()
        
        sizes = data.get('media_details', {}).get('sizes', {})
        url_full = data.get('source_url')
        url_thumbnail = sizes.get('thumbnail', {}).get('source_url', url_full)
        url_medium = sizes.get('medium', {}).get('source_url', url_full)

        time.sleep(0.3) # Reduced throttle

        return {
            'wp_media_id': data.get('id'),
            'title': data.get('title', {}).get('raw', filename),
            'file_name': filename,
            'mime_type': mime_type,
            'url_full': url_full,
            'url_thumbnail': url_thumbnail,
            'url_medium': url_medium
        }

    except requests.exceptions.RequestException as e:
        print(f"❌ Error uploading to WordPress: {e}")
        return None

def delete_media(wp_id):
    """
    Deletes a media item from WordPress.
    Args:
        wp_id (int): The WordPress Media ID.
    Returns:
        bool: True if successful, False otherwise.
    """
    if not all([WP_API_URL, WP_USER, WP_PASS]):
        print(f"ℹ️  Mock Mode: Simulated deletion of WP ID {wp_id}")
        return True

    url = f"{WP_API_URL}/{wp_id}?force=true" # force=true skips trash
    headers = _get_auth_header()
    headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    try:
        response = requests.delete(url, headers=headers, timeout=30)
        if response.ok:
            return True
        else:
            print(f"❌ Failed to delete WP ID {wp_id}: {response.status_code} - {response.text[:100]}")
            return False
    except Exception as e:
        print(f"❌ Error deleting from WordPress: {e}")
        return False

def _mock_upload_response(file_storage):
    """Generates a fake successful response for testing UI/DB logic."""
    mock_id = random.randint(1000, 9999)
    is_image = file_storage.mimetype.startswith('image')
    base_placeholder = "https://placehold.co"
    
    if is_image:
        url_full = f"{base_placeholder}/600x400/1e293b/4ade80?text={file_storage.filename}"
        url_thumb = f"{base_placeholder}/150x150/1e293b/4ade80?text=Thumb"
        url_med = f"{base_placeholder}/300x200/1e293b/4ade80?text=Medium"
    else:
        url_full = f"{base_placeholder}/600x400/1e293b/fb7185?text=File"
        url_thumb = f"{base_placeholder}/150x150/1e293b/fb7185?text=File"
        url_med = f"{base_placeholder}/300x200/1e293b/fb7185?text=File"

    return {
        'wp_media_id': mock_id,
        'title': f"Mock: {file_storage.filename}",
        'file_name': file_storage.filename,
        'mime_type': file_storage.mimetype,
        'url_full': url_full,
        'url_thumbnail': url_thumb,
        'url_medium': url_med
    }