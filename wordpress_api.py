from __future__ import annotations

import base64
import logging
import random
from typing import Any

import requests

from config import get_config

_config = get_config()
logger = logging.getLogger(__name__)

def _get_auth_header() -> dict[str, str] | None:
    if not _config.wp_user or not _config.wp_pass:
        return None
    credentials = f"{_config.wp_user}:{_config.wp_pass}"
    token = base64.b64encode(credentials.encode()).decode('utf-8')
    return {'Authorization': f'Basic {token}'}


def upload_media(file_storage: Any) -> dict[str, Any] | None:
    """
    Uploads a file to the WordPress Media Library or returns a mock response
    if credentials are not set.
    """
    if not _config.wp_configured or not _config.wp_api_url:
        logger.warning("WordPress credentials missing. Using MOCK MODE.")
        return _mock_upload_response(file_storage)

    wp_url = _config.wp_api_url
    filename = file_storage.filename
    mime_type = file_storage.mimetype
    file_content = file_storage.read()

    headers = {
        'Content-Disposition': f'attachment; filename={filename}',
        'Content-Type': mime_type,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    headers.update(_get_auth_header() or {})

    try:
        response = requests.post(
            wp_url,
            headers=headers,
            data=file_content,
            timeout=90 
        )
        
        if not response.ok:
            logger.error("WordPress upload error %s: %s", response.status_code, response.text[:200])

        response.raise_for_status()
        data = response.json()
        
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
        logger.exception("Error uploading to WordPress: %s", e)
        return None

def delete_media(wp_id: int) -> bool:
    """Deletes a media item from WordPress. Returns True if successful."""
    if not _config.wp_configured or not _config.wp_api_url:
        logger.info("Mock mode: simulated deletion of WP ID %s", wp_id)
        return True

    url = f"{_config.wp_api_url}/{wp_id}?force=true"
    headers = _get_auth_header() or {}
    headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    try:
        response = requests.delete(url, headers=headers, timeout=30)
        if response.ok:
            return True
        else:
            logger.error("Failed to delete WP ID %s: %s - %s", wp_id, response.status_code, response.text[:100])
            return False
    except Exception as e:
        logger.exception("Error deleting from WordPress: %s", e)
        return False

def _mock_upload_response(file_storage: Any) -> dict[str, Any]:
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