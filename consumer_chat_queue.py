from kafka_client import get_consumer
from config import KAFKA_TOPIC_INCOMING_raw_messages
from celery_config import celery_app
from tasks.chat_extractor import extract_chat_history, extract_chat_messages

processed_chats = set()

def should_extract_chat(event):
    event_type = event.get('event_type')
    chat_name = event.get('chat_name', '')
    unread_count = event.get('unread_count', 0)
    
    chat_key = f"{chat_name}_{event.get('timestamp', '')[:10]}"
    if chat_key in processed_chats:
        return False
    
    if event_type == 'new_message' and unread_count >= 3:
        return True
    if event_type == 'new_chat' and unread_count > 0:
        return True
    return False

def queue_chat_extraction(event, full_history=True):
    chat_name = event.get('chat_name')
    chat_id = event.get('chat_id')
    
    if not chat_name:
        return None
    
    chat_key = f"{chat_name}_{event.get('timestamp', '')[:10]}"
    processed_chats.add(chat_key)
    
    if full_history:
        task = extract_chat_history.delay(chat_name=chat_name, chat_id=chat_id, scroll_to_top=True)
        print(f"📦 Queued FULL extraction: {chat_name} (Task ID: {task.id})")
    else:
        task = extract_chat_messages.delay(chat_name=chat_name, max_messages=50)
        print(f"📦 Queued QUICK extraction: {chat_name} (Task ID: {task.id})")
    
    return task.id

def start_consumer():
    print("🎧 Starting Chat Extraction Queue Consumer...")
    print(f"📡 Listening to: {KAFKA_TOPIC_INCOMING_raw_messages}")
    print("🔍 Waiting for chat events to trigger extraction...\n")
    
    consumer = get_consumer(topic=KAFKA_TOPIC_INCOMING_raw_messages, group_id='chat_extraction_queue')
    
    try:
        for message in consumer:
            event = message.value
            event_type = event.get('event_type', 'unknown')
            chat_name = event.get('chat_name', 'unknown')[:30]
            unread = event.get('unread_count', 0)
            
            print(f"📨 Event: {event_type:15} | {chat_name:30} | Unread: {unread}")
            
            if should_extract_chat(event):
                full_history = unread >= 5
                task_id = queue_chat_extraction(event, full_history=full_history)
                if task_id:
                    print(f"   ✅ Extraction queued (Task: {task_id[:8]}...)")
            else:
                print(f"   ⏭️  Skipped (doesn't meet extraction criteria)")
            print()
    except KeyboardInterrupt:
        print("\n⏹️  Stopping consumer...")
    except Exception as e:
        print(f"❌ Consumer error: {e}")
    finally:
        consumer.close()

def manual_extract(chat_name, full_history=True):
    event = {'chat_name': chat_name, 'chat_id': f'manual_{chat_name}', 'timestamp': ''}
    task_id = queue_chat_extraction(event, full_history=full_history)
    print(f"\n✅ Manual extraction queued for '{chat_name}'")
    print(f"🔍 Task ID: {task_id}")
    return task_id

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == 'manual':
        chat_name = sys.argv[2]
        full_history = '--full' in sys.argv or '-f' in sys.argv
        manual_extract(chat_name, full_history=full_history)
    else:
        start_consumer()
