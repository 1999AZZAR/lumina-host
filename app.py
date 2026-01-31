import logging
import os
import requests
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from typing import Any
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Local imports
from config import get_config, resolve_secret_key
import database
from services import AssetService, MediaService
from validators import sanitize_search_query, validate_delete_ids, validate_file_extension_and_mime

# Load environment variables
load_dotenv()

_config = get_config()
logging.basicConfig(
    level=logging.DEBUG if _config.debug else logging.INFO,
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)
app = Flask(__name__)
app.secret_key = resolve_secret_key(_config)
app.config['MAX_CONTENT_LENGTH'] = _config.max_content_length_bytes
csrf = CSRFProtect(app)
limiter = Limiter(key_func=get_remote_address, app=app, default_limits=['200 per day', '60 per hour'])

ALLOWED_EXTENSIONS = _config.allowed_extensions

# Private/reserved hostnames and IP ranges that must not be proxied (SSRF mitigation)
BLOCKED_NETLOCS = frozenset(
    {'localhost', '127.0.0.1', '0.0.0.0', '::1', 'metadata.google.internal'}
)


def _get_proxy_allowed_netloc() -> str | None:
    """Extract allowed netloc from WP_API_URL for proxy_download whitelist."""
    api_url = _config.wp_api_url
    if not api_url:
        return None
    parsed = urlparse(api_url)
    if not parsed.netloc:
        return None
    host = parsed.hostname or parsed.netloc.split('@')[-1].split(':')[0]
    return host.lower() if host else None


def _is_safe_proxy_url(url: str) -> bool:
    """Validate URL for proxy_download: scheme http/https and whitelisted host."""
    if not url or len(url) > 2048:
        return False
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in ('http', 'https'):
        return False
    host = (parsed.hostname or parsed.netloc.split('@')[-1].split(':')[0]).lower()
    if not host or host in BLOCKED_NETLOCS:
        return False
    if host.startswith('192.168.') or host.startswith('10.') or host.startswith('169.254.'):
        return False
    allowed = _get_proxy_allowed_netloc()
    if not allowed:
        return False
    return host == allowed or host.endswith('.' + allowed)


@app.errorhandler(413)
def request_entity_too_large(error: Exception) -> Any:
    flash('File too large. Maximum limit is 16MB.')
    return redirect(url_for('index'))


@app.errorhandler(429)
def ratelimit_handler(error: Exception):
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Rate limit exceeded. Try again later.'}), 429
    flash('Rate limit exceeded. Try again later.')
    return redirect(url_for('index'))


@app.errorhandler(500)
def internal_error(error: Exception):
    logger.exception("Unhandled error")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'An unexpected error occurred.'}), 500
    flash('An unexpected error occurred.')
    return redirect(url_for('index'))


def allowed_file(filename: str | None) -> bool:
    if not filename:
        return False
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/health')
def health():
    """Health check for load balancers and monitoring. Returns 200 if DB (and Redis if configured) are OK."""
    try:
        with database.get_db_connection() as conn:
            conn.execute('SELECT 1').fetchone()
    except Exception as e:
        logger.warning("Health check DB failed: %s", e)
        return jsonify({'status': 'unhealthy', 'db': 'down'}), 503
    if database.redis_client:
        try:
            database.redis_client.ping()
        except Exception as e:
            logger.warning("Health check Redis failed: %s", e)
            return jsonify({'status': 'degraded', 'db': 'up', 'redis': 'down'}), 503
    return jsonify({'status': 'healthy', 'db': 'up', 'redis': 'up' if database.redis_client else 'n/a'})


@app.route('/')
def index():
    """Render the initial gallery view (Page 1)."""
    result = AssetService.get_assets(page=1, per_page=20)
    return render_template('gallery.html', assets=result['assets'], has_more=result['has_more'])


@app.route('/api/assets')
def get_assets_api():
    """API for Infinite Scroll & Search."""
    try:
        page = request.args.get('page', 1, type=int)
        if page < 1:
            page = 1
        search_query = sanitize_search_query(request.args.get('q', ''))
        result = AssetService.get_assets(page=page, per_page=20, search_query=search_query or None)
        return jsonify(result)
    except Exception as e:
        logger.exception("get_assets_api failed: %s", e)
        return jsonify({'error': 'Failed to load assets.'}), 500

@app.route('/proxy_download')
@limiter.limit('30 per minute')
def proxy_download():
    """Proxy image download to bypass CORS. URL must be same host as WP_API_URL."""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'Missing URL'}), 400
    if not _is_safe_proxy_url(url):
        return jsonify({'error': 'URL not allowed for proxy'}), 403
    try:
        req = requests.get(url, stream=True, timeout=30)
        req.raise_for_status()
        content_type = req.headers.get('content-type', 'application/octet-stream')
        return Response(
            stream_with_context(req.iter_content(chunk_size=1024)),
            content_type=content_type,
        )
    except requests.RequestException:
        return jsonify({'error': 'Proxy request failed'}), 502

@app.route('/upload', methods=['POST'])
@limiter.limit('20 per minute')
def upload_file():
    """Handle file upload, orchestration to WP, and local metadata save."""
    if 'file' not in request.files:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'error': 'No file part'}), 400
        flash('No file part')
        return redirect(url_for('index'))
    
    files = request.files.getlist('file')
    
    if not files or files[0].filename == '':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'error': 'No selected file'}), 400
        flash('No selected file')
        return redirect(url_for('index'))
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    valid: list[tuple[str, bytes, str]] = []
    for file in files:
        if file and allowed_file(file.filename) and validate_file_extension_and_mime(file.filename, file.content_type):
            try:
                valid.append((secure_filename(file.filename), file.read(), file.content_type or 'application/octet-stream'))
            except Exception as e:
                logger.warning("Failed to read file %s: %s", file.filename, e)
    if not valid:
        if is_ajax:
            return jsonify({'error': 'No valid files to upload'}), 400
        flash('No valid files to upload.')
        return redirect(url_for('index'))

    uploaded_assets, failed = MediaService.upload_files(valid)
    success_count = len(uploaded_assets)
    if is_ajax:
        if success_count > 0:
            msg = 'Upload successful' if not failed else f'Uploaded {success_count}; failed: {", ".join(failed)}'
            return jsonify({'message': msg, 'assets': uploaded_assets}), 200
        return jsonify({'error': f'Upload failed: {", ".join(failed) or "unknown"}'}), 502 if failed else 500

    if success_count > 0:
        flash(f'Successfully uploaded {success_count} files.' + (f' Failed: {", ".join(failed)}' if failed else ''))
    else:
        flash('Upload failed. Check server logs.')
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
@limiter.limit('30 per minute')
def delete_files():
    """Bulk delete assets."""
    data = request.get_json(silent=True) or {}
    try:
        ids = validate_delete_ids(data.get('ids', []))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    try:
        local_deleted, remote_deleted_count = MediaService.delete_assets(ids)
        return jsonify({
            'message': f'Deleted {local_deleted} local assets. Remote cleanup: {remote_deleted_count}/{local_deleted} successful.',
            'deleted_ids': ids
        })
    except Exception as e:
        logger.exception("delete_files failed: %s", e)
        return jsonify({'error': 'Delete failed.'}), 500

if __name__ == '__main__':
    if not os.path.exists(database.DB_PATH):
        database.init_db()
        logger.info("Created new database at %s", database.DB_PATH)
    else:
        database.init_db()

    app.run(debug=True, host='0.0.0.0', port=5050)
