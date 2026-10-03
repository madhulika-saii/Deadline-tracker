# 🎓 Google Classroom Integration Setup Guide

Follow these steps to connect your **Google Classroom** account to the **AI Deadline Tracker** to automatically pull in your active courses, assignments, and due dates.

---

### Step 1: Open Google Cloud Console
1. Visit [Google Cloud Console](https://console.cloud.google.com).
2. Sign in with your Google account.

---

### Step 2: Create or Select a Google Cloud Project
1. In the top navigation bar, click the project selector dropdown.
2. Click **New Project**.
3. Name it `AI Deadline Tracker` and click **Create**.
4. Make sure your new project is selected in the top bar.

---

### Step 3: Enable the Google Classroom API
1. In the left navigation menu, go to **APIs & Services** → **Library** (or search for `Google Classroom API`).
2. Select **Google Classroom API**.
3. Click the blue **Enable** button.

---

### Step 4: Configure the OAuth Consent Screen
1. Go to **APIs & Services** → **OAuth consent screen**.
2. Select **External** (or **Internal** if using a Google Workspace school account) and click **Create**.
3. Fill in the required fields:
   - **App name**: `AI Deadline Tracker`
   - **User support email**: Select your email address.
   - **Developer contact information**: Enter your email address.
4. Click **Save and Continue**.

---

### Step 5: Add Read-Only Classroom Scopes
In the **Scopes** section of the consent screen configuration:
1. Click **Add or Remove Scopes**.
2. Search for `Classroom` and select ONLY these read-only scopes:
   - `https://www.googleapis.com/auth/classroom.courses.readonly` (View your Google Classroom courses)
   - `https://www.googleapis.com/auth/classroom.coursework.me.readonly` (View your coursework and assignments)
3. Click **Update** and then **Save and Continue**.

---

### Step 6: Add Test Users (If in "Testing" mode)
1. In the **Test users** section, click **+ Add Users**.
2. Enter the Google/Gmail address of the student account you want to connect to Google Classroom.
3. Click **Save and Continue**.

---

### Step 7: Create OAuth 2.0 Client Credentials
1. Go to **APIs & Services** → **Credentials**.
2. Click **+ Create Credentials** → **OAuth client ID**.
3. Under **Application type**, choose:
   - **Desktop app** (recommended for local development) OR **Web application** with authorized redirect URI `http://localhost:8501`.
4. Name it `Deadline Tracker Client` and click **Create**.
5. Copy your **Client ID** and **Client Secret**.

---

### Step 8: Add OAuth Credentials to Streamlit Secrets
Open your local `.streamlit/secrets.toml` file (or **App Settings → Secrets** on Streamlit Community Cloud) and add:

```toml
GOOGLE_CLIENT_ID = "your-copied-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "your-copied-client-secret"
```

---

### Step 9: Launch & Connect
1. Start the Streamlit application:
   ```powershell
   streamlit run app.py
   ```
2. In the sidebar, under **🎓 Google Classroom**, click:
   ```text
   🎓 Connect Google Classroom
   ```
3. A browser window will open asking you to sign in with your Google Classroom account and authorize read-only permissions.
4. Once authorized, return to the app and click:
   ```text
   🔄 Sync Classroom
   ```
5. All your courses and upcoming assignment deadlines will be loaded into your Deadline Tracker dashboard and made available to Gemini AI and your Email Digest!
