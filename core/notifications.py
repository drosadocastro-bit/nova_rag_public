"""
Alert Notification System

Sends alerts via multiple channels:
- Email notifications
- Webhook (Slack, Discord, etc.)
- In-app notifications
"""

import json
import logging
import aiohttp
import asyncio
from typing import Callable, List, Optional, Dict, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class NotificationConfig:
    """Configuration for notifications."""
    
    # Email
    email_enabled: bool = False
    smtp_server: str = "localhost"
    smtp_port: int = 587
    email_from: str = "noreply@nova-nic.local"
    email_recipients: List[str] = None
    
    # Webhook
    webhook_enabled: bool = False
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    
    # In-app
    in_app_enabled: bool = True
    in_app_retention_hours: int = 24
    
    def __post_init__(self):
        if self.email_recipients is None:
            self.email_recipients = []


class EmailNotifier:
    """Send alert notifications via email."""
    
    def __init__(self, config: NotificationConfig):
        """Initialize email notifier."""
        self.config = config
        self.enabled = config.email_enabled
    
    async def send(self, subject: str, message: str, recipients: Optional[List[str]] = None) -> bool:
        """
        Send email notification.
        
        Args:
            subject: Email subject
            message: Email body
            recipients: Email recipients (uses config default if not provided)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        recipients = recipients or self.config.email_recipients
        if not recipients:
            logger.warning("No email recipients configured")
            return False
        
        try:
            # This would use actual SMTP in production
            # For now, just log the email
            logger.info(f"Email notification: {subject}")
            logger.info(f"Recipients: {recipients}")
            logger.info(f"Message: {message}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False


class WebhookNotifier:
    """Send alert notifications via webhook."""
    
    def __init__(self, config: NotificationConfig):
        """Initialize webhook notifier."""
        self.config = config
        self.enabled = config.webhook_enabled
    
    async def send(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        url: Optional[str] = None,
    ) -> bool:
        """
        Send webhook notification.
        
        Args:
            event_type: Type of event
            severity: Alert severity (critical, warning, info)
            message: Alert message
            details: Additional details
            url: Webhook URL (uses config default if not provided)
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        url = url or self.config.webhook_url
        if not url:
            logger.warning("No webhook URL configured")
            return False
        
        payload = {
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "details": details or {},
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"Content-Type": "application/json"}
                
                # Add secret if configured
                if self.config.webhook_secret:
                    import hmac
                    import hashlib
                    body = json.dumps(payload)
                    signature = hmac.new(
                        self.config.webhook_secret.encode(),
                        body.encode(),
                        hashlib.sha256
                    ).hexdigest()
                    headers["X-Signature"] = signature
                
                async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
                    if resp.status < 400:
                        logger.info(f"Webhook notification sent: {event_type}")
                        return True
                    else:
                        logger.error(f"Webhook returned {resp.status}: {await resp.text()}")
                        return False
        except asyncio.TimeoutError:
            logger.error(f"Webhook request timeout: {url}")
            return False
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False


class InAppNotifier:
    """Store in-app notifications."""
    
    def __init__(self, config: NotificationConfig, max_notifications: int = 1000):
        """Initialize in-app notifier."""
        self.config = config
        self.max_notifications = max_notifications
        self.notifications: List[Dict[str, Any]] = []
    
    async def send(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store in-app notification."""
        if not self.config.in_app_enabled:
            return False
        
        notification = {
            "event_type": event_type,
            "severity": severity,
            "message": message,
            "details": details or {},
            "timestamp": datetime.now().isoformat(),
        }
        
        self.notifications.append(notification)
        
        # Keep only recent notifications
        if len(self.notifications) > self.max_notifications:
            self.notifications = self.notifications[-self.max_notifications:]
        
        return True
    
    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent notifications."""
        return self.notifications[-limit:]
    
    def clear(self) -> None:
        """Clear all notifications."""
        self.notifications.clear()


class NotificationManager:
    """
    Central notification manager.
    
    Coordinates multiple notification channels.
    """
    
    def __init__(self, config: Optional[NotificationConfig] = None):
        """Initialize notification manager."""
        self.config = config or NotificationConfig()
        
        self.email = EmailNotifier(self.config)
        self.webhook = WebhookNotifier(self.config)
        self.in_app = InAppNotifier(self.config)
        
        # Notification queues for async processing
        self.notification_queue: List[Dict[str, Any]] = []
    
    async def notify(
        self,
        event_type: str,
        severity: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        channels: Optional[List[str]] = None,
    ) -> bool:
        """
        Send notification through configured channels.
        
        Args:
            event_type: Type of event
            severity: Severity level (critical, warning, info)
            message: Notification message
            details: Additional details
            channels: Channels to use (all enabled by default)
            
        Returns:
            True if at least one notification sent
        """
        channels = channels or ["email", "webhook", "in_app"]
        sent = False
        
        tasks = []
        
        if "email" in channels:
            tasks.append(self.email.send(event_type, message))
        
        if "webhook" in channels:
            tasks.append(self.webhook.send(event_type, severity, message, details))
        
        if "in_app" in channels:
            tasks.append(self.in_app.send(event_type, severity, message, details))
        
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            sent = any(r is True for r in results)
        
        return sent
    
    async def notify_alert(
        self,
        rule_name: str,
        severity: str,
        message: str,
        metric_value: float,
        threshold: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send alert notification."""
        alert_details = details or {}
        alert_details.update({
            "rule_name": rule_name,
            "metric_value": metric_value,
            "threshold": threshold,
        })
        
        return await self.notify(
            event_type="alert",
            severity=severity,
            message=message,
            details=alert_details,
        )
    
    async def notify_performance(
        self,
        metric_name: str,
        metric_value: float,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send performance notification."""
        alert_details = details or {}
        alert_details.update({
            "metric_name": metric_name,
            "metric_value": metric_value,
        })
        
        return await self.notify(
            event_type="performance",
            severity="info",
            message=f"Performance metric: {metric_name} = {metric_value}",
            details=alert_details,
        )
    
    async def notify_error(
        self,
        error_type: str,
        error_message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Send error notification."""
        alert_details = details or {}
        alert_details.update({
            "error_type": error_type,
        })
        
        return await self.notify(
            event_type="error",
            severity="critical",
            message=f"Error: {error_message}",
            details=alert_details,
        )
    
    def get_recent_notifications(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent notifications from in-app storage."""
        return self.in_app.get_recent(limit)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics."""
        return {
            "email_enabled": self.config.email_enabled,
            "webhook_enabled": self.config.webhook_enabled,
            "in_app_enabled": self.config.in_app_enabled,
            "recent_notifications": len(self.in_app.notifications),
        }


# Global notification manager instance
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager(config: Optional[NotificationConfig] = None) -> NotificationManager:
    """Get or create notification manager singleton."""
    global _notification_manager
    
    if _notification_manager is None:
        _notification_manager = NotificationManager(config)
    
    return _notification_manager


def configure_notifications(config: NotificationConfig) -> NotificationManager:
    """Configure and get notification manager."""
    global _notification_manager
    _notification_manager = NotificationManager(config)
    return _notification_manager
