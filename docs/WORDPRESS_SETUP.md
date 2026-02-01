# WordPress Setup Guide

This project uses your WordPress site as a "Headless" backend to store and serve images. This guide will help you configure your WordPress site and obtain the necessary credentials.

## Prerequisites

*   A self-hosted WordPress site (or a managed one like WordPress.com with a Business plan).
*   Administrator access to the WordPress dashboard.

---

## Step 1: Enable Permalinks (Crucial)

The WordPress REST API requires "pretty permalinks" to function correctly.

1.  Log in to your WordPress Dashboard (`/wp-admin`).
2.  Go to **Settings > Permalinks**.
3.  Select any option **other than "Plain"** (e.g., "Post name").
4.  Click **Save Changes**.

---

## Step 2: Create a Service User (Optional but Recommended)

It is best practice to create a dedicated user for this application rather than using your main admin account.

1.  Go to **Users > Add New**.
2.  **Username:** `lumina_bot` (or similar).
3.  **Email:** Any valid email.
4.  **Role:** `Author` or `Editor` (allows uploading media).
5.  Save the new user.

---

## Step 3: Generate an Application Password

**Do not use your real login password.** WordPress Application Passwords allow external systems to authenticate without revealing your main credentials.

1.  Go to **Users > Profile** (or edit the new user you just created).
2.  Scroll down to the **Application Passwords** section.
3.  **New Application Password Name:** Enter `Lumina Host`.
4.  Click **Add New Application Password**.
5.  **Copy the generated password** immediately (e.g., `abcd efgh ijkl mnop`). You won't see it again.

> **Note:** If you don't see this section, ensure your site is using HTTPS. If you are on HTTP (local dev), you may need to define `WP_ENVIRONMENT_TYPE` as `local` in `wp-config.php`.

---

## Step 4: Configure `.env`

Open the `.env` file in your project folder and update the following:

```env
# Your site URL + /wp-json/wp/v2/media
WP_API_URL=https://your-site.com/wp-json/wp/v2/media

# The username you used in Step 2/3
WP_USER=lumina_bot

# The password you copied in Step 3 (spaces are okay)
WP_PASS=abcd efgh ijkl mnop
```

---

## Troubleshooting

### 401 Unauthorized
*   **Cause:** Wrong username or password.
*   **Fix:** Double-check `WP_USER`. It must be the **username** (login name), not the display name. Check if the Application Password was copied correctly.

### 403 Forbidden / 502 Bad Gateway
*   **Cause:** Security plugins (Wordfence, iThemes) or Server Firewalls (Cloudflare, ModSecurity) blocking the API request.
*   **Fix:**
    *   Whitelist the IP address of your Lumina Host server.
    *   Ensure "Basic Authentication" is enabled on your server (some hosting providers disable the `Authorization` header).
    *   **Apache Fix:** Add this to your `.htaccess` file:
        ```apache
        RewriteEngine on
        RewriteCond %{HTTP:Authorization} ^(.*)
        RewriteRule ^(.*) - [E=HTTP_AUTHORIZATION:%1]
        ```

### JSON Error / HTML Response
*   **Cause:** The API URL is wrong, and WordPress is returning a 404 page (HTML) instead of JSON.
*   **Fix:** Visit `https://your-site.com/wp-json/` in your browser. If you see JSON data, the API is active. Ensure your `WP_API_URL` ends exactly with `/wp-json/wp/v2/media`.
