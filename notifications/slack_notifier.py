"""
Slack Notifier for Zuper Jobs Validation Dashboard
Sends notifications when jobs are completed without NetSuite Sales Order IDs
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


class SlackNotifier:
    """Handles Slack webhook notifications"""

    def __init__(self, webhook_url: str):
        """
        Initialize Slack notifier with webhook URL

        Args:
            webhook_url: Slack incoming webhook URL
        """
        self.webhook_url = webhook_url
        self.enabled = bool(webhook_url)

    def send_message(self, blocks: list, text: str = "New notification") -> bool:
        """
        Send a message to Slack using Block Kit

        Args:
            blocks: Slack Block Kit blocks
            text: Fallback text for notifications

        Returns:
            True if successful, False otherwise
        """
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
        """
        Send an alert for a job missing NetSuite ID

        Args:
            job_uid: Zuper job UID
            job_number: Job work order number
            job_title: Job title/description
            organization_name: Customer organization
            asset_name: Asset/serial number
            service_team: Team that completed the job
            completed_at: Completion timestamp
            line_items: List of line items needing NetSuite ID

        Returns:
            True if notification sent successfully
        """
        zuper_url = ZUPER_JOB_URL.format(job_uid=job_uid)

        # Format line items for display
        items_text = "\n".join([f"• {item}" for item in line_items[:5]])
        if len(line_items) > 5:
            items_text += f"\n• ... and {len(line_items) - 5} more"

        # Format completion time
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
                    {
                        "type": "mrkdwn",
                        "text": f"*Job Number:*\n<{zuper_url}|{job_number}>"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Organization:*\n{organization_name or 'N/A'}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Asset:*\n{asset_name or 'N/A'}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Service Team:*\n{service_team or 'N/A'}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Job Title:*\n{job_title}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Completed:* {completed_str}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Line Items Needing SO ID ({len(line_items)}):*\n{items_text}"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Open in Zuper",
                            "emoji": True
                        },
                        "url": zuper_url,
                        "style": "primary"
                    }
                ]
            }
        ]

        fallback_text = f"Job {job_number} completed without NetSuite ID - {len(line_items)} line items need SO ID"

        return self.send_message(blocks, fallback_text)


def init_notification_tracking():
    """
    Initialize the notification tracking table in the database.
    This tracks which notifications have been sent to avoid duplicates.
    """
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
    """
    Check if a notification was already sent for this job

    Args:
        job_uid: The job UID to check
        notification_type: Type of notification

    Returns:
        True if notification was already sent
    """
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
    """
    Record that a notification was sent (or attempted)

    Args:
        job_uid: The job UID
        notification_type: Type of notification
        success: Whether the notification was sent successfully
        error_message: Error message if failed
    """
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
    Send a Slack notification for a job missing NetSuite ID.
    Tracks notifications to avoid duplicates.

    Args:
        webhook_url: Slack webhook URL
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
    if not webhook_url:
        return False

    # Initialize tracking table if needed
    init_notification_tracking()

    # Check if already notified (unless forced)
    if not force and was_notification_sent(job_uid, 'missing_netsuite_id'):
        return False  # Already notified, skip

    # Send the notification
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

    # Record the notification attempt
    record_notification(
        job_uid=job_uid,
        notification_type='missing_netsuite_id',
        success=success,
        error_message=None if success else "Failed to send Slack notification"
    )

    return success


def get_notification_stats() -> dict:
    """
    Get statistics about notifications sent

    Returns:
        Dictionary with notification stats
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        # Total notifications sent
        cursor.execute("""
            SELECT COUNT(*) FROM notification_log WHERE success = 1
        """)
        total_sent = cursor.fetchone()[0]

        # Notifications in last 24 hours
        cursor.execute("""
            SELECT COUNT(*) FROM notification_log
            WHERE success = 1
            AND sent_at > datetime('now', '-24 hours')
        """)
        last_24h = cursor.fetchone()[0]

        # Failed notifications
        cursor.execute("""
            SELECT COUNT(*) FROM notification_log WHERE success = 0
        """)
        failed = cursor.fetchone()[0]

        conn.close()

        return {
            'total_sent': total_sent,
            'last_24_hours': last_24h,
            'failed': failed
        }

    except sqlite3.Error:
        return {'total_sent': 0, 'last_24_hours': 0, 'failed': 0}
