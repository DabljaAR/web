# Google Auth Credentials Setup

Step-by-step instructions to obtain and configure Google OAuth credentials for DabljaAR.

---

## Step 1: Create a Google Cloud Project

1. Open your browser and go to https://console.cloud.google.com
2. Sign in with your Google account
3. At the top of the page, click the project drop-down (next to "Google Cloud" logo)
4. Click **New Project**
5. Enter a project name, e.g. `DabljaAR`
6. Click **Create**
7. Once created, make sure the new project is selected in the top drop-down

---

## Step 2: Configure the OAuth consent screen

1. In the left sidebar menu, click **APIs & Services**
2. Click **OAuth consent screen**
3. Select **External** (unless you are building this for only users in your Google Workspace organization)
4. Click **Create**

### App Information

| Field | What to enter |
|-------|---------------|
| **App name** | `DabljaAR` (or your app name) |
| **User support email** | Your email address |
| **Developer contact information** | Your email address |

5. Click **Save and Continue**

### Scopes

6. Click **Add or Remove Scopes**
7. In the filter box, search for and select these scopes:
   - `.../auth/userinfo.email` — View your email address
   - `.../auth/userinfo.profile` — View your basic profile info
   - `openid` — Associate you with your personal info on Google
8. Click **Update**
9. Click **Save and Continue**

### Test users

10. If your app is in **Testing** mode (before publishing), click **Add Users** and add your email address
11. Click **Save and Continue**

### Summary

12. Review the summary and click **Back to Dashboard**

> **Production:** Once you are ready, click **Publish App** on the consent screen dashboard. Until then, only test users can sign in.

---

## Step 3: Create OAuth 2.0 Client ID

1. In the left sidebar, click **Credentials**
2. At the top, click **Create Credentials** → **OAuth 2.0 Client ID**

### Application type

3. Select **Web application**

### Name

4. Give it a name, e.g. `DabljaAR Web Client`

### Authorized JavaScript origins

> This tells Google which domains are allowed to make Google Sign-In requests from the browser.

5. Click **Add URI** under **Authorized JavaScript origins**
6. Enter each of the following (one at a time, click Add URI for each):

| Environment | URI to add |
|-------------|------------|
| Local development | `http://localhost:5173` |
| Local development (alt) | `http://localhost:3000` |
| Production | `https://app.yourdomain.com` (replace with your actual domain) |

### Authorized redirect URIs

> This tells Google where to send the user after authentication (used by Google's backend-to-backend flow). Even though this project uses credential-based (one-tap) auth via JS, you should still set these for completeness.

7. Click **Add URI** under **Authorized redirect URIs**
8. Enter each of the following:

| Environment | URI to add |
|-------------|------------|
| Local development | `http://localhost:8000/api/auth/google/callback` |
| Production | `https://app.yourdomain.com/api/auth/google/callback` (replace with your actual domain) |

### Finish

9. Click **Create**
10. A pop-up dialog appears with your **Client ID** and **Client Secret**

---

## Step 4: Copy the Client ID

1. In the pop-up dialog, find **Your Client ID**
2. Click the copy icon (or select the full value and press Ctrl+C / Cmd+C)
3. It will look something like:
   ```
   266126473698-0uqu4cfhha3bp2b9klirl6qhcov8r2g0.apps.googleusercontent.com
   ```
4. Click **OK** to close the dialog

> **Don't lose this!** If you close the dialog, you can find it again later: go to **APIs & Services** → **Credentials**, find your client, and click the pencil icon to view/edit.

---

## Step 5: Set the environment variables

### Backend (`backend/.env` for local, or `.env.production` for deployment)

1. Open `backend/.env` (or `.env.production` at the repo root)
2. Find the line:
   ```
   GOOGLE_CLIENT_ID=
   ```
3. Paste the Client ID after the `=` sign:
   ```
   GOOGLE_CLIENT_ID=266126473698-0uqu4cfhha3bp2b9klirl6qhcov8r2g0.apps.googleusercontent.com
   ```

### Frontend (`frontend/.env`)

1. Open `frontend/.env`
2. Find the line:
   ```
   VITE_GOOGLE_CLIENT_ID=
   ```
3. Paste the **same** Client ID after the `=` sign:
   ```
   VITE_GOOGLE_CLIENT_ID=266126473698-0uqu4cfhha3bp2b9klirl6qhcov8r2g0.apps.googleusercontent.com
   ```

> **Important:** Both `GOOGLE_CLIENT_ID` and `VITE_GOOGLE_CLIENT_ID` must be set to the **exact same value**. The backend verifies the token's `aud` (audience) claim against this ID.

---

## Step 6: Verify it works

1. Start the application (frontend + backend)
2. Open the app in your browser
3. Click **Sign in with Google** or the Google sign-in button
4. A Google one-tap pop-up should appear (or a new window if using the button flow)
5. Select a Google account and sign in
6. If successful, you will be logged into DabljaAR

### Troubleshooting

| Issue | Likely cause | Fix |
|-------|-------------|-----|
| `Google authentication is not configured on the server` | `GOOGLE_CLIENT_ID` is empty in the backend | Check `backend/.env` or `.env.production` |
| `Google token audience mismatch` | `GOOGLE_CLIENT_ID` in backend does not match the Client ID from Google Cloud Console | Copy the exact Client ID from Google Cloud Console |
| Pop-up says "invalid client" or "redirect_uri_mismatch" | `VITE_GOOGLE_CLIENT_ID` is wrong, or authorized origins/URIs are not set correctly | Double-check the Client ID and the Authorized JavaScript origins in Google Cloud Console |
| `VITE_GOOGLE_CLIENT_ID is not configured` (console warning) | Frontend `.env` is missing `VITE_GOOGLE_CLIENT_ID` or the app was not restarted after editing | Add the variable and restart the dev server |

---

## Quick Reference

```env
# backend/.env or .env.production
GOOGLE_CLIENT_ID=266126473698-0uqu4cfhha3bp2b9klirl6qhcov8r2g0.apps.googleusercontent.com

# frontend/.env
VITE_GOOGLE_CLIENT_ID=266126473698-0uqu4cfhha3bp2b9klirl6qhcov8r2g0.apps.googleusercontent.com
```
