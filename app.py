import os
import time
import requests
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response, stream_with_context
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
    """Render the initial gallery view (Page 1)."""
    # Fetch first page (20 items)
    result = database.get_assets(page=1, per_page=20)
    return render_template('gallery.html', assets=result['assets'], has_more=result['has_more'])

@app.route('/api/assets')
def get_assets_api():
    """API for Infinite Scroll & Search."""
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '')
    
    result = database.get_assets(page=page, per_page=20, search_query=search_query)
    return jsonify(result)

@app.route('/proxy_download')
def proxy_download():
    """Proxy image download to bypass CORS."""
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400
        
    req = requests.get(url, stream=True)
    return Response(stream_with_context(req.iter_content(chunk_size=1024)), 
                    content_type=req.headers['content-type'])

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
    
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    uploaded_assets = []

    success_count = 0
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            asset_data = wordpress_api.upload_media(file)
            
            if asset_data:
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

    wp_ids = database.delete_assets(ids)
    
    remote_deleted_count = 0
    for wp_id in wp_ids:
        if wordpress_api.delete_media(wp_id):
            remote_deleted_count += 1
        time.sleep(0.5) 
            
    return jsonify({
        'message': f'Deleted {len(ids)} local assets. Remote cleanup: {remote_deleted_count}/{len(wp_ids)} successful.',
        'deleted_ids': ids
    })

if __name__ == '__main__':
    if not os.path.exists(database.DB_PATH):
        database.init_db()
        print(f"Created new database at {database.DB_PATH}")
    else:
        database.init_db()

    app.run(debug=True, host='0.0.0.0', port=5000)
