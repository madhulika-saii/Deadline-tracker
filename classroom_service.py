"""
Google Classroom Service Module for AI Deadline Tracker
Handles OAuth 2.0 authentication, course discovery, coursework retrieval,
deadline normalization, and session management.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import streamlit as st

# Relax token scope check to handle Google's scope normalization gracefully
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

# Read-only Classroom scopes
SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
]


def get_oauth_client_config() -> Optional[Dict[str, Any]]:
    """
    Retrieves Google OAuth client configuration from Streamlit secrets,
    environment variables, or a local credentials.json file.
    Returns a dict suitable for InstalledAppFlow.from_client_config.
    """
    # 1. Check Streamlit secrets for direct Client ID & Secret
    client_id = st.secrets.get("GOOGLE_CLIENT_ID", "").strip() or os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = st.secrets.get("GOOGLE_CLIENT_SECRET", "").strip() or os.getenv("GOOGLE_CLIENT_SECRET", "").strip()

    if client_id and client_secret:
        return {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["http://localhost", "http://localhost:8501", "urn:ietf:wg:oauth:2.0:oob"],
            }
        }

    # 2. Check Streamlit secrets for complete client config JSON string or dict
    if "GOOGLE_OAUTH_CLIENT_CONFIG" in st.secrets:
        raw_config = st.secrets["GOOGLE_OAUTH_CLIENT_CONFIG"]
        if isinstance(raw_config, dict):
            return raw_config
        try:
            return json.loads(raw_config)
        except Exception:
            pass

    # 3. Check for local credentials.json file (local dev only)
    if os.path.exists("credentials.json"):
        try:
            with open("credentials.json", "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return None


def authenticate_google_classroom() -> Tuple[bool, Optional[Credentials], str]:
    """
    Executes the OAuth 2.0 flow for Google Classroom.
    Returns (success, credentials, message).
    """
    client_config = get_oauth_client_config()
    if not client_config:
        return (
            False,
            None,
            "Google Classroom OAuth credentials are not configured. "
            "Please add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to Streamlit secrets.",
        )

    try:
        # Determine flow type (installed vs web)
        flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
        
        # Run local server flow for authentication
        credentials = flow.run_local_server(
            port=0,
            prompt="consent",
            access_type="offline",
            authorization_prompt_message="Please complete Google Classroom authorization in the browser window.",
        )

        return True, credentials, "Successfully connected to Google Classroom!"
    except Exception as error:
        error_msg = str(error)
        if "access_denied" in error_msg.lower():
            return False, None, "Google Classroom authorization was cancelled by the user."
        return False, None, f"Google Classroom authentication failed: {error_msg}"


def build_classroom_service(credentials: Credentials):
    """Builds and returns the Google Classroom API v1 client service."""
    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception:
            pass
    return build("classroom", "v1", credentials=credentials)


def get_courses(service) -> Tuple[bool, List[Dict[str, Any]], str]:
    """
    Fetches the user's active Google Classroom courses.
    Returns (success, courses_list, message).
    """
    try:
        courses = []
        page_token = None

        while True:
            # First try listing as student
            try:
                response = service.courses().list(
                    studentId="me",
                    courseStates=["ACTIVE"],
                    pageToken=page_token,
                    pageSize=50,
                ).execute()
            except HttpError as http_err:
                # Fallback to general list if studentId filter is restricted
                if http_err.resp.status in (400, 403):
                    response = service.courses().list(
                        courseStates=["ACTIVE"],
                        pageToken=page_token,
                        pageSize=50,
                    ).execute()
                else:
                    raise http_err

            courses.extend(response.get("courses", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        if not courses:
            return True, [], "No Google Classroom courses were found."

        return True, courses, f"Found {len(courses)} active course(s)."
    except HttpError as error:
        status_code = error.resp.status
        if status_code == 403:
            return (
                False,
                [],
                "Google Classroom did not allow access to this information. "
                "Please verify that the Google Classroom API is enabled and you authorized the correct account.",
            )
        elif status_code == 404:
            return False, [], "No Google Classroom courses were found."
        return False, [], f"Google Classroom API error ({status_code}): {error._get_reason()}"
    except Exception as error:
        return False, [], f"Failed to retrieve courses: {str(error)}"


def get_coursework(service, course_id: str, course_name: str) -> List[Dict[str, Any]]:
    """
    Fetches coursework items/assignments for a specific course.
    """
    coursework_items = []
    page_token = None

    try:
        while True:
            response = service.courses().courseWork().list(
                courseId=course_id,
                courseWorkStates=["PUBLISHED"],
                pageToken=page_token,
                pageSize=50,
            ).execute()

            for item in response.get("courseWork", []):
                normalized = normalize_coursework_item(course_name, item)
                coursework_items.append(normalized)

            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception:
        # Gracefully handle course-level permission or access restrictions
        pass

    return coursework_items


def normalize_coursework_item(course_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """
    Converts a Google Classroom CourseWork resource into the standardized deadline structure.
    """
    title = item.get("title", "Untitled Assignment").strip()
    description = item.get("description", "").strip()
    alternate_link = item.get("alternateLink", "")

    due_date_obj = item.get("dueDate")
    due_time_obj = item.get("dueTime")

    formatted_date = "No due date"
    formatted_time = "Not specified"
    has_due_date = False
    raw_datetime_sort_key = "9999-99-99 99:99"

    if due_date_obj:
        year = due_date_obj.get("year")
        month = due_date_obj.get("month", 1)
        day = due_date_obj.get("day", 1)

        if year and month and day:
            formatted_date = f"{year:04d}-{month:02d}-{day:02d}"
            has_due_date = True

            hours = due_time_obj.get("hours", 23) if due_time_obj else 23
            minutes = due_time_obj.get("minutes", 59) if due_time_obj else 59
            formatted_time = f"{hours:02d}:{minutes:02d}"

            raw_datetime_sort_key = f"{formatted_date} {formatted_time}"

    return {
        "source": "Google Classroom",
        "course": course_name,
        "task": title,
        "description": description,
        "due_date": formatted_date,
        "due_time": formatted_time,
        "priority": "Not specified",
        "url": alternate_link,
        "has_due_date": has_due_date,
        "sort_key": raw_datetime_sort_key,
    }


def get_all_classroom_deadlines(service, courses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Iterates through all courses and aggregates normalized coursework deadlines.
    Sorts them chronologically.
    """
    all_deadlines = []

    for course in courses:
        course_id = course.get("id")
        course_name = course.get("name", "Unnamed Course")
        if course_id:
            items = get_coursework(service, course_id, course_name)
            all_deadlines.extend(items)

    # Sort: Dated items first (chronologically), then items with no due date
    all_deadlines.sort(key=lambda x: (not x["has_due_date"], x["sort_key"]))
    return all_deadlines


def format_classroom_deadlines_for_gemini(deadlines: List[Dict[str, Any]]) -> str:
    """
    Formats the list of Classroom deadlines into clear structured context for Gemini AI.
    """
    if not deadlines:
        return "No Google Classroom assignments or deadlines currently synced."

    dated_items = [d for d in deadlines if d.get("has_due_date")]
    undated_items = [d for d in deadlines if not d.get("has_due_date")]

    lines = ["### Live Synchronized Google Classroom Deadlines:"]

    if dated_items:
        lines.append("\n**Upcoming Deadlines:**")
        for idx, d in enumerate(dated_items, 1):
            time_str = f" at {d['due_time']}" if d['due_time'] != "Not specified" else ""
            lines.append(f"{idx}. **{d['course']}** — {d['task']}")
            lines.append(f"   - **Due Date:** {d['due_date']}{time_str}")
            if d.get("description"):
                brief_desc = (d['description'][:120] + "...") if len(d['description']) > 120 else d['description']
                lines.append(f"   - **Details:** {brief_desc}")

    if undated_items:
        lines.append(f"\n**Coursework Without Due Dates ({len(undated_items)} items):**")
        for d in undated_items[:10]:  # Limit to 10 for prompt efficiency
            lines.append(f"- **{d['course']}**: {d['task']} (No due date)")

    return "\n".join(lines)


def clear_classroom_session():
    """Clears all Classroom-related information from Streamlit session state."""
    keys_to_clear = [
        "classroom_connected",
        "classroom_credentials",
        "classroom_courses",
        "classroom_deadlines",
        "classroom_sync_time",
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]
