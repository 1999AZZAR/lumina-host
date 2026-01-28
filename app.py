import os
from flask import Flask, render_template, request, redirect, url_for, flash
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
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        # 1. Sanitize
        filename = secure_filename(file.filename)
        # We don't save to disk locally; we pass the file stream directly to WP logic
        
        # 2. Upload to WordPress (or Mock)
        asset_data = wordpress_api.upload_media(file)
        
        if asset_data:
            # 3. Save Metadata Locally
            database.add_asset(asset_data)
            flash('Upload successful!')
        else:
            flash('Upload failed. Check server logs.')
            
        return redirect(url_for('index'))
        
    flash('Invalid file type')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Initialize DB on start
    if not os.path.exists(database.DB_PATH):
        database.init_db()
        print(f"Created new database at {database.DB_PATH}")
    else:
        # Check if table exists, if not init
        # (Naive check, relying on init_db IF NOT EXISTS)
        database.init_db()

    app.run(debug=True, port=5000)
