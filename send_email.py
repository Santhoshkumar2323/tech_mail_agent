"""
send_email.py
Module 4 — Builds the MIME email (audio card at top, written report below)
and sends it individually to each recipient (not BCC), so:
  - each message looks like a normal 1-to-1 email to spam filters
  - one bad/bouncing address doesn't affect delivery to anyone else

Credentials and recipient list come from environment variables
(GitHub Actions secrets), never hardcoded or committed.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio


def build_html_report(items: list[dict]) -> str:
    """
    Builds the structured written portion of the email: title, score,
    summary, and a clickable link, per item.
    """
    rows = []
    for item in items:
        rows.append(f"""
        <div style="margin-bottom:20px;padding:14px;border-left:3px solid #444;">
            <div style="font-weight:bold;font-size:15px;">{item['title']}</div>
            <div style="color:#666;font-size:13px;margin:4px 0;">
                Score: {item['score']}/10 &nbsp;|&nbsp; Source: {item['source'].upper()}
            </div>
            <div style="font-size:14px;margin-bottom:6px;">{item['reasoning']}</div>
            <a href="{item['url']}" style="font-size:13px;">🔗 View source</a>
        </div>
        """)

    return f"""
    <html>
    <body style="font-family:Arial,sans-serif;max-width:640px;margin:auto;">
        <h2>🤖 Deep-Tech Briefing</h2>
        {''.join(rows)}
    </body>
    </html>
    """


def send_briefing(
    recipients: list[str],
    subject: str,
    sender_name: str,
    html_body: str,
    audio_path: str | None,
    smtp_server: str,
    smtp_port: int,
) -> None:
    """
    Sends the briefing individually to each recipient. Logs (doesn't raise)
    per-recipient failures so one bad address doesn't kill the whole batch.
    """
    sender_email = os.environ["SMTP_USERNAME"]
    sender_password = os.environ["SMTP_PASSWORD"]

    audio_bytes = None
    if audio_path and os.path.exists(audio_path):
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        server.starttls()
        server.login(sender_email, sender_password)

        for recipient in recipients:
            try:
                msg = MIMEMultipart("mixed")
                msg["Subject"] = subject
                msg["From"] = f"{sender_name} <{sender_email}>"
                msg["To"] = recipient

                # Audio attached first so it renders as a playable card near the top
                if audio_bytes:
                    audio_part = MIMEAudio(audio_bytes, _subtype="mp3")
                    audio_part.add_header("Content-Disposition", "inline", filename="briefing.mp3")
                    msg.attach(audio_part)

                msg.attach(MIMEText(html_body, "html"))

                server.sendmail(sender_email, recipient, msg.as_string())
                print(f"[send_email] Sent to {recipient}")

            except Exception as e:
                print(f"[send_email] FAILED to send to {recipient}: {e}")
                continue


def get_recipients_from_env() -> list[str]:
    """
    Recipient list comes from a comma-separated env var (GitHub Actions secret),
    e.g. RECIPIENT_LIST="a@example.com,b@example.com"
    """
    raw = os.environ.get("RECIPIENT_LIST", "")
    return [r.strip() for r in raw.split(",") if r.strip()]