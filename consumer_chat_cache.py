"""
Kafka Consumer for WhatsApp Chat Events
Consumes messages from streaming monitor and updates in-memory cache
"""

from kafka_client import get_consumer
from config import KAFKA_TOPIC_INCOMING_raw_messages
import json
from datetime import datetime

# In-memory chat cache (shared with Flask via Redis or DB in production)
chat_cache = {}

def process_chat_event(event):
    """
    Process incoming chat event and update cache
    """
    try:
        event_type = event.get('event_type')
        chat_id = event.get('chat_id')
        
        # Create/update chat entry
        chat_entry = {
            'chatId': chat_id,
            'name': event.get('chat_name', ''),
            'lastMsg': event.get('last_message', ''),
            'unreadCount': event.get('unread_count', 0),
            'time': event.get('time', ''),
            'lastUpdated': event.get('timestamp'),
            'source': event.get('source', 'stream')
        }
        
        # Update cache
        chat_cache[chat_id] = chat_entry
        
        # Log the event
        emoji_map = {
            'new_chat': '🆕',
            'new_message': '📩',
            'message_update': '🔄'
        }
        emoji = emoji_map.get(event_type, '📬')
        
        print(f"{emoji} [{event_type}] {chat_entry['name'][:30]} | Unread: {chat_entry['unreadCount']}")
        
        # Additional processing based on event type
        if event_type == 'new_message':
            new_msg_count = event.get('new_messages', 0)
            print(f"   └─ +{new_msg_count} new message(s)")
            
            # Here you can trigger AI response logic
            # trigger_ai_response(chat_entry)
        
    except Exception as e:
        print(f"❌ Error processing event: {e}")


def get_cached_chats():
    """Get all cached chats as a list"""
    return list(chat_cache.values())


def get_cache_stats():
    """Get cache statistics"""
    total_unread = sum(chat.get('unreadCount', 0) for chat in chat_cache.values())
    unread_chats = sum(1 for chat in chat_cache.values() if chat.get('unreadCount', 0) > 0)
    
    return {
        'total_chats': len(chat_cache),
        'unread_chats': unread_chats,
        'total_unread_messages': total_unread
    }


def start_consumer():
    """
    Start Kafka consumer and process events
    """
    print("🎧 Starting Kafka consumer for chat events...")
    print(f"📡 Listening to topic: {KAFKA_TOPIC_INCOMING_raw_messages}")
    
    consumer = get_consumer(
        topic=KAFKA_TOPIC_INCOMING_raw_messages,
        group_id='chat_cache_consumer'
    )
    
    print("✅ Consumer started. Waiting for messages...\n")
    
    try:
        for message in consumer:
            event = message.value
            
            # Process the event
            process_chat_event(event)
            
            # Print cache stats periodically
            if len(chat_cache) > 0 and len(chat_cache) % 10 == 0:
                stats = get_cache_stats()
                print(f"\n📊 Cache Stats: {stats['total_chats']} chats, "
                      f"{stats['unread_chats']} unread, "
                      f"{stats['total_unread_messages']} total unread messages\n")
    
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping consumer...")
    except Exception as e:
        print(f"❌ Consumer error: {e}")
    finally:
        consumer.close()
        print("✅ Consumer closed")


if __name__ == "__main__":
    start_consumer()