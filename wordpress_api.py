from __future__ import annotations

import base64
import logging
import random
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import get_config
import database

_config = get_config()
logger = logging.getLogger(__name__)

# Retry transient connection errors (e.g. connection reset by peer).
WP_UPLOAD_RETRIES = 3
WP_UPLOAD_RETRY_BACKOFF = (1, 2, 3)  # seconds before each retry

WP_API_URL_KEY = 'wp_api_url'
WP_USER_KEY = 'wp_user'
WP_PASS_KEY = 'wp_pass'

# Global session with connection pooling
session = requests.Session()
# Configure retry strategy for low-level connection issues
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=retries)
session.mount('http://', adapter)
session.mount('https://', adapter)


def _get_wp_credentials() -> tuple[str | None, str | None, str | None]:
    """Return (wp_api_url, wp_user, wp_pass) from settings table first, else from env config."""
    try:
        url = database.get_setting(WP_API_URL_KEY)
        user = database.get_setting(WP_USER_KEY)
        pass_ = database.get_setting(WP_PASS_KEY)
        if url and user and pass_:
            return (url.strip(), user.strip(), pass_)
    except Exception as e:
        logger.debug("Settings lookup for WP credentials: %s", e)
    return (_config.wp_api_url, _config.wp_user, _config.wp_pass)


def _get_auth_header(wp_user: str | None = None, wp_pass: str | None = None) -> dict[str, str] | None:
    if not wp_user or not wp_pass:
        return None
    credentials = f"{wp_user}:{wp_pass}"
    token = base64.b64encode(credentials.encode()).decode('utf-8')
    return {'Authorization': f'Basic {token}'}


def upload_media(file_storage: Any) -> dict[str, Any] | None:
    """
    Uploads a file to the WordPress Media Library or returns a mock response
    if credentials are not set.
    """
    wp_url, wp_user, wp_pass = _get_wp_credentials()
    if not wp_url or not wp_user or not wp_pass:
        logger.warning("WordPress credentials missing. Using MOCK MODE.")
        return _mock_upload_response(file_storage)

    filename = file_storage.filename
    mime_type = file_storage.mimetype
    file_content = file_storage.read()

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': mime_type,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    headers.update(_get_auth_header(wp_user, wp_pass) or {})

    last_error: Exception | None = None
    for attempt in range(WP_UPLOAD_RETRIES):
        try:
            if attempt > 0:
                time.sleep(WP_UPLOAD_RETRY_BACKOFF[attempt - 1])
            response = session.post(
                wp_url,
                headers=headers,
                data=file_content,
                timeout=90,
            )
            
            # Retry on server errors
            if response.status_code >= 500:
                logger.warning(
                    "WordPress upload error %s (Attempt %s/%s): %s",
                    response.status_code,
                    attempt + 1,
                    WP_UPLOAD_RETRIES,
                    response.text[:200]
                )
                response.raise_for_status()

            if not response.ok:
                logger.error(
                    "WordPress upload error %s: %s",
                    response.status_code,
                    response.text[:200],
                )
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
                'url_medium': url_medium,
            }
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
            last_error = e
            # Only retry 5xx errors if it's an HTTPError
            is_5xx = isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code >= 500
            is_connection = isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))
            
            if (is_connection or is_5xx) and attempt < WP_UPLOAD_RETRIES - 1:
                logger.warning(
                    "WordPress upload attempt %s failed (%s), retrying: %s",
                    attempt + 1,
                    type(e).__name__,
                    e,
                )
            else:
                if attempt == WP_UPLOAD_RETRIES - 1:
                    logger.exception("Error uploading to WordPress after %s attempts: %s", WP_UPLOAD_RETRIES, e)
                else:
                    # If it's not a retryable error (e.g. 400), break immediately
                    logger.error("Error uploading to WordPress: %s", e)
                    return None
        except requests.exceptions.RequestException as e:
            logger.exception("Error uploading to WordPress: %s", e)
            return None

    if last_error:
        logger.exception("Error uploading to WordPress: %s", last_error)
    return None

WP_DELETE_RETRIES = 2
WP_DELETE_RETRY_BACKOFF = (1,)


def delete_media(wp_id: int) -> bool:
    """Deletes a media item from WordPress. Returns True if successful."""
    wp_url, wp_user, wp_pass = _get_wp_credentials()
    if not wp_url or not wp_user or not wp_pass:
        logger.info("Mock mode: simulated deletion of WP ID %s", wp_id)
        return True

    url = f"{wp_url}/{wp_id}?force=true"
    headers = _get_auth_header(wp_user, wp_pass) or {}
    headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    last_error: Exception | None = None
    for attempt in range(WP_DELETE_RETRIES):
        try:
            if attempt > 0:
                time.sleep(WP_DELETE_RETRY_BACKOFF[attempt - 1])
            response = session.delete(url, headers=headers, timeout=30)
            
            # Retry on server errors
            if response.status_code >= 500:
                logger.warning(
                    "WordPress delete error %s (Attempt %s/%s): %s",
                    response.status_code,
                    attempt + 1,
                    WP_DELETE_RETRIES,
                    response.text[:100]
                )
                response.raise_for_status()

            if response.ok:
                return True
            
            logger.error(
                "Failed to delete WP ID %s: %s - %s",
                wp_id,
                response.status_code,
                response.text[:100],
            )
            return False
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout, requests.exceptions.HTTPError) as e:
            last_error = e
            # Only retry 5xx errors if it's an HTTPError
            is_5xx = isinstance(e, requests.exceptions.HTTPError) and e.response is not None and e.response.status_code >= 500
            is_connection = isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))

            if (is_connection or is_5xx) and attempt < WP_DELETE_RETRIES - 1:
                logger.warning(
                    "WordPress delete attempt %s failed (%s), retrying: %s",
                    attempt + 1,
                    type(e).__name__,
                    e,
                )
            else:
                if attempt == WP_DELETE_RETRIES - 1:
                    logger.exception(
                        "Error deleting from WordPress after %s attempts: %s",
                        WP_DELETE_RETRIES,
                        e,
                    )
                return False
        except Exception as e:
            logger.exception("Error deleting from WordPress: %s", e)
            return False

    if last_error:
        logger.exception("Error deleting from WordPress: %s", last_error)
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