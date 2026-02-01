"""Request and input validation for Lumina Host."""

import re
import unicodedata
import time
import random
import string
from datetime import datetime
from typing import Any

# Max length for search query (chars)
SEARCH_QUERY_MAX_LEN = 200

USERNAME_MAX_LEN = 64
EMAIL_MAX_LEN = 256
USERNAME_RE = re.compile(r'^[a-zA-Z0-9_]+$')
PASSWORD_MIN_LEN = 8
MAX_ID = 2**31 - 1

# MIME types allowed per extension (subset; client can lie so we only sanity-check)
# Include common variants (e.g. image/jpg) and allow octet-stream when extension is valid (mobile often sends that)
EXTENSION_MIME: dict[str, set[str]] = {
    'png': {'image/png', 'image/x-png'},
    'jpg': {'image/jpeg', 'image/jpg', 'image/pjpeg', 'image/x-citrix-jpeg'},
    'jpeg': {'image/jpeg', 'image/jpg', 'image/pjpeg', 'image/x-citrix-jpeg'},
    'gif': {'image/gif'},
    'webp': {'image/webp', 'image/x-webp'},
    'bmp': {'image/bmp', 'image/x-bmp', 'image/x-ms-bmp'},
    'tiff': {'image/tiff', 'image/x-tiff'},
    'ico': {'image/x-icon', 'image/vnd.microsoft.icon', 'image/ico'},
    'svg': {'image/svg+xml'},
}
# When extension is allowed but MIME is generic/empty, still accept (extension is primary check)
GENERIC_MIMETYPES = frozenset({'application/octet-stream', 'application/unknown', ''})


def normalize_filename(filename: str | None) -> str:
    """
    Generate a standardized filename using the scheme: MMDDYY_HHMM_WXYZ.ext
    - MMDDYY: Current date (Month, Day, Year)
    - HHMM: Current time (Hour, Minute)
    - WXYZ: 4-character random alphanumeric string
    - ext: Original file extension (normalized to lowercase)
    """
    # Get extension from original filename
    if filename and '.' in filename:
        ext = '.' + filename.rsplit('.', 1)[-1].lower()
    else:
        ext = '.jpg' # Fallback for safety, though validators.py usually prevents this

    now = datetime.now()
    date_part = now.strftime("%m%d%y") # MMDDYY
    time_part = now.strftime("%H%M")   # HHMM
    random_part = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))

    return f"{date_part}_{time_part}_{random_part}{ext}"


def validate_username(s: str | None) -> str:
    """Validate username: strip, length cap, alphanumeric and underscore only. Raises ValueError if invalid."""
    if s is None:
        raise ValueError('Username is required.')
    s = s.strip()[:USERNAME_MAX_LEN]
    if not s:
        raise ValueError('Username is required.')
    if not USERNAME_RE.match(s):
        raise ValueError('Username may only contain letters, numbers, and underscores.')
    return s


def validate_album_name(s: str | None) -> str:
    """Validate album name: strip, length cap. Raises ValueError if invalid."""
    if s is None:
        raise ValueError('Album name is required.')
    s = s.strip()[:64]
    if not s:
        raise ValueError('Album name is required.')
    # Allow alphanumeric, spaces, hyphens, underscores
    if not re.match(r'^[a-zA-Z0-9 _-]+$', s):
        raise ValueError('Album name may only contain letters, numbers, spaces, hyphens, and underscores.')
    return s


def validate_email_for_db(s: str | None) -> str:
    """Validate and normalize email. Raises ValueError if invalid. Allows @localhost for dev."""
    if s is None:
        raise ValueError('Email is required.')
    s = (s.strip())[:EMAIL_MAX_LEN]
    if not s:
        raise ValueError('Email is required.')
    if '@' in s and s.split('@')[-1].lower() == 'localhost':
        return s
    from email_validator import validate_email as ve, EmailNotValidError
    try:
        info = ve(s)
        return info.normalized
    except EmailNotValidError as e:
        raise ValueError('Invalid email address.') from e


def validate_password_strength(password: str) -> None:
    """Require min length and at least one letter and one digit. Raises ValueError if weak."""
    if not password or len(password) < PASSWORD_MIN_LEN:
        raise ValueError(f'Password must be at least {PASSWORD_MIN_LEN} characters.')
    if not re.search(r'[a-zA-Z]', password):
        raise ValueError('Password must contain at least one letter.')
    if not re.search(r'\d', password):
        raise ValueError('Password must contain at least one digit.')


def validate_positive_id(value: Any, max_val: int = MAX_ID) -> int:
    """Validate positive integer ID. Raises ValueError if invalid."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError('Invalid id.')
    if n < 1 or n > max_val:
        raise ValueError('Id out of range.')
    return n


def sanitize_search_query(raw: str | None) -> str:
    """Sanitize and limit search query. Returns safe string for LIKE (caller must use ESCAPE '\\')."""
    if raw is None:
        return ''
    s = (raw.strip())[:SEARCH_QUERY_MAX_LEN]
    # Escape LIKE wildcards and backslash for use with ESCAPE '\\'
    s = s.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return s


def validate_delete_ids(payload: Any) -> list[int]:
    """Validate and return list of integer asset IDs. Raises ValueError if invalid."""
    if not isinstance(payload, list):
        raise ValueError('ids must be a list')
    ids: list[int] = []
    for i in payload:
        try:
            if isinstance(i, int):
                n = i
            elif isinstance(i, str) and i.isdigit():
                n = int(i)
            else:
                raise ValueError(f'Invalid id: {i!r}')
        except (TypeError, ValueError) as e:
            raise ValueError(f'Invalid id: {i!r}') from e
        if n < 1 or n > 2**31 - 1:
            raise ValueError(f'Id out of range: {n}')
        ids.append(n)
    if len(ids) > 500:
        raise ValueError('Too many ids')
    return ids


def validate_file_extension_and_mime(filename: str, mimetype: str | None) -> bool:
    """Return True if extension is allowed; MIME must match when provided (or generic/empty is OK)."""
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower()
    allowed_mimes = EXTENSION_MIME.get(ext)
    if not allowed_mimes:
        return False
    mime = (mimetype or '').split(';')[0].strip().lower()
    if not mime or mime in GENERIC_MIMETYPES:
        return True
    return mime in allowed_mimes
