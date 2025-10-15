"""
Setup script to create all required Celery files
Run this once to set up the proper file structure
"""

import os
from pathlib import Path

# File contents as separate variables to avoid quote issues
TASKS_INIT = """# Tasks package for Celery workers
"""

CELERY_CONFIG = """from celery import Celery
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
"""

CHAT_EXTRACTOR = """from celery_config import celery_app
from playwright.sync_api import sync_playwright
import json
import os
import re
from datetime import datetime
from pathlib import Path

CDP_URL = "http://127.0.0.1:9240"
CHAT_EXPORT_DIR = "exported_chats"
SCROLL_PAUSE_TIME = 1.5

Path(CHAT_EXPORT_DIR).mkdir(exist_ok=True)

def sanitize_filename(name):
    safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
    return safe_name[:50]

@celery_app.task(name='tasks.chat_extractor.extract_chat_history', bind=True)
def extract_chat_history(self, chat_name, chat_id=None, scroll_to_top=True):
    self.update_state(state='PROGRESS', meta={'status': 'Connecting to Chrome...'})
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            
            self.update_state(state='PROGRESS', meta={'status': f'Searching for chat: {chat_name}'})
            
            success = open_chat(page, chat_name)
            if not success:
                return {'status': 'error', 'message': f'Could not find chat: {chat_name}', 'chat_name': chat_name}
            
            self.update_state(state='PROGRESS', meta={'status': 'Scrolling to load messages...'})
            
            if scroll_to_top:
                scroll_count = scroll_to_top_of_chat(page)
                self.update_state(state='PROGRESS', meta={'status': f'Loaded messages (scrolled {scroll_count} times)'})
            
            self.update_state(state='PROGRESS', meta={'status': 'Extracting messages...'})
            
            messages = extract_messages(page)
            
            chat_header = page.query_selector('#main header span[dir="auto"]')
            actual_chat_name = chat_header.inner_text().strip() if chat_header else chat_name
            
            safe_name = sanitize_filename(actual_chat_name)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_name}_{timestamp}_chat.json"
            filepath = os.path.join(CHAT_EXPORT_DIR, filename)
            
            export_data = {
                'chat_name': actual_chat_name,
                'chat_id': chat_id,
                'extracted_at': datetime.now().isoformat(),
                'message_count': len(messages),
                'messages': messages
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            browser.close()
            
            print(f"✅ Extracted {len(messages)} messages from '{actual_chat_name}' → {filepath}")
            
            return {
                'status': 'success',
                'chat_name': actual_chat_name,
                'message_count': len(messages),
                'filepath': filepath,
                'filename': filename
            }
            
    except Exception as e:
        print(f"❌ Error extracting chat '{chat_name}': {e}")
        return {'status': 'error', 'message': str(e), 'chat_name': chat_name}

def open_chat(page, chat_name):
    try:
        search_box = page.query_selector('div[contenteditable="true"][data-tab="3"]')
        if not search_box:
            return False
        
        search_box.click()
        page.wait_for_timeout(500)
        search_box.fill(chat_name)
        page.wait_for_timeout(1000)
        
        first_result = page.query_selector('div[data-testid="cell-frame-container"]')
        if not first_result:
            return False
        
        first_result.click()
        page.wait_for_timeout(1500)
        
        return page.query_selector('#main') is not None
    except:
        return False

def scroll_to_top_of_chat(page, max_scrolls=100):
    scroll_count = 0
    try:
        prev_count = len(page.query_selector_all('div[data-pre-plain-text]'))
        
        for i in range(max_scrolls):
            page.evaluate('''
                const container = document.querySelector('#main div[data-testid="conversation-panel-body"]');
                if (container) { container.scrollTop = 0; }
            ''')
            
            page.wait_for_timeout(int(SCROLL_PAUSE_TIME * 1000))
            scroll_count += 1
            
            current_count = len(page.query_selector_all('div[data-pre-plain-text]'))
            if current_count == prev_count:
                break
            prev_count = current_count
            
            if scroll_count % 10 == 0:
                print(f"📜 Scrolled {scroll_count} times, loaded {current_count} messages...")
        
        return scroll_count
    except:
        return scroll_count

def extract_messages(page):
    js_script = \"\"\"
    (function () {
        const messageDivs = [...document.querySelectorAll('div[data-pre-plain-text]')];
        return messageDivs.map((div, index) => {
            try {
                const meta = div.getAttribute('data-pre-plain-text') || '';
                const timeMatch = meta.match(/\\\\[(.*?)\\\\]/);
                const rawTimestamp = timeMatch ? timeMatch[1] : null;
                let timestamp = null;
                if (rawTimestamp) {
                    try { timestamp = new Date(rawTimestamp).toISOString(); }
                    catch (e) { timestamp = rawTimestamp; }
                }
                const senderMatch = meta.match(/\\\\] (.*?):/);
                const sender = senderMatch ? senderMatch[1].trim() : 'Unknown';
                const textEl = div.querySelector('span.selectable-text');
                const text = textEl ? textEl.innerText.trim() : '';
                const fromBusiness = sender.toLowerCase().includes('harsh') || sender.toLowerCase().includes('bot');
                return {
                    index: index,
                    sender: sender,
                    text: text,
                    timestamp: timestamp,
                    fromBusiness: fromBusiness,
                    rawMeta: meta
                };
            } catch (e) { return null; }
        }).filter(m => m !== null && m.text);
    })();
    \"\"\"
    try:
        return page.evaluate(js_script)
    except:
        return []

@celery_app.task(name='tasks.chat_extractor.extract_chat_messages', bind=True)
def extract_chat_messages(self, chat_name, max_messages=100):
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            
            success = open_chat(page, chat_name)
            if not success:
                return {'status': 'error', 'message': f'Could not find chat: {chat_name}'}
            
            messages = extract_messages(page)
            browser.close()
            
            return {
                'status': 'success',
                'chat_name': chat_name,
                'message_count': len(messages),
                'messages': messages[:max_messages]
            }
    except Exception as e:
        return {'status': 'error', 'message': str(e), 'chat_name': chat_name}
"""

CONSUMER_CHAT_QUEUE = """from kafka_client import get_consumer
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
    print("🔍 Waiting for chat events to trigger extraction...\\n")
    
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
        print("\\n⏹️  Stopping consumer...")
    except Exception as e:
        print(f"❌ Consumer error: {e}")
    finally:
        consumer.close()

def manual_extract(chat_name, full_history=True):
    event = {'chat_name': chat_name, 'chat_id': f'manual_{chat_name}', 'timestamp': ''}
    task_id = queue_chat_extraction(event, full_history=full_history)
    print(f"\\n✅ Manual extraction queued for '{chat_name}'")
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
"""

def create_file(filepath, content):
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Created: {filepath}")

def setup_celery_structure():
    print("🚀 Setting up Celery Chat Extraction System...\n")
    
    # Create directories
    os.makedirs('tasks', exist_ok=True)
    os.makedirs('exported_chats', exist_ok=True)
    print("📁 Created: tasks/")
    print("📁 Created: exported_chats/")
    
    # Create files
    create_file('tasks/__init__.py', TASKS_INIT)
    create_file('celery_config.py', CELERY_CONFIG)
    create_file('tasks/chat_extractor.py', CHAT_EXTRACTOR)
    create_file('consumer_chat_queue.py', CONSUMER_CHAT_QUEUE)
    
    print("\n" + "="*60)
    print("✅ Setup Complete!")
    print("="*60)
    print("\n📝 Add to your .env file:")
    print("CELERY_BROKER_URL=redis://localhost:6379/0")
    print("CELERY_RESULT_BACKEND=redis://localhost:6379/0")
    print("\n🚀 Next steps:")
    print("1. Start Redis: redis-server")
    print("2. Start worker: celery -A celery_config worker --loglevel=info --queues=chat_extraction")
    print("3. Start consumer: python consumer_chat_queue.py")
    print()

if __name__ == "__main__":
    setup_celery_structure()