"""
agent/emailer.py — Gmail SMTP Alert Sender
==========================================
Sends a nicely formatted HTML email listing new funding opportunities.

Set these environment variables (see .env.example):
  ALERT_EMAIL_FROM      your Gmail address
  ALERT_EMAIL_PASSWORD  your Gmail App Password (not your login password)
  ALERT_EMAIL_TO        comma-separated recipient email(s)

To create a Gmail App Password:
  Google Account → Security → 2-Step Verification → App Passwords
"""

import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from agent.config_agent import (
    EMAIL_FROM,
    EMAIL_PASSWORD,
    EMAIL_TO,
    SMTP_HOST,
    SMTP_PORT,
)

log = logging.getLogger(__name__)

# ── Templates ──────────────────────────────────────────────────────────────────

_OPP_CARD = """\
<div style="border:1px solid #ddd;border-radius:6px;padding:14px 18px;
            margin-bottom:16px;background:#fafafa;">
  <h3 style="margin:0 0 6px;font-size:15px;color:#1a1a2e;">
    <a href="{url}" style="color:#0077b6;text-decoration:none;">{title}</a>
  </h3>
  <p style="margin:0 0 4px;font-size:13px;color:#444;">
    <strong>Source:</strong> {source} &nbsp;|&nbsp;
    <strong>Agency/Funder:</strong> {agency}
  </p>
  {deadline_row}
  {amount_row}
  <p style="margin:6px 0 0;font-size:13px;color:#555;">{description}</p>
</div>
"""

_DEADLINE_ROW = '<p style="margin:0 0 4px;font-size:13px;color:#444;"><strong>Deadline:</strong> {}</p>'
_AMOUNT_ROW   = '<p style="margin:0 0 4px;font-size:13px;color:#444;"><strong>Award ceiling:</strong> {}</p>'

_HTML_BODY = """\
<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:760px;
margin:auto;color:#222;">
<h2 style="background:#0077b6;color:#fff;padding:14px 18px;border-radius:6px 6px 0 0;
           margin-bottom:0;">
  🌍 Global Health Funding Opportunities — {date}
</h2>
<div style="padding:16px;">
  <p style="color:#555;margin-top:4px;">
    Found <strong>{count}</strong> new funding {opp_word} across {source_count} source(s).
  </p>
  {cards}
  <hr style="border:none;border-top:1px solid #eee;margin-top:24px;">
  <p style="font-size:11px;color:#999;">
    Sent by Polycrise Sentinel · Global Health Funding Agent ·
    To change keywords or sources, update your <code>.env</code> file.
  </p>
</div>
</body></html>
"""


# ── Public API ─────────────────────────────────────────────────────────────────

def send_alert(opportunities: list[dict]) -> bool:
    """
    Compose and send an HTML alert email for `opportunities`.
    Returns True on success, False on failure.
    Each opportunity dict must have: id, title, url, source, agency.
    Optional keys: deadline, award_ceiling, description.
    """
    if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
        log.error(
            "Email credentials not configured. "
            "Set ALERT_EMAIL_FROM, ALERT_EMAIL_PASSWORD, ALERT_EMAIL_TO."
        )
        return False

    if not opportunities:
        log.info("No opportunities to send — skipping email.")
        return True

    cards_html = _build_cards(opportunities)
    sources = {o["source"] for o in opportunities}
    today = datetime.utcnow().strftime("%Y-%m-%d")
    count = len(opportunities)

    html_body = _HTML_BODY.format(
        date=today,
        count=count,
        opp_word="opportunity" if count == 1 else "opportunities",
        source_count=len(sources),
        cards=cards_html,
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Funding Alert] {count} new global health opportunit{'y' if count==1 else 'ies'} — {today}"
    msg["From"]    = EMAIL_FROM
    msg["To"]      = ", ".join(EMAIL_TO)
    msg.attach(MIMEText(_plain_text(opportunities), "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())
        log.info("Alert email sent to %s (%d opportunities).", EMAIL_TO, count)
        return True
    except smtplib.SMTPAuthenticationError:
        log.error(
            "Gmail authentication failed. "
            "Make sure you're using an App Password, not your login password."
        )
    except Exception as exc:
        log.error("Failed to send email: %s", exc)
    return False


# ── Helpers ────────────────────────────────────────────────────────────────────

def _build_cards(opportunities: list[dict]) -> str:
    html = ""
    for o in opportunities:
        deadline    = o.get("deadline", "")
        amount      = o.get("award_ceiling", "")
        description = (o.get("description") or "")[:280]
        if len(o.get("description", "")) > 280:
            description += "…"

        html += _OPP_CARD.format(
            url=o.get("url", "#"),
            title=_esc(o.get("title", "Untitled")),
            source=_esc(o.get("source", "")),
            agency=_esc(o.get("agency", "N/A")),
            deadline_row=_DEADLINE_ROW.format(_esc(deadline)) if deadline else "",
            amount_row=_AMOUNT_ROW.format(_esc(str(amount))) if amount else "",
            description=_esc(description),
        )
    return html


def _plain_text(opportunities: list[dict]) -> str:
    lines = [f"Global Health Funding Alert — {datetime.utcnow().strftime('%Y-%m-%d')}\n"]
    for i, o in enumerate(opportunities, 1):
        lines.append(f"{i}. {o.get('title', 'Untitled')}")
        lines.append(f"   Source  : {o.get('source', '')}")
        lines.append(f"   Agency  : {o.get('agency', 'N/A')}")
        if o.get("deadline"):
            lines.append(f"   Deadline: {o['deadline']}")
        lines.append(f"   URL     : {o.get('url', '')}")
        lines.append("")
    return "\n".join(lines)


def _esc(text: str) -> str:
    """Minimal HTML escaping."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
