"""Request and input validation for Lumina Host."""

from typing import Any

# Max length for search query (chars)
SEARCH_QUERY_MAX_LEN = 200

# MIME types allowed per extension (subset; client can lie so we only sanity-check)
# Include common variants (e.g. image/jpg) and allow octet-stream when extension is valid (mobile often sends that)
EXTENSION_MIME: dict[str, set[str]] = {
    'png': {'image/png'},
    'jpg': {'image/jpeg', 'image/jpg', 'image/pjpeg'},
    'jpeg': {'image/jpeg', 'image/jpg', 'image/pjpeg'},
    'gif': {'image/gif'},
    'webp': {'image/webp'},
}
# When extension is allowed but MIME is generic/empty, still accept (extension is primary check)
GENERIC_MIMETYPES = frozenset({'application/octet-stream', 'application/unknown', ''})


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
