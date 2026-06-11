"""
==========================================================
MetricGuard — Email Notifier  (email_notifier.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List

logger = logging.getLogger("metricguard.alerting.email_notifier")


class EmailNotifier:
    """
    SMTP-based notifier designed for SMTP integrations (including Gmail SMTP).
    """

    def __init__(self) -> None:
        self.server = os.getenv("SMTP_SERVER")
        self.port_str = os.getenv("SMTP_PORT")
        self.username = os.getenv("EMAIL_USERNAME")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.receiver = os.getenv("ALERT_RECEIVER")

    def send_alert_email(
        self,
        alert_id: str,
        severity: str,
        title: str,
        message: str,
        affected_services: List[str],
    ) -> bool:
        """
        Sends a rich, styled HTML alert email using configured SMTP details.
        Returns True if successful, False otherwise.
        """
        # Validate configuration
        if not all([self.server, self.port_str, self.username, self.password, self.receiver]):
            logger.warning(
                "[Email Notifier] SMTP configuration is incomplete. Skipping email notification. "
                "Ensure SMTP_SERVER, SMTP_PORT, EMAIL_USERNAME, EMAIL_PASSWORD, ALERT_RECEIVER are set in .env"
            )
            return False

        try:
            port = int(self.port_str)
        except ValueError:
            logger.error("[Email Notifier] Invalid SMTP_PORT: %s", self.port_str)
            return False

        # Build email content
        subject = f"[{severity.upper()}] MetricGuard Alert: {title} ({alert_id})"
        services_str = ", ".join(affected_services) if affected_services else "None"
        
        # Color based on severity
        header_color = "#d9534f" if severity.upper() == "CRITICAL" else "#f0ad4e"

        html_content = f"""
        <html>
            <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; background-color: #f7f9fc; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e1e8ed; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                    <div style="background-color: {header_color}; color: #ffffff; padding: 20px; text-align: center;">
                        <h2 style="margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 0.5px;">
                            {severity.upper()} Incident Alert
                        </h2>
                    </div>
                    <div style="padding: 25px;">
                        <table style="width: 100%; border-collapse: collapse; margin-bottom: 25px;">
                            <tr style="border-bottom: 1px solid #f0f2f5;">
                                <td style="padding: 10px 0; font-weight: bold; color: #657786; width: 140px;">Alert ID:</td>
                                <td style="padding: 10px 0; color: #14171a;">{alert_id}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #f0f2f5;">
                                <td style="padding: 10px 0; font-weight: bold; color: #657786;">Severity:</td>
                                <td style="padding: 10px 0;">
                                    <span style="background-color: {header_color}; color: #ffffff; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: bold; text-transform: uppercase;">
                                        {severity}
                                    </span>
                                </td>
                            </tr>
                            <tr style="border-bottom: 1px solid #f0f2f5;">
                                <td style="padding: 10px 0; font-weight: bold; color: #657786;">Root Cause:</td>
                                <td style="padding: 10px 0; color: #14171a; font-weight: 500;">{title}</td>
                            </tr>
                            <tr style="border-bottom: 1px solid #f0f2f5;">
                                <td style="padding: 10px 0; font-weight: bold; color: #657786;">Affected Services:</td>
                                <td style="padding: 10px 0; color: #14171a;">{services_str}</td>
                            </tr>
                        </table>
                        
                        <div style="background-color: #f8f9fa; border-left: 4px solid {header_color}; border-radius: 4px; padding: 15px; margin-bottom: 25px;">
                            <strong style="color: #333; display: block; margin-bottom: 5px;">Alert Message:</strong>
                            <span style="color: #4b4f56; font-size: 14px;">{message}</span>
                        </div>
                        
                        <p style="font-size: 12px; color: #aab8c2; text-align: center; margin-top: 35px; border-top: 1px solid #e1e8ed; padding-top: 15px;">
                            This email was generated automatically by MetricGuard AIOps Alerting Engine.<br/>
                            Do not reply directly to this notification.
                        </p>
                    </div>
                </div>
            </body>
        </html>
        """

        # Plain text alternative
        plain_text = (
            f"=== METRICGUARD ALERT ===\n"
            f"Alert ID: {alert_id}\n"
            f"Severity: {severity.upper()}\n"
            f"Root Cause: {title}\n"
            f"Affected Services: {services_str}\n\n"
            f"Description:\n{message}\n"
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = self.receiver

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        try:
            logger.info("[Email Notifier] Connecting to SMTP server %s:%d...", self.server, port)
            
            # Port 465 uses SMTP_SSL; port 587 and others use STARTTLS
            if port == 465:
                server = smtplib.SMTP_SSL(self.server, port, timeout=10)
            else:
                server = smtplib.SMTP(self.server, port, timeout=10)
                server.ehlo()
                if port == 587 or server.has_extn("STARTTLS"):
                    server.starttls()
                    server.ehlo()

            server.login(self.username, self.password)
            server.sendmail(self.username, self.receiver, msg.as_string())
            server.close()
            
            logger.info("[Email Notifier] Alert %s email successfully delivered to %s.", alert_id, self.receiver)
            return True
        except Exception as e:
            logger.error("[Email Notifier] Failed to deliver alert %s email: %s", alert_id, e, exc_info=True)
            return False
