import os
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Local imports
import database
import wordpress_api

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-prod')
app.config['MAX_CONTENT_LENGTH'] = 128 * 1024 * 1024 # Increased to 128MB for folder uploads

# Allowed extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

@app.errorhandler(413)
def request_entity_too_large(error):
    flash('Upload too large. Maximum limit is 128MB.')
    return redirect(url_for('index'))

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    """Render the gallery grid with Albums and Orphan Assets."""
    assets = database.get_all_assets()
    albums = database.get_albums()
    return render_template('gallery.html', assets=assets, albums=albums)

@app.route('/album/<int:album_id>')
def view_album(album_id):
    """Render a specific album."""
    # Fetch album details (naive check from get_albums)
    all_albums = database.get_albums()
    album = next((a for a in all_albums if a['id'] == album_id), None)
    
    if not album:
        abort(404)
        
    assets = database.get_assets_by_album(album_id)
    return render_template('gallery.html', assets=assets, current_album=album)

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle single file OR folder upload."""
    if 'file' not in request.files:
        flash('No file part')
        return redirect(url_for('index'))
    
    files = request.files.getlist('file')
    
    if not files or files[0].filename == '':
        flash('No selected file')
        return redirect(url_for('index'))

    # Detect Album Mode
    # If multiple files share a directory path, or if explicit 'is_album' flag is set (not used here yet),
    # or simply if the input was webkitdirectory.
    # We infer "Album Mode" if there are multiple files OR if the first file has a path separator.
    
    album_id = None
    first_filename = files[0].filename
    
    # Check if folder upload (webkitRelativePath usually sent as filename 'Folder/Img.jpg')
    if '/' in first_filename:
        folder_name = first_filename.split('/')[0]
        # Create Album
        album_id = database.create_album(folder_name)
        flash(f'Created album: {folder_name}')
    elif len(files) > 1:
        # Multiple files selected but flat? Create "Batch Upload" album? 
        # For now, treat as loose files unless folder structure is detected.
        # User asked: "upload entire folder that will automatically became an album"
        pass

    success_count = 0
    
    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Upload to WordPress
            asset_data = wordpress_api.upload_media(file)
            
            if asset_data:
                database.add_asset(asset_data, album_id=album_id)
                success_count += 1
    
    if success_count > 0:
        flash(f'Successfully uploaded {success_count} files.')
    else:
        flash('Upload failed or no valid images found.')
            
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Initialize DB on start
    if not os.path.exists(database.DB_PATH):
        database.init_db()
        print(f"Created new database at {database.DB_PATH}")
    else:
        database.init_db()

    app.run(debug=True, port=5000)