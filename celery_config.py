from celery import Celery
import os
from dotenv import load_dotenv


load_dotenv()

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

celery_app = Celery(
    'whatsapp_chat_processor',
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=['tasks.chat_extractor']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
)

celery_app.conf.task_routes = {
    'tasks.chat_extractor.extract_chat_history': {'queue': 'chat_extraction'},
    'tasks.chat_extractor.extract_chat_messages': {'queue': 'chat_extraction'},
}

if __name__ == '__main__':
    celery_app.start()
