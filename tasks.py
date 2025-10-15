# tasks.py
from celery import Celery
from kafka import KafkaConsumer, KafkaProducer
import json
from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_TOPIC_INCOMING_raw_messages, KAFKA_TOPIC_REPLIES

app = Celery('tasks', broker='redis://localhost:6379/0', backend='redis://localhost:6379/0')

@app.task
def consume_messages():
    consumer = KafkaConsumer(
        KAFKA_TOPIC_INCOMING_raw_messages,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode('utf-8')),
        auto_offset_reset='earliest',
        group_id='whatsapp-ai'
    )
    
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_serializer=lambda m: json.dumps(m).encode('utf-8')
    )

    print("🚀 Kafka consumer started for incoming_raw_messages...")
    
    for msg in consumer:
        data = msg.value
        phone = data.get('phone')
        message = data.get('message')
        print(f"📥 Received message from {phone}: {message}")

        # TODO: run NLP, persona detection, Playwright automation
        reply = f"Auto-reply to {phone}: got your message '{message}'"

        # Push reply to Kafka topic
        producer.send(KAFKA_TOPIC_REPLIES, {"phone": phone, "reply": reply})
        producer.flush()
        print(f"📤 Reply queued for {phone}")
