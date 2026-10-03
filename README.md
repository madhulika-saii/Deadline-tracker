# 📅 AI Deadline Tracker with Google Classroom

An AI-powered academic assistant that combines **Google Classroom assignments** and **photographed/uploaded syllabi, timetables, and academic notices** using **Gemini Vision**, sorts all upcoming deadlines chronologically, and emails a structured digest to the student via **Gmail SMTP**.

---

## 🏗️ Architecture

```text
                 ┌─────────────────────┐
                 │ Google Classroom     │
                 └──────────┬──────────┘
                            ↓
                    Classroom OAuth
                            ↓
                  Courses + Coursework
                            ↓
                       Due dates
                            │
                            │
Academic Documents ──→ Gemini extraction
                            │
                            ↓
                 ┌─────────────────────┐
                 │ AI DEADLINE TRACKER │
                 └──────────┬──────────┘
                            ↓
                    Deadline summary
                            ↓
                     Gmail Digest
```

---

## 📁 Project Structure

```text
deadline-tracker/
├── app.py                         # Streamlit UI & unified application flow
├── classroom_service.py           # Google Classroom API & OAuth 2.0 service
├── prompts.py                     # AI system & user prompt templates
├── requirements.txt               # Dependencies
├── .gitignore                     # Protects secrets.toml and OAuth tokens from Git
├── CLASSROOM_SETUP.md             # Complete Google Cloud & Classroom setup guide
└── .streamlit/
    └── secrets.toml.example       # Template for secrets
```

---

## 🚀 Quickstart & Local Setup

### 1. Prerequisites
- **Python 3.9+** installed
- **Gemini API Key** from [Google AI Studio](https://aistudio.google.com)
- **Gmail Account** with:
  - 2-Step Verification enabled
  - A 16-character **Gmail App Password** from [Google Account Security](https://myaccount.google.com/security)
- **Google Cloud Project** with **Google Classroom API** enabled (see [`CLASSROOM_SETUP.md`](file:///c:/Users/rames/Deadline%20Tracker/CLASSROOM_SETUP.md))

### 2. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 3. Configure Local Secrets

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`:

```toml
GEMINI_API_KEY = "your-gemini-api-key"
GMAIL_ADDRESS = "your-email@gmail.com"
GMAIL_APP_PASSWORD = "abcd efgh ijkl mnop"

# Google Classroom OAuth (Desktop / Web Client)
GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET = "your-client-secret"
```

### 4. Run the Application

```powershell
streamlit run app.py
```

Open `http://localhost:8501`.

---

## 🎓 Google Classroom Integration Features

1. **Connect & Authorize**: Click **🎓 Connect Google Classroom** in the sidebar to authorize read-only access to courses and assignments.
2. **Synchronize**: Click **🔄 Sync** to fetch active courses and extract all coursework due dates.
3. **AI Chat Awareness**: Ask questions like:
   - *"What assignments do I have this week?"*
   - *"Show me all my DBMS coursework."*
   - *"What is my next deadline?"*
4. **Unified Email Digest**: Click **📧 Send Deadline Digest** to send an email combining both Google Classroom tasks and document-extracted milestones.
