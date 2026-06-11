"""
==========================================================
MetricGuard — Alerting Package Initialization  (__init__.py)
==========================================================

Phase 14: Real-Time Alerting System
"""

from backend.alerting.models import Alert
from backend.alerting.repository import AlertRepository
from backend.alerting.alert_manager import get_alert_manager, AlertManager
from backend.alerting.websocket_notifier import get_websocket_manager, ConnectionManager
from backend.alerting.email_notifier import EmailNotifier
