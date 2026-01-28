# design.md

## System Architecture Overview

This document outlines the design for a decoupled image gallery application. The architecture separates application logic and metadata storage (**Flask & SQLite**) from media processing and asset delivery (**Headless WordPress CDN**). This approach leverages the powerful image manipulation and optimization engine of WordPress while maintaining a lightweight, custom Python backend.

---

## Technical Stack

| Component | Technology | Role |
| --- | --- | --- |
| **Backend Framework** | Flask (Python) | Routing, API orchestration, and server-side logic. |
| **Local Database** | SQLite | Persistent storage for media metadata and relational data. |
| **Media Engine** | WordPress REST API | Image hosting, thumbnail generation, and CDN delivery. |
| **Frontend** | Tailwind CSS | Utility-first styling with a focus on minimalism. |
| **Iconography** | Font Awesome | Vector icons for UI elements. |

---

## 1. Database Schema (SQLite)

The local database acts as a high-speed cache for remote asset locations. By storing metadata locally, the application avoids redundant API calls to WordPress during page loads.

```sql
CREATE TABLE IF NOT EXISTS gallery_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    wp_media_id INTEGER UNIQUE NOT NULL, -- Reference to WordPress ID
    title TEXT NOT NULL,
    file_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    url_full TEXT NOT NULL,               -- High-resolution source
    url_thumbnail TEXT NOT NULL,          -- Optimized preview
    url_medium TEXT NOT NULL,             -- Responsive layout size
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_wp_id ON gallery_assets(wp_media_id);

```

---

## 2. Media Orchestration Logic

The automation flow ensures that the user only interacts with the Flask interface. The transition of data is handled server-to-server.

### Upload Flow

1. **Ingestion:** Flask receives the binary stream via a `POST` request.
2. **Validation:** Input is validated for MIME type (e.g., `image/jpeg`, `image/png`) and file size.
3. **Relay:** Flask forwards the binary data to the WordPress `/wp-json/wp/v2/media` endpoint using **HTTP Basic Authentication** (Application Passwords).
4. **Processing:** WordPress generates multiple image sizes (thumbnails, medium, large).
5. **Synchronization:** WordPress returns a JSON response containing the new IDs and URLs. Flask saves this specific metadata into `gallery.db`.

---

## 3. UI/UX Design Principles

The interface follows a **Minimalist Dark Pastel** theme, incorporating **Material You** accessibility and **Glassmorphism** for depth.

### Visual Constraints

* **Palette:** Background in deep slate (`#0f172a`), surfaces in translucent pastels, and accent colors in soft emerald or muted indigo.
* **Glassmorphism:** Navigation bars and upload modals utilize `backdrop-blur-md` and semi-transparent backgrounds (`bg-white/5`) with subtle borders (`border-white/10`).
* **Typography:** Sans-serif, high-contrast, with generous whitespace (kerning and leading).

### UI Components (Tailwind CSS)

* **Gallery Grid:** `grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-6`
* **Image Cards:** Hover-triggered scaling and info overlays using `group` and `transition-all`.
* **Upload Trigger:** A floating action button (FAB) or a clean header-integrated form using Font Awesome (`fa-cloud-arrow-up`).

---

## 4. Security & Performance

### Security-First Approach

* **Sanitization:** All filenames are passed through `werkzeug.utils.secure_filename` before being relayed to the CDN.
* **Credential Isolation:** WordPress API keys and application passwords must reside in a `.env` file, never hardcoded.
* **Error Handling:** Implementation of try-except blocks around the `requests` module to handle WordPress downtime without crashing the Flask application.

### Performance Optimization

* **Lazy Loading:** Images utilize the native `loading="lazy"` attribute.
* **Asset Delivery:** The frontend strictly uses `url_thumbnail` for grid views to minimize payload size, only fetching `url_full` upon explicit user request.
* **Connection Pooling:** Efficient handling of the SQLite connection to prevent database locks during concurrent uploads.

---

## 5. Directory Structure

```text
/project-root
├── app.py              # Application entry point & routes
├── database.py         # SQLite connection & schema management
├── wordpress_api.py    # Logic for WordPress REST API communication
├── .env                # Sensitive credentials (WP_USER, WP_PASS)
├── templates/
│   └── gallery.html    # Glassmorphic UI with Tailwind CSS
└── static/
    └── css/            # Custom Tailwind builds (if applicable)

```

Would you like me to generate the `wordpress_api.py` module with the robust error handling mentioned in the security section?
