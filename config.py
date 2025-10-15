# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# Kafka
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC_INCOMING_raw_messages = "incoming_raw_messages"
kafka_topic_persona = "persona"
kafka_topic_call_report = "call-report"
KAFKA_TOPIC_REPLIES = "bot_replies"

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

# Misc
DEBUG = True
