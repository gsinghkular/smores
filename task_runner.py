import settings

from celery import Celery

celery = Celery("smores", broker=settings.REDIS_URL)

celery.conf.beat_schedule = {
    "match_pairs": {"task": "tasks.match_pairs_periodic", "schedule": 60 * 60},
    "send_failed_intros": {"task": "tasks.send_failed_intros", "schedule": 60 * 60}
}
