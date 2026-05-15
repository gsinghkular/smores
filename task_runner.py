import settings

from celery import Celery
from celery.schedules import crontab

celery = Celery("smores", broker=settings.REDIS_URL)
celery.autodiscover_tasks(["src.tasks.pairing", "src.tasks.member_management"])

celery.conf.beat_schedule = {
    "match_pairs": {
        "task": "src.tasks.pairing.match_pairs_periodic",
        "schedule": 60 * 60,
    },
    "send_failed_intros": {
        "task": "src.tasks.pairing.send_failed_intros",
        "schedule": 60 * 60,
    },
    "send_midpoint_reminder": {
        "task": "src.tasks.pairing.send_midpoint_reminder",
        "schedule": 60 * 60,
    },
    "remove_disabled_users": {
        "task": "src.tasks.member_management.remove_disabled_users",
        "schedule": crontab(hour=0, minute=0, day_of_week="thursday"),
    },
}
