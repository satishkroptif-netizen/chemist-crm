from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "chemist_crm",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.services.email_tasks",
        "app.services.notification_tasks",
        "app.services.report_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,
    task_soft_time_limit=25 * 60,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    beat_schedule={
        "check-expiring-products": {
            "task": "app.services.notification_tasks.check_expiring_products",
            "schedule": 86400.0,  # Daily
        },
        "send-overdue-reminders": {
            "task": "app.services.notification_tasks.send_overdue_reminders",
            "schedule": 86400.0,  # Daily
        },
        "generate-daily-reports": {
            "task": "app.services.report_tasks.generate_daily_reports",
            "schedule": 3600.0,  # Hourly
        },
        "cleanup-old-sessions": {
            "task": "app.services.maintenance_tasks.cleanup_old_sessions",
            "schedule": 604800.0,  # Weekly
        },
    },
)

celery_app.autodiscover_tasks()


@celery_app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f"Request: {self.request!r}")