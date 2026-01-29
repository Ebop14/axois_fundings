"""Gmail API client for fetching newsletters and creating drafts."""

import base64
import logging
import os
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailClient:
    """Client for interacting with Gmail API."""

    def __init__(
        self,
        credentials_file: str = "credentials/credentials.json",
        token_file: str = "credentials/token.json",
    ):
        self.credentials_file = Path(credentials_file)
        self.token_file = Path(token_file)
        self.service = None
        self._authenticate()

    def _authenticate(self) -> None:
        """Authenticate with Gmail API using OAuth2."""
        creds = None

        if self.token_file.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_file), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired credentials")
                creds.refresh(Request())
            else:
                if not self.credentials_file.exists():
                    raise FileNotFoundError(
                        f"Credentials file not found: {self.credentials_file}\n"
                        "Download OAuth2 credentials from Google Cloud Console."
                    )
                logger.info("Starting OAuth2 flow - browser will open")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_file), SCOPES
                )
                creds = flow.run_local_server(port=0)

            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())
            logger.info(f"Credentials saved to {self.token_file}")

        self.service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail API authenticated successfully")

    def get_or_create_label(self, label_name: str) -> str:
        """Get label ID, creating the label if it doesn't exist."""
        try:
            results = self.service.users().labels().list(userId="me").execute()
            labels = results.get("labels", [])

            for label in labels:
                if label["name"] == label_name:
                    return label["id"]

            label_body = {
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            }
            created = (
                self.service.users()
                .labels()
                .create(userId="me", body=label_body)
                .execute()
            )
            logger.info(f"Created label: {label_name}")
            return created["id"]

        except HttpError as e:
            logger.error(f"Error managing labels: {e}")
            raise

    def fetch_axios_emails(
        self,
        sender_filter: str = "axios.com",
        processed_label: str = "Axios-Processed",
        max_results: int = 10,
    ) -> list[dict]:
        """Fetch unread Axios Pro Rata emails that haven't been processed."""
        try:
            processed_label_id = self.get_or_create_label(processed_label)

            query = f"from:{sender_filter} is:unread -label:{processed_label}"
            logger.info(f"Searching with query: {query}")

            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute()
            )

            messages = results.get("messages", [])
            logger.info(f"Found {len(messages)} unprocessed Axios emails")

            emails = []
            for msg in messages:
                email_data = self._get_email_content(msg["id"])
                if email_data:
                    email_data["label_id"] = processed_label_id
                    emails.append(email_data)

            return emails

        except HttpError as e:
            logger.error(f"Error fetching emails: {e}")
            raise

    def _get_email_content(self, message_id: str) -> Optional[dict]:
        """Get full email content including headers and body."""
        try:
            message = (
                self.service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )

            headers = message.get("payload", {}).get("headers", [])
            subject = next(
                (h["value"] for h in headers if h["name"].lower() == "subject"), ""
            )
            from_header = next(
                (h["value"] for h in headers if h["name"].lower() == "from"), ""
            )
            date = next(
                (h["value"] for h in headers if h["name"].lower() == "date"), ""
            )

            body_html = ""
            body_text = ""
            self._extract_body(message.get("payload", {}), body_html, body_text)

            payload = message.get("payload", {})
            body_html, body_text = self._extract_body_recursive(payload)

            return {
                "id": message_id,
                "subject": subject,
                "from": from_header,
                "date": date,
                "body_html": body_html,
                "body_text": body_text,
            }

        except HttpError as e:
            logger.error(f"Error getting email content: {e}")
            return None

    def _extract_body_recursive(
        self, payload: dict
    ) -> tuple[str, str]:
        """Recursively extract HTML and plain text body from email payload."""
        body_html = ""
        body_text = ""

        mime_type = payload.get("mimeType", "")
        body = payload.get("body", {})
        data = body.get("data", "")

        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            if "html" in mime_type:
                body_html = decoded
            elif "plain" in mime_type:
                body_text = decoded

        for part in payload.get("parts", []):
            html, text = self._extract_body_recursive(part)
            if html:
                body_html = html
            if text:
                body_text = text

        return body_html, body_text

    def _extract_body(self, payload: dict, body_html: str, body_text: str) -> None:
        """Legacy method - use _extract_body_recursive instead."""
        pass

    def mark_as_processed(self, message_id: str, label_id: str) -> None:
        """Add processed label to an email."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            logger.info(f"Marked message {message_id} as processed")

        except HttpError as e:
            logger.error(f"Error marking email as processed: {e}")
            raise

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        html: bool = False,
    ) -> dict:
        """Create a draft email in Gmail."""
        try:
            message = MIMEText(body, "html" if html else "plain")
            message["to"] = to
            message["subject"] = subject

            encoded = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            draft_body = {"message": {"raw": encoded}}

            draft = (
                self.service.users()
                .drafts()
                .create(userId="me", body=draft_body)
                .execute()
            )
            logger.info(f"Created draft for {to}: {subject}")
            return draft

        except HttpError as e:
            logger.error(f"Error creating draft: {e}")
            raise
