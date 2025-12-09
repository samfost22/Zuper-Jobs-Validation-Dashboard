"""
Slack Notifier for Zuper Jobs Validation Dashboard
Sends notifications when jobs are completed without NetSuite Sales Order IDs

Supports:
- Direct Slack webhooks
- Zapier webhooks (which then send to Slack)
- Any generic webhook endpoint
"""

import json
import sqlite3
import requests
from datetime import datetime
from pathlib import Path

# Database path
DATA_DIR = Path(__file__).parent.parent / 'data'
DB_FILE = str(DATA_DIR / 'jobs_validation.db')

# Zuper URL patterns
ZUPER_JOB_URL = "https://web.zuperpro.com/jobs/{job_uid}/details"


def send_zapier_webhook(
    webhook_url: str,
    job_uid: str,
    job_number: str,
    job_title: str,
    organization_name: str,
    asset_name: str,
    service_team: str,
    completed_at: str,
    line_items: list
) -> bool:
    """
    Send job data to a Zapier webhook (or any generic webhook).
    Zapier can then format and send to Slack.

    Args:
        webhook_url: Zapier webhook URL (or any webhook endpoint)
        job_uid: Zuper job UID
        job_number: Job work order number
        job_title: Job title/description
        organization_name: Customer organization
        asset_name: Asset/serial number
        service_team: Team that completed the job
        completed_at: Completion timestamp
        line_items: List of line items needing NetSuite ID

    Returns:
        True if webhook call was successful
    """
    zuper_url = ZUPER_JOB_URL.format(job_uid=job_uid)

    # Format completion time nicely
    try:
        if completed_at:
            dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            completed_str = dt.strftime("%b %d, %Y at %I:%M %p")
        else:
            completed_str = "Unknown"
    except:
        completed_str = completed_at or "Unknown"

    # Simple flat payload - easy for Zapier to map
    payload = {
        "event_type": "job_missing_netsuite_id",
        "job_number": job_number or "N/A",
        "job_title": job_title or "N/A",
        "organization": organization_name or "N/A",
        "asset": asset_name or "N/A",
        "service_team": service_team or "N/A",
        "completed_at": completed_str,
        "line_items": ", ".join(line_items[:10]) if line_items else "None",
        "line_items_count": len(line_items) if line_items else 0,
        "zuper_url": zuper_url,
        "job_uid": job_uid,
        "timestamp": datetime.now().isoformat()
    }

    try:
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )

        # Zapier returns 200 on success
        if response.status_code in [200, 201, 202]:
            print(f"  Notification sent for job {job_number}")
            return True
        else:
            print(f"Webhook error: {response.status_code} - {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        print(f"Failed to send webhook notification: {e}")
        return False


class SlackNotifier:
    """Handles direct Slack webhook notifications (Block Kit format)"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def send_message(self, blocks: list, text: str = "New notification") -> bool:
        if not self.enabled:
            print("Slack notifications disabled (no webhook URL configured)")
            return False

        payload = {
            "text": text,
            "blocks": blocks
        }

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            if response.status_code == 200:
                return True
            else:
                print(f"Slack API error: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            print(f"Failed to send Slack notification: {e}")
            return False

    def send_missing_netsuite_alert(
        self,
        job_uid: str,
        job_number: str,
        job_title: str,
        organization_name: str,
        asset_name: str,
        service_team: str,
        completed_at: str,
        line_items: list
    ) -> bool:
        zuper_url = ZUPER_JOB_URL.format(job_uid=job_uid)

        items_text = "\n".join([f"• {item}" for item in line_items[:5]])
        if len(line_items) > 5:
            items_text += f"\n• ... and {len(line_items) - 5} more"

        try:
            if completed_at:
                dt = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
                completed_str = dt.strftime("%b %d, %Y at %I:%M %p")
            else:
                completed_str = "Unknown"
        except:
            completed_str = completed_at or "Unknown"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Job Needs NetSuite Sales Order ID",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Job Number:*\n<{zuper_url}|{job_number}>"},
                    {"type": "mrkdwn", "text": f"*Organization:*\n{organization_name or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Asset:*\n{asset_name or 'N/A'}"},
                    {"type": "mrkdwn", "text": f"*Service Team:*\n{service_team or 'N/A'}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Job Title:*\n{job_title}"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Completed:* {completed_str}"}
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Line Items Needing SO ID ({len(line_items)}):*\n{items_text}"}
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Open in Zuper", "emoji": True},
                        "url": zuper_url,
                        "style": "primary"
                    }
                ]
            }
        ]

        fallback_text = f"Job {job_number} completed without NetSuite ID - {len(line_items)} line items need SO ID"
        return self.send_message(blocks, fallback_text)


def init_notification_tracking():
    """Initialize the notification tracking table in the database."""
    DATA_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_uid TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            channel TEXT DEFAULT 'slack',
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            success BOOLEAN DEFAULT 1,
            error_message TEXT,
            UNIQUE(job_uid, notification_type, channel)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notification_job
        ON notification_log(job_uid, notification_type)
    """)

    conn.commit()
    conn.close()


def was_notification_sent(job_uid: str, notification_type: str = 'missing_netsuite_id') -> bool:
    """Check if a notification was already sent for this job."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 1 FROM notification_log
            WHERE job_uid = ? AND notification_type = ? AND success = 1
            LIMIT 1
        """, (job_uid, notification_type))

        result = cursor.fetchone() is not None
        conn.close()
        return result

    except sqlite3.Error:
        return False


def record_notification(
    job_uid: str,
    notification_type: str,
    success: bool,
    error_message: str = None
):
    """Record that a notification was sent (or attempted)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO notification_log
            (job_uid, notification_type, channel, sent_at, success, error_message)
            VALUES (?, ?, 'slack', ?, ?, ?)
        """, (
            job_uid,
            notification_type,
            datetime.now().isoformat(),
            success,
            error_message
        ))

        conn.commit()
        conn.close()

    except sqlite3.Error as e:
        print(f"Failed to record notification: {e}")


def send_missing_netsuite_notification(
    webhook_url: str,
    job_uid: str,
    job_number: str,
    job_title: str,
    organization_name: str,
    asset_name: str,
    service_team: str,
    completed_at: str,
    line_items: list,
    force: bool = False
) -> bool:
    """
    Send a notification for a job missing NetSuite ID.
    Works with both Zapier webhooks and direct Slack webhooks.
    Tracks notifications to avoid duplicates.

    Args:
        webhook_url: Webhook URL (Zapier or Slack)
        job_uid: Zuper job UID
        job_number: Job work order number
        job_title: Job title
        organization_name: Customer organization
        asset_name: Asset/serial
        service_team: Team that completed job
        completed_at: Completion timestamp
        line_items: List of line item names
        force: Send even if already notified

    Returns:
        True if notification was sent successfully
    """
    print(f"  [Notification] Attempting to send notification for job {job_number}")
    print(f"  [Notification] Webhook URL: {'configured' if webhook_url else 'NOT CONFIGURED'}")

    if not webhook_url:
        print(f"  [Notification] SKIPPED - No webhook URL configured")
        return False

    # Initialize tracking table if needed
    init_notification_tracking()

    # Check if already notified (unless forced)
    if not force and was_notification_sent(job_uid, 'missing_netsuite_id'):
        print(f"  [Notification] SKIPPED - Already notified for this job")
        return False  # Already notified, skip

    print(f"  [Notification] Sending to webhook...")

    # Detect webhook type and send appropriately
    # Zapier webhooks contain "hooks.zapier.com"
    # Slack webhooks contain "hooks.slack.com"
    is_slack_direct = "hooks.slack.com" in webhook_url

    if is_slack_direct:
        # Use Slack Block Kit format
        notifier = SlackNotifier(webhook_url)
        success = notifier.send_missing_netsuite_alert(
            job_uid=job_uid,
            job_number=job_number,
            job_title=job_title,
            organization_name=organization_name,
            asset_name=asset_name,
            service_team=service_team,
            completed_at=completed_at,
            line_items=line_items
        )
    else:
        # Use simple JSON for Zapier/generic webhooks
        success = send_zapier_webhook(
            webhook_url=webhook_url,
            job_uid=job_uid,
            job_number=job_number,
            job_title=job_title,
            organization_name=organization_name,
            asset_name=asset_name,
            service_team=service_team,
            completed_at=completed_at,
            line_items=line_items
        )

    # Record the notification attempt
    record_notification(
        job_uid=job_uid,
        notification_type='missing_netsuite_id',
        success=success,
        error_message=None if success else "Failed to send notification"
    )

    return success


def get_notification_stats() -> dict:
    """Get statistics about notifications sent."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM notification_log WHERE success = 1")
        total_sent = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM notification_log
            WHERE success = 1 AND sent_at > datetime('now', '-24 hours')
        """)
        last_24h = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM notification_log WHERE success = 0")
        failed = cursor.fetchone()[0]

        conn.close()

        return {
            'total_sent': total_sent,
            'last_24_hours': last_24h,
            'failed': failed
        }

    except sqlite3.Error:
        return {'total_sent': 0, 'last_24_hours': 0, 'failed': 0}
