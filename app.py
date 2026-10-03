import os
import smtplib
from email.mime.text import MIMEText

from google import genai
from google.genai import types
import streamlit as st

from classroom_service import (
    authenticate_google_classroom,
    build_classroom_service,
    clear_classroom_session,
    format_classroom_deadlines_for_gemini,
    get_all_classroom_deadlines,
    get_courses,
    get_oauth_client_config,
)
from prompts import (
    SUMMARY_REQUEST_PROMPT,
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
)

# Centralized Model Configuration
MODEL_NAME = "gemini-3.5-flash-lite"

st.set_page_config(
    page_title="AI Deadline Tracker",
    page_icon="📅",
    layout="wide",
)


# ==========================================
# Section: Safe API Key Loading & Gemini Client
# ==========================================
def get_gemini_api_key():
    key = st.secrets.get("GEMINI_API_KEY", "")

    if not key:
        key = os.getenv("GEMINI_API_KEY", "")

    return str(key).strip()


@st.cache_resource
def get_gemini_client(api_key):
    return genai.Client(api_key=api_key)


def test_gemini_connection():
    api_key = get_gemini_api_key()

    if not api_key:
        return False, "GEMINI_API_KEY is missing."

    try:
        client = get_gemini_client(api_key)

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents="Reply with exactly: Gemini connection successful.",
        )

        if response and response.text:
            return True, response.text

        return False, "Gemini returned an empty response."

    except Exception as error:
        error_text = str(error)

        if "API_KEY_INVALID" in error_text:
            return False, "API_KEY_INVALID"
        elif "PERMISSION_DENIED" in error_text:
            return False, "PERMISSION_DENIED"
        elif "RESOURCE_EXHAUSTED" in error_text:
            return False, "RESOURCE_EXHAUSTED"
        elif "NOT_FOUND" in error_text:
            return False, "NOT_FOUND"
        elif "INVALID_ARGUMENT" in error_text:
            return False, "INVALID_ARGUMENT"

        return False, error_text


def get_gemini_chat():
    if "chat" in st.session_state:
        return st.session_state.chat

    api_key = get_gemini_api_key()

    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    client = get_gemini_client(api_key)

    st.session_state.chat = client.chats.create(
        model=MODEL_NAME,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT
        ),
    )

    return st.session_state.chat


def ask_gemini(parts):
    try:
        chat = get_gemini_chat()

        # If Classroom deadlines are synced, enrich the prompt context seamlessly
        enriched_parts = list(parts)
        classroom_deadlines = st.session_state.get("classroom_deadlines", [])

        if classroom_deadlines:
            classroom_summary = format_classroom_deadlines_for_gemini(classroom_deadlines)
            context_instruction = (
                f"\n\n[Background Google Classroom Context for Student]:\n{classroom_summary}\n"
                "Use this accurate Google Classroom data when answering questions about coursework, courses, or deadlines.\n"
            )
            # Prepend or append context to the last string part
            for i in range(len(enriched_parts) - 1, -1, -1):
                if isinstance(enriched_parts[i], str):
                    enriched_parts[i] = enriched_parts[i] + context_instruction
                    break

        response = chat.send_message(enriched_parts)

        if not response or not response.text:
            return "Gemini returned an empty response."

        return response.text

    except Exception as error:
        error_text = str(error)

        if "API_KEY_INVALID" in error_text:
            return (
                "⚠️ Gemini API authentication failed.\n\n"
                "The application is running correctly, but Google did not accept "
                "the configured Gemini credential.\n\n"
                "Please replace the deployed GEMINI_API_KEY in Streamlit Secrets "
                "with a valid API key from Google AI Studio."
            )
        elif "PERMISSION_DENIED" in error_text:
            return "⚠️ Gemini API error: Permission denied for this API key."
        elif "RESOURCE_EXHAUSTED" in error_text:
            return "⚠️ Gemini API rate limit or quota exceeded. Please try again in a moment."
        elif "NOT_FOUND" in error_text:
            return f"⚠️ Gemini model '{MODEL_NAME}' was not found."

        return f"Sorry, something went wrong: {error_text}"


# ==========================================
# Section: Gmail SMTP Functionality
# ==========================================
def get_gmail_credentials():
    address = str(st.secrets.get("GMAIL_ADDRESS", os.getenv("GMAIL_ADDRESS", ""))).strip()
    # Remove any accidental whitespace or spaces in the 16-character app password
    password = str(st.secrets.get("GMAIL_APP_PASSWORD", os.getenv("GMAIL_APP_PASSWORD", ""))).strip().replace(" ", "")
    return address, password


def clean_email_text(text):
    if not text:
        return "No academic deadline summary available."

    text = text.strip()

    return text[:5000] + "..." if len(text) > 5000 else text


def send_email(to_address, user_name, summary):
    gmail_address, gmail_app_password = get_gmail_credentials()

    if not gmail_address or not gmail_app_password:
        return False, "GMAIL_ADDRESS or GMAIL_APP_PASSWORD is not configured in Streamlit secrets."

    try:
        cleaned_summary = clean_email_text(summary)

        body = (
            f"Hello {user_name},\n\n"
            "Here is your academic deadline summary:\n\n"
            f"{cleaned_summary}\n\n"
            "Please make sure to complete your tasks before their deadlines.\n\n"
            "— AI Deadline Tracker"
        )

        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = "📅 Upcoming Academic Deadlines"
        message["From"] = gmail_address
        message["To"] = to_address

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_address, gmail_app_password)
            server.send_message(message)

        return True, "Email sent successfully."

    except smtplib.SMTPAuthenticationError:
        return (
            False,
            "Gmail authentication failed. Check that GMAIL_ADDRESS is correct and GMAIL_APP_PASSWORD is a valid 16-character Gmail App Password.",
        )
    except smtplib.SMTPException as error:
        return False, f"Gmail SMTP error: {str(error)}"
    except Exception as error:
        return False, str(error)


# ==========================================
# Section: UI Helpers
# ==========================================
def render_message(message):
    with st.chat_message(message["role"]):
        if message["kind"] == "text":
            st.write(message["content"])
        elif message["kind"] == "image":
            st.image(message["content"])


def add_message(role, kind, content):
    if "messages" not in st.session_state:
        st.session_state.messages = []

    st.session_state.messages.append(
        {
            "role": role,
            "kind": kind,
            "content": content,
        }
    )

    render_message(st.session_state.messages[-1])


# ==========================================
# Section: Google Classroom Sync Logic
# ==========================================
def sync_classroom_data():
    """Fetches courses, coursework, and normalizes deadlines from Google Classroom."""
    creds = st.session_state.get("classroom_credentials")
    if not creds:
        return False, "Google Classroom is not connected. Please connect first."

    try:
        service = build_classroom_service(creds)
        success_courses, courses, msg_courses = get_courses(service)

        if not success_courses:
            return False, msg_courses

        st.session_state.classroom_courses = courses

        deadlines = get_all_classroom_deadlines(service, courses)
        st.session_state.classroom_deadlines = deadlines
        st.session_state.classroom_connected = True

        dated_count = sum(1 for d in deadlines if d.get("has_due_date"))
        return (
            True,
            f"Classroom synced successfully! Found {len(courses)} course(s), {len(deadlines)} total assignment(s) ({dated_count} with due dates).",
        )
    except Exception as error:
        return False, f"Failed to sync Classroom: {str(error)}"


# ==========================================
# SIDEBAR: System Status & Google Classroom
# ==========================================
with st.sidebar:
    st.header("⚙️ System Control")

    # 1. Google Classroom Integration
    st.subheader("🎓 Google Classroom")
    classroom_connected = st.session_state.get("classroom_connected", False)

    if classroom_connected:
        st.success("Status: 🟢 Connected")
        courses_count = len(st.session_state.get("classroom_courses", []))
        deadlines_list = st.session_state.get("classroom_deadlines", [])
        dated_deadlines = sum(1 for d in deadlines_list if d.get("has_due_date"))

        st.caption(f"📚 **Courses:** {courses_count} | 📝 **Assignments:** {len(deadlines_list)} ({dated_deadlines} dated)")

        col_sync, col_disc = st.columns(2)
        with col_sync:
            if st.button("🔄 Sync", use_container_width=True):
                with st.spinner("Syncing courses and coursework..."):
                    sync_ok, sync_msg = sync_classroom_data()
                    if sync_ok:
                        st.success(sync_msg)
                        st.rerun()
                    else:
                        st.error(sync_msg)

        with col_disc:
            if st.button("🔓 Disconnect", use_container_width=True):
                clear_classroom_session()
                st.info("Disconnected from Google Classroom.")
                st.rerun()
    else:
        st.warning("Status: ● Not connected")

        oauth_configured = bool(get_oauth_client_config())
        if not oauth_configured:
            st.caption("⚠️ OAuth credentials not configured in secrets.toml (see CLASSROOM_SETUP.md).")

        if st.button("🎓 Connect Google Classroom", use_container_width=True):
            with st.spinner("Opening Google OAuth authorization..."):
                auth_ok, creds, auth_msg = authenticate_google_classroom()
                if auth_ok and creds:
                    st.session_state.classroom_credentials = creds
                    st.session_state.classroom_connected = True
                    # Auto-sync on first connection
                    sync_ok, sync_msg = sync_classroom_data()
                    st.success("✅ Google Classroom connected and synced!")
                    st.rerun()
                else:
                    st.error(auth_msg)

    st.divider()

    # 2. Gemini System Status & Diagnostic
    st.subheader("🤖 Gemini API")
    api_key = get_gemini_api_key()

    if api_key:
        st.success("Gemini credential: Configured")
        st.caption(f"Credential length: {len(api_key)} characters")
    else:
        st.error("Gemini credential: Missing")

    if st.button("🔌 Test Gemini Connection", use_container_width=True):
        with st.spinner("Testing connection to Gemini API..."):
            success, result = test_gemini_connection()

        if success:
            st.success("✅ Gemini connection successful!")
            st.write(result)
        else:
            if result == "API_KEY_INVALID":
                st.error(
                    "❌ Gemini rejected the configured credential.\n\n"
                    "Replace GEMINI_API_KEY in the deployed Streamlit Secrets."
                )
            elif result == "PERMISSION_DENIED":
                st.error("❌ Permission denied: The credential does not have access to this API.")
            elif result == "RESOURCE_EXHAUSTED":
                st.error("❌ Quota exceeded: Rate limit or quota exhausted.")
            elif result == "NOT_FOUND":
                st.error(f"❌ Model not found: '{MODEL_NAME}' is not available for this key.")
            else:
                st.error(f"❌ Gemini connection error: {result}")

    # 3. Active Student Profile & Reset
    if st.session_state.get("onboarded"):
        st.divider()
        st.write(f"👤 **Student:** {st.session_state.get('name', 'N/A')}")
        st.write(f"📧 **Email:** `{st.session_state.get('email', 'N/A')}`")

        if st.button("🔄 Reset Session", use_container_width=True):
            for key in ["onboarded", "name", "email", "chat", "messages"]:
                if key in st.session_state:
                    del st.session_state[key]
            clear_classroom_session()
            st.rerun()


# ==========================================
# ONBOARDING SCREEN (No Gemini Calls)
# ==========================================
if "onboarded" not in st.session_state:
    st.title("📅 AI Deadline Tracker")

    st.caption("Upload it or sync Google Classroom. Extract deadlines. Email yourself the results.")

    with st.form("onboarding_form"):
        name = st.text_input("Your name")

        email = st.text_input(
            "Email address",
            placeholder="student@example.com",
            help="This is the email address where your deadline digest will be sent.",
        )

        submitted = st.form_submit_button("Let's get started 🚀")

    if submitted:
        if not name.strip() or not email.strip():
            st.warning("Please fill in both your name and email address.")
        else:
            st.session_state.name = name.strip()
            st.session_state.email = email.strip()
            st.session_state.messages = []
            st.session_state.onboarded = True

            st.rerun()

    st.stop()


# ==========================================
# MAIN INTERACTION INTERFACE
# ==========================================
header_col, button_col = st.columns(
    [5, 2],
    vertical_alignment="center",
)

with header_col:
    st.title("📅 AI Deadline Tracker")

with button_col:
    has_chat_messages = len(st.session_state.get("messages", [])) > 1
    has_classroom_deadlines = bool(st.session_state.get("classroom_deadlines"))
    send_disabled = not (has_chat_messages or has_classroom_deadlines)

    if st.button(
        "📧 Send Deadline Digest",
        disabled=send_disabled,
        use_container_width=True,
    ):
        with st.spinner("Preparing your unified deadline digest..."):
            classroom_deadlines = st.session_state.get("classroom_deadlines", [])
            classroom_text = format_classroom_deadlines_for_gemini(classroom_deadlines)

            digest_prompt = (
                f"{SUMMARY_REQUEST_PROMPT}\n\n"
                "Combine both the uploaded academic document deadlines from the conversation "
                "AND the following Google Classroom deadlines into one clean, organized email digest:\n\n"
                f"{classroom_text}\n\n"
                "Format clearly with separate sections for 'Google Classroom' and 'Uploaded Documents' if both exist. "
                "Do not duplicate identical items."
            )

            summary = ask_gemini([digest_prompt])

        success, info = send_email(
            st.session_state.get("email", ""),
            st.session_state.get("name", "Student"),
            summary,
        )

        if success:
            st.success("Sent! Check your email 📧")
        else:
            st.error(f"Couldn't send the email: {info}")


st.caption(
    f"Logged in as **{st.session_state.get('name', 'Student')}** — "
    f"Deadline digests will be emailed to `{st.session_state.get('email', '')}`"
)


# Display Live Classroom Deadlines Card if synced
classroom_deadlines = st.session_state.get("classroom_deadlines", [])
if classroom_deadlines:
    with st.expander(f"🎓 Synchronized Google Classroom Assignments ({len(classroom_deadlines)} items)", expanded=False):
        dated_items = [d for d in classroom_deadlines if d.get("has_due_date")]
        undated_items = [d for d in classroom_deadlines if not d.get("has_due_date")]

        if dated_items:
            st.markdown("#### 📅 Upcoming Due Dates")
            for item in dated_items:
                time_info = f" at {item['due_time']}" if item['due_time'] != "Not specified" else ""
                link_btn = f"[Open in Classroom ↗]({item['url']})" if item.get("url") else ""
                st.markdown(
                    f"- 📘 **{item['course']}** — **{item['task']}**  \n"
                    f"  ⏰ *Due: {item['due_date']}{time_info}* | 🏷️ `Google Classroom` {link_btn}"
                )

        if undated_items:
            st.markdown("#### 📋 Assignments Without Due Dates")
            for item in undated_items:
                link_btn = f"[Open ↗]({item['url']})" if item.get("url") else ""
                st.markdown(f"- 📄 **{item['course']}**: {item['task']} {link_btn}")


# Display Chat Conversation
if not st.session_state.get("messages", []):
    add_message(
        "assistant",
        "text",
        WELCOME_MESSAGE_TEMPLATE.format(name=st.session_state.get("name", "Student")),
    )
else:
    for message in st.session_state.get("messages", []):
        render_message(message)


user_input = st.chat_input(
    "Ask about your deadlines, or attach an academic document (syllabus, notice, timetable)",
    accept_file=True,
    file_type=["jpg", "jpeg", "png"],
)


if user_input:
    document = user_input.files[0] if user_input.files else None
    text = user_input.text

    parts = []

    if document is not None:
        document_bytes = document.getvalue()

        add_message("user", "image", document_bytes)

        parts.append(
            types.Part.from_bytes(
                data=document_bytes,
                mime_type=document.type,
            )
        )

    if text:
        add_message("user", "text", text)
        parts.append(text)

    elif document is not None:
        parts.append(
            "Analyze this academic document and extract all "
            "clearly identifiable deadlines, dates, assignments, "
            "exams, and important academic tasks. "
            "Do not invent missing information."
        )

    with st.spinner("Analyzing your academic document..."):
        answer = ask_gemini(parts)

    add_message("assistant", "text", answer)
