import os
import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SENDER_EMAIL = os.getenv("MAIL_ID")


def _get_gmail_service():
    """Builds an authenticated Gmail API service using OAuth2 refresh token."""
    client_id = os.getenv("GMAIL_CLIENT_ID")
    client_secret = os.getenv("GMAIL_CLIENT_SECRET")
    refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        raise ValueError(
            "Gmail credentials missing. Set GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, "
            "and GMAIL_REFRESH_TOKEN in your .env file."
        )

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)


async def save_as_draft(to: str, subject: str, body: str) -> str:
    """
    Creates a Gmail draft (does NOT send). Returns the Gmail draft ID.
    
    You review the draft in Gmail, then hit Send yourself.
    The draft ID is stored in the DB so you can match it back to the job.

    Args:
        to: Recipient email address
        subject: Email subject line
        body: Plain-text email body

    Returns:
        Gmail draft ID string (e.g. "r-12345678")
    
    Raises:
        Exception if Gmail API call fails
    """
    service = _get_gmail_service()

    # Build MIME message
    message = MIMEMultipart("alternative")
    message["to"] = to
    message["from"] = SENDER_EMAIL
    message["subject"] = subject

    # Plain text part
    text_part = MIMEText(body, "plain")
    message.attach(text_part)

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()

    draft_id = draft["id"]
    logger.info(f"Gmail draft saved: {draft_id} -> {to} | {subject}")
    return draft_id
