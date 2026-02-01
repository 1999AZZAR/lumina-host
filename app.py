import logging
import os
import requests
from urllib.parse import urlparse
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
from typing import Any
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, login_user, logout_user, login_required
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Local imports
from config import get_config, resolve_secret_key
import database
from auth import User, admin_required, get_current_tenant_id, get_current_user_id, login_required as auth_login_required
from services import AssetService, MediaService
from services.auth import authenticate_user, create_user as auth_create_user, generate_api_token, validate_api_token
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

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to continue.'


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    row = database.get_user_by_id(uid)
    return User(row) if row else None


def ensure_default_admin() -> None:
    """Create default tenant and admin user at startup if missing and ADMIN_PASSWORD is set."""
    if not _config.admin_password:
        return
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM tenants LIMIT 1')
        row = cursor.fetchone()
        if not row:
            cursor.execute('INSERT INTO tenants (name, slug) VALUES (?, ?)', ('Default', 'default'))
            conn.commit()
            tenant_id = cursor.lastrowid
            logger.info("Created default tenant (id=%s)", tenant_id)
        else:
            tenant_id = row['id']
        cursor.execute("SELECT id FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1")
        row = cursor.fetchone()
        if not row:
            from services.auth import hash_password
            password_hash = hash_password(_config.admin_password)
            cursor.execute(
                'INSERT INTO users (username, email, password_hash, role, tenant_id) VALUES (?, ?, ?, ?, ?)',
                (_config.admin_username, _config.admin_email, password_hash, 'admin', tenant_id),
            )
            conn.commit()
            logger.info("Created default admin user '%s' (id=%s)", _config.admin_username, cursor.lastrowid)
        else:
            admin_id = row['id']
            from services.auth import hash_password
            password_hash = hash_password(_config.admin_password)
            cursor.execute(
                'UPDATE users SET password_hash = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                (password_hash, admin_id),
            )
            conn.commit()
            logger.info("Updated password for admin user '%s' from ADMIN_PASSWORD.", _config.admin_username)


@app.before_request
def authenticate_api_token():
    """If Authorization: Bearer <token> is present and no session user, log in via token."""
    from flask_login import current_user
    if current_user.is_authenticated:
        return
    auth = request.headers.get('Authorization')
    if not auth or not auth.startswith('Bearer '):
        return
    token = auth[7:].strip()
    if not token:
        return
    row = validate_api_token(token)
    if not row:
        return
    user_row = database.get_user_by_id(row['user_id'])
    if not user_row:
        return
    login_user(User(user_row))
    database.touch_api_token(token)


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


@app.errorhandler(401)
def unauthorized(error: Exception) -> tuple[Any, int]:
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Authentication required.'}), 401
    flash('Please log in to continue.')
    return redirect(url_for('login', next=request.url))


@app.errorhandler(403)
def forbidden(error: Exception) -> tuple[Any, int]:
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': 'Access denied.'}), 403
    flash('Access denied.')
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


@app.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    """Login page and handler."""
    if request.method == 'GET':
        if request.referrer and urlparse(request.referrer).path != urlparse(request.url).path:
            next_url = request.args.get('next') or request.referrer
        else:
            next_url = request.args.get('next') or url_for('index')
        return render_template(
            'login.html',
            next_url=next_url,
            enable_registration=_config.enable_registration,
        )
    username = (request.form.get('username') or '').strip()
    password = request.form.get('password') or ''
    if not username or not password:
        flash('Username and password are required.')
        return render_template('login.html', next_url=request.form.get('next') or url_for('index'))
    user_row = authenticate_user(username, password)
    if not user_row:
        flash('Invalid username or password.')
        return render_template('login.html', next_url=request.form.get('next') or url_for('index'))
    login_user(User(user_row))
    next_url = (request.form.get('next') or '').strip()
    if not next_url or next_url.startswith('//') or not next_url.startswith('/'):
        next_url = url_for('index')
    return redirect(next_url)


@app.route('/logout', methods=['GET', 'POST'])
def logout():
    """Logout handler."""
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))


@app.route('/register', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def register():
    """Registration (only when ENABLE_REGISTRATION is set)."""
    if not _config.enable_registration:
        flash('Registration is disabled.')
        return redirect(url_for('index'))
    if request.method == 'GET':
        return render_template('register.html')
    username = (request.form.get('username') or '').strip()[:64]
    email = (request.form.get('email') or '').strip()[:256]
    password = request.form.get('password') or ''
    if not username or not email or not password:
        flash('Username, email and password are required.')
        return render_template('register.html')
    try:
        from email_validator import validate_email as ve
        ve(email)
    except Exception:
        flash('Invalid email address.')
        return render_template('register.html')
    if len(password) < 8:
        flash('Password must be at least 8 characters.')
        return render_template('register.html')
    user_id = auth_create_user(username, email, password, role='user', tenant_id=None)
    if not user_id:
        flash('Username or email already in use.')
        return render_template('register.html')
    flash('Account created. You can log in now.')
    return redirect(url_for('login'))


@app.route('/profile')
@auth_login_required
def profile():
    """User profile and API token management."""
    return render_template('profile.html')


@app.route('/api/tokens', methods=['GET'])
@auth_login_required
def list_tokens():
    """List current user's API tokens (no secret value)."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    tokens = database.get_user_tokens(user_id)
    return jsonify({'tokens': [dict(t) for t in tokens]})


@app.route('/api/tokens', methods=['POST'])
@auth_login_required
def create_token():
    """Create a new API token. Raw token returned only once."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()[:64] or None
    expires_days = _config.api_token_expiry_days
    try:
        raw_token, token_id = generate_api_token(user_id, name=name, expires_days=expires_days)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    return jsonify({
        'id': token_id,
        'token': raw_token,
        'name': name,
        'expires_days': expires_days,
        'message': 'Store this token securely; it will not be shown again.',
    }), 201


@app.route('/api/tokens/<int:token_id>', methods=['DELETE'])
@auth_login_required
def revoke_token(token_id: int):
    """Revoke an API token belonging to the current user."""
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({'error': 'Unauthorized'}), 401
    if database.revoke_api_token(token_id, user_id):
        return jsonify({'message': 'Token revoked.'})
    return jsonify({'error': 'Token not found or already revoked.'}), 404


@app.route('/admin/users', methods=['GET'])
@auth_login_required
@admin_required
def admin_list_users():
    """Admin: list users."""
    users = database.list_users()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users', methods=['POST'])
@auth_login_required
@admin_required
@limiter.limit('20 per hour')
def admin_create_user():
    """Admin: create user."""
    data = request.get_json(silent=True) or request.form
    username = (data.get('username') or '').strip()[:64]
    email = (data.get('email') or '').strip()[:256]
    password = (data.get('password') or '')[:256]
    role = (data.get('role') or 'user').strip()[:16] or 'user'
    if role not in ('admin', 'user'):
        role = 'user'
    if not username or not email or not password:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Username, email and password required.'}), 400
        flash('Username, email and password required.')
        return redirect(url_for('admin_list_users'))
    try:
        from email_validator import validate_email as ve
        ve(email)
    except Exception:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Invalid email.'}), 400
        flash('Invalid email.')
        return redirect(url_for('admin_list_users'))
    if len(password) < 8:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Password must be at least 8 characters.'}), 400
        flash('Password must be at least 8 characters.')
        return redirect(url_for('admin_list_users'))
    user_id = auth_create_user(username, email, password, role=role, tenant_id=None)
    if not user_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'error': 'Username or email already in use.'}), 400
        flash('Username or email already in use.')
        return redirect(url_for('admin_list_users'))
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'id': user_id, 'username': username}), 201
    flash(f'User {username} created.')
    return redirect(url_for('admin_list_users'))


@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@auth_login_required
@admin_required
def admin_delete_user(user_id: int):
    """Admin: deactivate user (soft delete)."""
    from flask_login import current_user
    if current_user.id == user_id:
        return jsonify({'error': 'Cannot delete your own account.'}), 400
    with database.get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'error': 'User not found.'}), 404
    return jsonify({'message': 'User deactivated.'})


@app.route('/')
def index():
    """Render the initial gallery view (Page 1)."""
    tenant_id = get_current_tenant_id()
    user_id = get_current_user_id()
    from flask_login import current_user
    if current_user.is_authenticated and getattr(current_user, 'role', None) == 'admin':
        tenant_id = None
        user_id = None
    result = AssetService.get_assets(page=1, per_page=20, tenant_id=tenant_id, user_id=user_id)
    return render_template('gallery.html', assets=result['assets'], has_more=result['has_more'])


@app.route('/api/assets')
def get_assets_api():
    """API for Infinite Scroll & Search. Filtered by tenant/user when logged in."""
    try:
        page = request.args.get('page', 1, type=int)
        if page < 1:
            page = 1
        search_query = sanitize_search_query(request.args.get('q', ''))
        tenant_id = get_current_tenant_id()
        user_id = get_current_user_id()
        from flask_login import current_user
        if current_user.is_authenticated and getattr(current_user, 'role', None) == 'admin':
            tenant_id = None
            user_id = None
        result = AssetService.get_assets(
            page=page,
            per_page=20,
            search_query=search_query or None,
            tenant_id=tenant_id,
            user_id=user_id,
        )
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
@auth_login_required
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

    user_id = get_current_user_id()
    tenant_id = get_current_tenant_id()
    uploaded_assets, failed = MediaService.upload_files(valid, user_id=user_id, tenant_id=tenant_id)
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
@auth_login_required
def delete_files():
    """Bulk delete assets (only own tenant/user assets)."""
    data = request.get_json(silent=True) or {}
    try:
        ids = validate_delete_ids(data.get('ids', []))
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400
    tenant_id = get_current_tenant_id()
    user_id = get_current_user_id()
    from flask_login import current_user
    if getattr(current_user, 'role', None) == 'admin':
        tenant_id = None
        user_id = None
    try:
        local_deleted, remote_deleted_count = MediaService.delete_assets(
            ids, tenant_id=tenant_id, user_id=user_id
        )
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
    ensure_default_admin()

    app.run(debug=True, host='0.0.0.0', port=5050)
