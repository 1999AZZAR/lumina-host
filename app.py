import os
import time
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Local imports
import database
import wordpress_api

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-prod')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16MB limit

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('File too large. Maximum limit is 16MB.')
    return redirect(url_for('index'))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Render the gallery grid with assets from the local DB."""
    assets = database.get_all_assets()
    return render_template('gallery.html', assets=assets)

@app.route('/upload', methods=['POST'])
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
    
    # AJAX / Queue Mode (Single file per request expected usually, but loop works)
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    uploaded_assets = []

    success_count = 0
    for file in files:
        if file and allowed_file(file.filename):
            # 1. Sanitize
            filename = secure_filename(file.filename)
            
            # 2. Upload to WordPress
            asset_data = wordpress_api.upload_media(file)
            
            if asset_data:
                # 3. Save Metadata Locally
                database.add_asset(asset_data)
                uploaded_assets.append(asset_data)
                success_count += 1
            elif is_ajax:
                return jsonify({'error': f'Failed to upload {filename} to WordPress'}), 502
            
    if is_ajax:
        if success_count > 0:
            return jsonify({'message': 'Upload successful', 'assets': uploaded_assets}), 200
        else:
            return jsonify({'error': 'Upload failed'}), 500

    # Standard Form Fallback
    if success_count > 0:
        flash(f'Successfully uploaded {success_count} files.')
    else:
        flash('Upload failed. Check server logs.')
            
    return redirect(url_for('index'))

@app.route('/delete', methods=['POST'])
def delete_files():
    """Bulk delete assets."""
    data = request.get_json()
    ids = data.get('ids', [])
    
    if not ids:
        return jsonify({'error': 'No IDs provided'}), 400

    # 1. Delete from Local DB and get WP IDs
    wp_ids = database.delete_assets(ids)
    
    # 2. Delete from WordPress (Async-like loop)
    remote_deleted_count = 0
    for wp_id in wp_ids:
        if wordpress_api.delete_media(wp_id):
            remote_deleted_count += 1
        time.sleep(0.5) # Throttle to prevent 502/429 errors
            
    return jsonify({
        'message': f'Deleted {len(ids)} local assets. Remote cleanup: {remote_deleted_count}/{len(wp_ids)} successful.',
        'deleted_ids': ids
    })

if __name__ == '__main__':
    # Initialize DB on start
    if not os.path.exists(database.DB_PATH):
        database.init_db()
        print(f"Created new database at {database.DB_PATH}")
    else:
        # Check if table exists, if not init
        # (Naive check, relying on init_db IF NOT EXISTS)
        database.init_db()

    app.run(debug=True, host='0.0.0.0', port=5000)