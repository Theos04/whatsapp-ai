import time, json
from unread_messages import open_and_download_unread_chat
from kafka_client import get_producer
from config import KAFKA_TOPIC_INCOMING_raw_messages

producer = get_producer()

def process_unread_chats():
    while True:
        try:
            result = open_and_download_unread_chat()
            if result and result.get("messageCount", 0) > 0:
                chat_file = f"{result['chatName']}_chat.json"
                with open(chat_file, "r", encoding="utf-8") as f:
                    messages = json.load(f)
                
                for msg in messages:
                    phone = msg["sender"]
                    text = msg["text"]
                    payload = {"phone": phone, "message": text, "source": "whatsapp"}
                    producer.send(KAFKA_TOPIC_INCOMING_raw_messages, payload)
                    print(f"📥 Queued message to Kafka: {phone} -> {text}")
                
                producer.flush()
        except Exception as e:
            print(f"Watcher error: {e}")
        
        # Poll every 10 seconds
        time.sleep(10)

if __name__ == "__main__":
    print("🕵️ Starting WhatsApp watcher...")
    process_unread_chats()
