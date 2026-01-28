# Lumina Host

A decoupled image gallery application that leverages Headless WordPress for robust media management while delivering a lightweight, custom Flask frontend.

## Features

* Decoupled Architecture: Application logic (Flask) is separated from media storage (WordPress).
* Local Caching: SQLite stores metadata for instant page loads, minimizing API calls.
* Glassmorphic UI: Modern, dark-themed interface designed with Tailwind CSS.
* Mock Mode: Built-in simulation for testing without a live WordPress instance.
* Security First: Sanitized filenames and environment-variable based configuration.

## Technical Stack

* Backend: Python 3, Flask
* Database: SQLite
* Frontend: Tailwind CSS, Font Awesome
* Integration: WordPress REST API

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/1999AZZAR/lumina-host.git
   cd lumina-host
   ```

2. Set up Virtual Environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install Dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Configuration:
   The project includes an `example.env` file. You must rename it to `.env` to configure your environment.

   ```bash
   cp example.env .env
   ```

   * Mock Mode: Leave `WP_*` variables empty (or delete them) to test with simulated uploads.
   * Live Mode: Fill in your WordPress credentials to enable real CDN hosting.

   ```env
   WP_API_URL=https://your-site.com/wp-json/wp/v2/media
   WP_USER=your_username
   WP_PASS=your_application_password
   ```

5. Run the Application:

   ```bash
   python app.py
   ```

   Visit `http://127.0.0.1:5000` in your browser.

## Contributing

Please see CONTRIBUTING.md for details on our code of conduct, and the process for submitting pull requests to us.

## License

This project is licensed under the MIT License - see the LICENSE file for details.