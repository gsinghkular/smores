web: uvicorn main:api --host=0.0.0.0 --port=${PORT:-5000}
celery: celery -A task_runner worker -B -l info --concurrency=1
release: alembic upgrade head