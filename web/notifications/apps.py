from django.apps import AppConfig

class NotificationsConfig(AppConfig):
    name = 'notifications'

    def ready(self):
        try:
            import notifications.signals  # noqa
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(
                f"[NotificationsConfig] gagal import signals: {e}"
            )