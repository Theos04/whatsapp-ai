"""
Stream WhatsApp Chat Updates to Kafka
Monitors #pane-side for chat changes and pushes to Kafka in real-time
"""

from playwright.sync_api import sync_playwright
from kafka_client import get_producer
from config import KAFKA_TOPIC_INCOMING_raw_messages
import time
import json
from datetime import datetime

# Configuration
CDP_URL = "http://127.0.0.1:9240"  # Chrome DevTools port
CHECK_INTERVAL = 2  # Check for changes every 2 seconds
WARMUP_CYCLES = 2  # Skip events for first N cycles to avoid false positives

# Kafka Producer
producer = get_producer()

# Store previous state to detect changes
previous_chats = {}
warmup_counter = 0


def extract_chat_data(page):
    """
    Extract chat data from WhatsApp using optimized selectors
    Returns list of chat dictionaries
    """
    js_script = """
    (function() {
        const chatList = document.querySelector('#pane-side > div > div > div[aria-label="Chat list"]');
        if (!chatList) return [];
        
        const chatElements = chatList.querySelectorAll(':scope > div > div');
        
        return Array.from(chatElements).map((chat, index) => {
            try {
                // Chat name/number - clean up newlines and timestamps
                const nameEl = chat.querySelector('div._ak8l._ap1_ > div._ak8o');
                let name = nameEl?.innerText?.trim() || '';
                // Remove timestamp from name (e.g., "Harish1\\n5:46 am" -> "Harish1")
                name = name.split('\\n')[0].trim();
                
                // Last message
                const msgEl = chat.querySelector('div._ak8l._ap1_ > div._ak8j > div._ak8k > span > span');
                const lastMsg = msgEl?.innerText?.trim() || '';
                
                // Unread count
                const countEl = chat.querySelector('div._ak8l._ap1_ > div._ak8j > div._ak8i > span:nth-child(1) > div > span > span');
                const unreadCount = countEl?.innerText?.trim() || '0';
                
                // Time
                const timeEl = chat.querySelector('div._ak8l._ap1_ > div._ak8o > div._ak8i.x1s688f');
                const time = timeEl?.innerText?.trim() || '';
                
                // Generate unique identifier based on name and index
                const chatId = name ? `chat_${name.replace(/[^a-zA-Z0-9]/g, '_')}_${index}` : `chat_${index}`;
                
                return {
                    chatId: chatId,
                    name: name,
                    lastMsg: lastMsg,
                    unreadCount: unreadCount,
                    time: time,
                    index: index
                };
            } catch (e) {
                console.error('Error extracting chat data:', e);
                return null;
            }
        }).filter(chat => chat !== null && chat.name !== '');
    })();
    """
    
    try:
        chats = page.evaluate(js_script)
        return chats
    except Exception as e:
        print(f"❌ Error extracting chat data: {e}")
        return []


def detect_changes(current_chats, skip_events=False):
    """
    Compare current chats with previous state
    Returns list of changed/new chats
    skip_events: If True, update state but don't return changes (warmup phase)
    """
    global previous_chats
    changes = []
    
    for chat in current_chats:
        chat_id = chat['chatId']
        
        # Skip event detection during warmup
        if skip_events:
            continue
        
        # Check if chat is new or has changes
        if chat_id not in previous_chats:
            # New chat - only report if it has unread messages
            unread = extract_number(chat.get('unreadCount', '0'))
            if unread > 0:
                changes.append({
                    'type': 'new_chat',
                    'chat': chat,
                    'timestamp': datetime.now().isoformat()
                })
        else:
            prev_chat = previous_chats[chat_id]
            
            # Check for new messages (unread count increased)
            prev_unread = extract_number(prev_chat.get('unreadCount', '0'))
            curr_unread = extract_number(chat.get('unreadCount', '0'))
            
            if curr_unread > prev_unread:
                changes.append({
                    'type': 'new_message',
                    'chat': chat,
                    'prev_unread': prev_unread,
                    'curr_unread': curr_unread,
                    'new_count': curr_unread - prev_unread,
                    'timestamp': datetime.now().isoformat()
                })
            
            # Check if last message changed (only if unread count is same or increased)
            elif chat['lastMsg'] != prev_chat['lastMsg'] and curr_unread > 0:
                changes.append({
                    'type': 'message_update',
                    'chat': chat,
                    'prev_msg': prev_chat['lastMsg'],
                    'timestamp': datetime.now().isoformat()
                })
    
    # Update previous state
    previous_chats = {chat['chatId']: chat for chat in current_chats}
    
    return changes


def extract_number(text):
    """Extract numeric value from text (e.g., '9 unread messages' -> 9)"""
    import re
    match = re.search(r'\d+', str(text))
    return int(match.group()) if match else 0


def push_to_kafka(change):
    """Push chat change event to Kafka"""
    try:
        chat = change['chat']
        
        # Prepare payload for Kafka
        payload = {
            'event_type': change['type'],
            'chat_id': chat['chatId'],
            'chat_name': chat['name'],
            'last_message': chat['lastMsg'],
            'unread_count': extract_number(chat['unreadCount']),
            'time': chat['time'],
            'timestamp': change['timestamp'],
            'source': 'whatsapp_stream'
        }
        
        # Add extra info based on event type
        if change['type'] == 'new_message':
            payload['prev_unread'] = change.get('prev_unread', 0)
            payload['new_messages'] = change.get('new_count', 1)
        
        # Send to Kafka
        producer.send(KAFKA_TOPIC_INCOMING_raw_messages, payload)
        producer.flush()
        
        # Log the event with better formatting
        emoji = "🆕" if change['type'] == 'new_chat' else "📩" if change['type'] == 'new_message' else "🔄"
        name_display = chat['name'][:25].ljust(25)
        unread_display = f"Unread: {extract_number(chat['unreadCount'])}"
        
        print(f"{emoji} {change['type'].upper():15} | {name_display} | {unread_display}")
        
        # Show new message count for new_message events
        if change['type'] == 'new_message':
            new_count = change.get('new_count', 0)
            print(f"   └─ +{new_count} new message(s) | Last: {chat['lastMsg'][:50]}")
        
    except Exception as e:
        print(f"❌ Error pushing to Kafka: {e}")


def monitor_whatsapp():
    """
    Main monitoring loop
    Connects to Chrome via CDP and monitors chat changes
    """
    global warmup_counter
    
    print("🚀 Starting WhatsApp Stream Monitor...")
    print(f"📡 Connecting to Chrome at {CDP_URL}")
    
    try:
        with sync_playwright() as p:
            # Connect to existing Chrome instance
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            
            # Wait for WhatsApp to load
            print("⏳ Waiting for WhatsApp to load...")
            page.wait_for_selector('#pane-side', timeout=30000)
            print(f"✅ Connected to WhatsApp: {page.url}")
            
            # Initialize previous state
            print("📊 Initializing chat state...")
            initial_chats = extract_chat_data(page)
            global previous_chats
            previous_chats = {chat['chatId']: chat for chat in initial_chats}
            
            # Count unread chats
            unread_chats = sum(1 for chat in initial_chats if extract_number(chat['unreadCount']) > 0)
            total_unread = sum(extract_number(chat['unreadCount']) for chat in initial_chats)
            
            print(f"✅ Found {len(initial_chats)} chats ({unread_chats} with unread, {total_unread} total unread messages)")
            print(f"⏰ Warmup phase: Skipping events for {WARMUP_CYCLES} cycles to avoid false positives...")
            print(f"\n🔍 Monitoring for changes... (Press Ctrl+C to stop)\n")
            
            # Main monitoring loop
            while True:
                try:
                    # Extract current chat data
                    current_chats = extract_chat_data(page)
                    
                    # Warmup phase - skip event generation
                    skip_events = warmup_counter < WARMUP_CYCLES
                    if skip_events:
                        warmup_counter += 1
                        if warmup_counter == WARMUP_CYCLES:
                            print(f"✅ Warmup complete! Now monitoring for real changes...\n")
                    
                    # Detect changes
                    changes = detect_changes(current_chats, skip_events=skip_events)
                    
                    # Push changes to Kafka
                    for change in changes:
                        push_to_kafka(change)
                    
                    # Wait before next check
                    time.sleep(CHECK_INTERVAL)
                    
                except KeyboardInterrupt:
                    print("\n\n⏹️  Stopping monitor...")
                    break
                except Exception as e:
                    print(f"⚠️  Error in monitoring loop: {e}")
                    time.sleep(CHECK_INTERVAL)
            
            browser.close()
            print("✅ Browser connection closed")
            
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        print("💡 Make sure Chrome is running with remote debugging enabled")
        print(f"💡 Check if WhatsApp is open at {CDP_URL}")


def test_extraction():
    """Test function to verify chat extraction works"""
    print("🧪 Testing chat extraction...")
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            
            page.wait_for_selector('#pane-side', timeout=10000)
            chats = extract_chat_data(page)
            
            # Calculate stats
            unread_chats = sum(1 for chat in chats if extract_number(chat['unreadCount']) > 0)
            total_unread = sum(extract_number(chat['unreadCount']) for chat in chats)
            
            print(f"\n✅ Successfully extracted {len(chats)} chats")
            print(f"📊 Stats: {unread_chats} chats with unread, {total_unread} total unread messages\n")
            print("Sample data (first 3 chats):")
            print(json.dumps(chats[:3], indent=2, ensure_ascii=False))
            
            browser.close()
            
    except Exception as e:
        print(f"❌ Test failed: {e}")


if __name__ == "__main__":
    import sys
    
    # Check for test mode
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_extraction()
    else:
        monitor_whatsapp()