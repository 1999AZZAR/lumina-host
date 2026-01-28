import os
import requests
import base64
from datetime import datetime
import random

# Configuration
WP_API_URL = os.getenv('WP_API_URL') # e.g., https://your-site.com/wp-json/wp/v2/media
WP_USER = os.getenv('WP_USER')
WP_PASS = os.getenv('WP_PASS')

def upload_media(file_storage):
    """
    Uploads a file to the WordPress Media Library or returns a mock response
    if credentials are not set.
    
    Args:
        file_storage (werkzeug.datastructures.FileStorage): The file upload object.
        
    Returns:
        dict: Normalized asset data for the local database or None on failure.
    """
    
    # --- Mock Mode (Fallback) ---
    if not all([WP_API_URL, WP_USER, WP_PASS]):
        print("⚠️  Warning: WordPress credentials missing. Using MOCK MODE.")
        return _mock_upload_response(file_storage)

    # --- Live Mode ---
    filename = file_storage.filename
    mime_type = file_storage.mimetype
    file_content = file_storage.read()

    headers = {
        'Content-Disposition': f'attachment; filename={filename}',
        'Content-Type': mime_type,
    }

    # Create Basic Auth header
    credentials = f"{WP_USER}:{WP_PASS}"
    token = base64.b64encode(credentials.encode()).decode('utf-8')
    headers['Authorization'] = f'Basic {token}'

    try:
        response = requests.post(
            WP_API_URL,
            headers=headers,
            data=file_content,
            timeout=30 # Prevent hanging indefinitely
        )
        
        response.raise_for_status()
        data = response.json()
        
        # Extract relevant fields based on WP API structure
        # Fallback to full URL if specific sizes aren't generated
        sizes = data.get('media_details', {}).get('sizes', {})
        
        url_full = data.get('source_url')
        url_thumbnail = sizes.get('thumbnail', {}).get('source_url', url_full)
        url_medium = sizes.get('medium', {}).get('source_url', url_full)

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

def _mock_upload_response(file_storage):
    """Generates a fake successful response for testing UI/DB logic."""
    # Use generic placeholder images
    mock_id = random.randint(1000, 9999)
    
    # Determine type for better placeholders if possible (simple logic)
    is_image = file_storage.mimetype.startswith('image')
    base_placeholder = "https://placehold.co"
    
    # Simple colorful placeholders
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
