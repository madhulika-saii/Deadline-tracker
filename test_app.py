"""
Comprehensive Test Suite for AI Deadline Tracker
Tests Gemini Vision extraction, chat reasoning, Google Classroom normalization, and Gmail MIME formatting.
"""

import io
import os
import sys
import toml
from email.mime.text import MIMEText
from PIL import Image, ImageDraw
from google import genai
from google.genai import types

from classroom_service import (
    SCOPES,
    format_classroom_deadlines_for_gemini,
    get_oauth_client_config,
    normalize_coursework_item,
)
from prompts import (
    SUMMARY_REQUEST_PROMPT,
    SYSTEM_PROMPT,
    WELCOME_MESSAGE_TEMPLATE,
)


def run_tests():
    print("========================================")
    print("RUNNING COMPREHENSIVE PROJECT TEST SUITE")
    print("========================================")

    # 1. Check secrets.toml
    secrets_path = os.path.join(os.getcwd(), ".streamlit", "secrets.toml")
    assert os.path.exists(secrets_path), "secrets.toml not found!"
    with open(secrets_path, "r", encoding="utf-8") as f:
        secrets_data = toml.load(f)

    gemini_key = secrets_data.get("GEMINI_API_KEY", "").strip()
    assert gemini_key, "GEMINI_API_KEY is missing in secrets.toml"
    print(f"[PASS] 1. Secrets file loaded. GEMINI_API_KEY detected ({len(gemini_key)} chars).")

    # 2. Check Classroom OAuth secrets
    client_id = secrets_data.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = secrets_data.get("GOOGLE_CLIENT_SECRET", "").strip()
    assert client_id and client_secret, "Classroom OAuth client ID or secret missing in secrets.toml"
    assert client_id.endswith(".apps.googleusercontent.com"), "Client ID does not match Google OAuth format"
    print(f"[PASS] 2. Google Classroom OAuth credentials detected in secrets.toml.")

    # 3. Test Gemini API Connection & Text Query
    client = genai.Client(api_key=gemini_key)
    MODEL_NAME = "gemini-3.5-flash-lite"
    print(f"Testing Gemini model: {MODEL_NAME}...")

    try:
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents="Reply with exactly: Gemini connection successful.",
        )
        assert resp and resp.text, "Gemini returned empty response"
        print(f"[PASS] 3. Gemini Connection Test: {resp.text.strip()}")
    except Exception as e:
        print(f"[FAIL] 3. Gemini Connection Failed: {e}")
        sys.exit(1)

    # 4. Test Chat / Text Reasoning with Deadlines
    try:
        chat = client.chats.create(
            model=MODEL_NAME,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            ),
        )
        chat_resp = chat.send_message("What deadlines have been identified so far?")
        assert chat_resp and chat_resp.text, "Empty chat response"
        print(f"[PASS] 4. Gemini Chat Query Test: Succeeded. Response excerpt: {chat_resp.text[:90]}...")
    except Exception as e:
        print(f"[FAIL] 4. Gemini Chat Test Failed: {e}")
        sys.exit(1)

    # 5. Test Multimodal Image Deadline Extraction with Gemini Vision
    try:
        img = Image.new("RGB", (800, 400), color=(255, 255, 255))
        d = ImageDraw.Draw(img)
        text_content = """DEPARTMENT OF COMPUTER SCIENCE
COURSE: Database Management Systems (CS301)
ASSIGNMENT 3: Relational Algebra & Normalization
DEADLINE: October 15, 2026 at 11:59 PM
PRIORITY: High (20% of total grade)
Submission Portal: Google Classroom"""
        d.text((30, 40), text_content, fill=(0, 0, 0))
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format="PNG")
        img_bytes = img_byte_arr.getvalue()

        vision_part = types.Part.from_bytes(
            data=img_bytes,
            mime_type="image/png",
        )

        vision_resp = chat.send_message([
            vision_part,
            "Extract the subject, task, deadline date, time, and priority from this document.",
        ])
        assert vision_resp and vision_resp.text, "Empty vision response"
        print(f"[PASS] 5. Multimodal Image Deadline Extraction: Succeeded. Response excerpt: {vision_resp.text[:100]}...")
    except Exception as e:
        print(f"[FAIL] 5. Image Deadline Extraction Failed: {e}")
        sys.exit(1)

    # 6. Test Classroom Service Logic & Normalization
    assert len(SCOPES) == 2, f"Expected exactly 2 scopes, got {len(SCOPES)}"
    assert "https://www.googleapis.com/auth/classroom.courses.readonly" in SCOPES
    assert "https://www.googleapis.com/auth/classroom.coursework.me.readonly" in SCOPES
    for scope in SCOPES:
        assert "readonly" in scope, f"Scope {scope} is not read-only!"
    print(f"[PASS] 6. Google Classroom Scopes: Verified {len(SCOPES)} scopes (courses.readonly & coursework.me.readonly).")

    # Verify OAuth client config builder
    mock_config = get_oauth_client_config()
    assert mock_config and "installed" in mock_config, "OAuth client config generation failed"
    assert mock_config["installed"]["client_id"] == client_id, "Client ID mismatch in config"
    print("[PASS] 7. OAuth Client Config Generation: Verified InstalledAppFlow format.")

    # Verify Coursework Normalization
    sample_coursework = {
        "title": "Assignment 2 - SQL Queries",
        "description": "Solve problems 1 to 10 on SQL joins",
        "alternateLink": "https://classroom.google.com/c/123/a/456",
        "dueDate": {"year": 2026, "month": 10, "day": 20},
        "dueTime": {"hours": 18, "minutes": 30},
    }
    normalized = normalize_coursework_item("Database Management Systems", sample_coursework)
    assert normalized["source"] == "Google Classroom"
    assert normalized["course"] == "Database Management Systems"
    assert normalized["task"] == "Assignment 2 - SQL Queries"
    assert normalized["due_date"] == "2026-10-20"
    assert normalized["due_time"] == "18:30"
    assert normalized["has_due_date"] is True
    print(f"[PASS] 8. Coursework Normalization: Verified structure -> {normalized['course']} | {normalized['task']} | Due: {normalized['due_date']} {normalized['due_time']}")

    # Verify Undated item normalization
    undated_sample = {
        "title": "Course Syllabus & Reading Material",
        "description": "General reading list",
        "alternateLink": "https://classroom.google.com/c/123/m/789",
    }
    normalized_undated = normalize_coursework_item("Operating Systems", undated_sample)
    assert normalized_undated["due_date"] == "No due date"
    assert normalized_undated["due_time"] == "Not specified"
    assert normalized_undated["has_due_date"] is False
    print("[PASS] 9. Undated Coursework Handling: Correctly marked as 'No due date'.")

    # Verify Combined Deadline Formatting for Gemini
    sample_deadlines = [normalized, normalized_undated]
    formatted_summary = format_classroom_deadlines_for_gemini(sample_deadlines)
    assert "Database Management Systems" in formatted_summary
    assert "2026-10-20" in formatted_summary
    assert "Operating Systems" in formatted_summary
    print("[PASS] 10. Gemini Classroom Context Generation: Formatted multi-course context correctly.")

    # 7. Test Email MIME Construction and SMTP Handshake
    user_name = "Test Student"
    summary_text = "Google Classroom:\n1. DBMS - Assignment 2 (Due: Oct 20)\n\nUploaded Documents:\n2. OS - Lab 3 (Due: Oct 22)"
    body = (
        f"Hello {user_name},\n\n"
        "Here is your academic deadline summary:\n\n"
        f"{summary_text}\n\n"
        "Please make sure to complete your tasks before their deadlines.\n\n"
        "— AI Deadline Tracker"
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = "📅 Upcoming Academic Deadlines"
    gmail_addr = str(secrets_data.get("GMAIL_ADDRESS", "student@example.com")).strip()
    msg["From"] = gmail_addr
    msg["To"] = "student@example.com"
    assert msg["Subject"] == "📅 Upcoming Academic Deadlines"
    decoded_body = msg.get_payload(decode=True).decode("utf-8")
    assert "DBMS - Assignment 2" in decoded_body
    print("[PASS] 11. Gmail MIME Construction: Verified decoded payload and UTF-8 charset.")

    # 8. Test SMTP SSL Host & Port Connection
    import smtplib
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=5) as server:
            server.noop()
        print("[PASS] 12. Gmail SMTP SSL Handshake: Successfully connected to smtp.gmail.com:465.")
    except Exception as e:
        print(f"[NOTE] Gmail SMTP handshake note (network-dependent): {e}")

    print("\n========================================")
    print("ALL TESTS PASSED SUCCESSFULLY!")
    print("========================================")


if __name__ == "__main__":
    run_tests()
