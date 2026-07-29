import os
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.audio import MIMEAudio


def clean_latex(text: str) -> str:
    if not text:
        return text
    text = re.sub(r"\\math(bf|rm|cal|bb|it)\{([^}]*)\}", r"\2", text)
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)


    greek = {
        "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
        "epsilon": "epsilon", "theta": "theta", "lambda": "lambda",
        "pi": "pi", "sigma": "sigma", "omega": "omega", "mu": "mu",
    }
    for name, replacement in greek.items():
        text = re.sub(rf"\\{name}\b", replacement, text)

    text = re.sub(r"\^(\{[^}]*\}|\w)", lambda m: m.group(1).strip("{}"), text)
    text = re.sub(r"_(\{[^}]*\}|\w)", lambda m: m.group(1).strip("{}"), text)
    text = text.replace("$", "")

    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)

    return text.strip()


def clean_item(item: dict) -> dict:
    cleaned = dict(item)
    cleaned["title"] = clean_latex(item.get("title", ""))
    cleaned["reasoning"] = clean_latex(item.get("reasoning", ""))
    return cleaned

def build_html_report(items: list[dict]) -> str:
    items = [clean_item(i) for i in items]

    ACCENT = "#2563eb"
    rows = []
    for item in items:
        rows.append(f"""
        <tr>
          <td style="padding:0 0 20px 0;">
            <table role="presentation" width="100%" style="border-collapse:collapse;">
              <tr>
                <td style="border-left:3px solid {ACCENT};padding:12px 16px;">
                  <div style="font-weight:600;font-size:16px;color:#111;line-height:1.4;">
                    {item['title']}
                  </div>
                  <div style="font-size:12px;color:#888;margin:6px 0 8px 0;letter-spacing:0.02em;">
                    SCORE {item['score']}/10 &nbsp;&middot;&nbsp; {item['source'].upper()}
                  </div>
                  <div style="font-size:14px;color:#333;line-height:1.5;margin-bottom:10px;">
                    {item['reasoning']}
                  </div>
                  <a href="{item['url']}" style="font-size:13px;color:{ACCENT};text-decoration:none;font-weight:500;">
                    View source &rarr;
                  </a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        """)

    return f"""
    <html>
    <body style="margin:0;padding:0;background-color:#f5f5f7;font-family:-apple-system,Segoe UI,Arial,sans-serif;">
      <table role="presentation" width="100%" style="background-color:#f5f5f7;padding:24px 0;">
        <tr>
          <td align="center">
            <table role="presentation" width="600" style="background-color:#ffffff;border-radius:8px;overflow:hidden;">
              <tr>
                <td style="background-color:#111827;padding:24px 28px;">
                  <span style="font-size:20px;color:#ffffff;font-weight:600;">
                    🤖 Deep-Tech Briefing
                  </span>
                </td>
              </tr>
              <tr>
                <td style="padding:24px 28px 8px 28px;">
                  <table role="presentation" width="100%">
                    {''.join(rows)}
                  </table>
                </td>
              </tr>
              <tr>
                <td style="padding:16px 28px 24px 28px;border-top:1px solid #eee;">
                  <span style="font-size:12px;color:#999;">
                    Autonomous Tech Scout &mdash; sent every 3 days
                  </span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def build_plain_text_report(items: list[dict]) -> str:
    items = [clean_item(i) for i in items]

    lines = ["DEEP-TECH BRIEFING", "=" * 40, ""]
    for item in items:
        lines.append(item["title"])
        lines.append(f"Score: {item['score']}/10 | Source: {item['source'].upper()}")
        lines.append(item["reasoning"])
        lines.append(f"Link: {item['url']}")
        lines.append("-" * 40)
        lines.append("")

    lines.append("Autonomous Tech Scout — sent every 3 days")
    return "\n".join(lines)


def send_briefing(
    recipients: list[str],
    subject: str,
    sender_name: str,
    html_body: str,
    plain_body: str,
    audio_path: str | None,
    smtp_server: str,
    smtp_port: int,
) -> None:
    """
    Sends the briefing individually to each recipient. Logs (doesn't raise)
    per-recipient failures so one bad address doesn't kill the whole batch.

    MIME structure per message:
      mixed
        alternative
          text/plain
          text/html
        audio (attachment, if available)
    """
    sender_email = os.environ["SMTP_USERNAME"]
    sender_password = os.environ["SMTP_PASSWORD"]

    subject = clean_latex(subject)

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

                alt_part = MIMEMultipart("alternative")
                alt_part.attach(MIMEText(plain_body, "plain"))
                alt_part.attach(MIMEText(html_body, "html"))
                msg.attach(alt_part)

                if audio_bytes:
                    audio_part = MIMEAudio(audio_bytes, _subtype="mp3")
                    audio_part.add_header("Content-Disposition", "inline", filename="briefing.mp3")
                    msg.attach(audio_part)

                server.sendmail(sender_email, recipient, msg.as_string())
                print(f"[send_email] Sent to {recipient}")

            except Exception as e:
                print(f"[send_email] FAILED to send to {recipient}: {e}")
                continue


def get_recipients_from_env() -> list[str]:
    raw = os.environ.get("RECIPIENT_LIST", "")
    return [r.strip() for r in raw.split(",") if r.strip()]