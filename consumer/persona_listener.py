from kafka_client import get_consumer
from config import kafka_topic_persona

consumer = get_consumer(kafka_topic_persona, "persona-group")
for msg in consumer:
    data = msg.value
    print(f"🧍 Persona Update: {data['phone']} -> {data['persona']}")
