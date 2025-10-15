import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from celery_config import celery_app
from playwright.sync_api import sync_playwright
import json
import re
from datetime import datetime
from pathlib import Path

# ==========================
# Constants & Config
# ==========================
CDP_URL = "http://127.0.0.1:9240"
CHAT_EXPORT_DIR = "exported_chats"
SCROLL_PAUSE_TIME = 1.5
Path(CHAT_EXPORT_DIR).mkdir(exist_ok=True)


# ==========================
# Utility Functions
# ==========================
def sanitize_filename(name):
    """Sanitize filename to avoid illegal characters."""
    safe_name = re.sub(r'[^a-z0-9]', '_', name.lower())
    return safe_name[:50]


# ==========================
# Core Page Functions
# ==========================
def open_chat(page, chat_name=None):
    """Open the first chat or a specific chat by name."""
    try:
        page.wait_for_selector("#pane-side", timeout=15000)

        if chat_name:
            search_box = page.query_selector('div[contenteditable="true"][data-tab="1"]')
            if not search_box:
                page.screenshot(path="debug_search_box.png")
                return False
            search_box.click()
            page.wait_for_timeout(500)
            search_box.fill(chat_name)
            page.wait_for_timeout(1000)
            first_result = page.query_selector('div[data-testid="cell-frame-container"]')
            if not first_result:
                page.screenshot(path="debug_no_results.png")
                return False
            first_result.click()
        else:
            first_chat = page.query_selector('#pane-side > div > div > div > div:nth-child(1)')
            if not first_chat:
                page.screenshot(path="debug_first_chat.png")
                return False
            first_chat.click()

        page.wait_for_timeout(2000)
        chat_pane = page.query_selector('#main')
        if not chat_pane:
            page.screenshot(path="debug_chat_pane.png")
            return False

        return True
    except Exception as e:
        print(f"❌ Open chat error: {e}")
        page.screenshot(path="debug_open_chat.png")
        return False


def scroll_to_top_of_chat(page, max_scrolls=200):
    """Scroll to top to load all messages."""
    scroll_count = 0
    try:
        prev_count = len(page.query_selector_all('div[data-pre-plain-text]'))

        for _ in range(max_scrolls):
            page.evaluate("""
                const container = document.querySelector('#main div[data-testid="conversation-panel-body"]');
                if (container) { container.scrollTop = 0; }
            """)
            page.wait_for_timeout(int(SCROLL_PAUSE_TIME * 1000))
            scroll_count += 1
            current_count = len(page.query_selector_all('div[data-pre-plain-text]'))
            if current_count == prev_count:
                break
            prev_count = current_count
        return scroll_count
    except Exception as e:
        print(f"❌ Scroll error: {e}")
        return scroll_count


def extract_messages(page, max_messages=None):
    """Extract messages including text and media placeholders."""
    js_script = """
    (function () {
        const messageDivs = [...document.querySelectorAll('div[data-pre-plain-text]')];
        return messageDivs.map((div, index) => {
            try {
                const meta = div.getAttribute('data-pre-plain-text') || '';
                const timeMatch = meta.match(/\\[(.*?)\\]/);
                const rawTimestamp = timeMatch ? timeMatch[1] : null;
                let timestamp = rawTimestamp;
                const senderMatch = meta.match(/\\] (.*?):/);
                const sender = senderMatch ? senderMatch[1].trim() : 'Unknown';
                
                // Handle both text and media messages
                const textEl = div.querySelector('span.selectable-text');
                const text = textEl ? textEl.innerText.trim() : '';

                let mediaType = null;
                if (!text) {
                    if (div.querySelector('img')) mediaType = 'image';
                    else if (div.querySelector('video')) mediaType = 'video';
                    else if (div.querySelector('audio')) mediaType = 'audio';
                    else if (div.querySelector('svg[data-icon="sticker"]')) mediaType = 'sticker';
                }

                const fromBusiness = sender.toLowerCase().includes('harsh') || sender.toLowerCase().includes('bot');

                return {index, sender, text, timestamp, fromBusiness, rawMeta: meta, mediaType};
            } catch (e) {
                return null;
            }
        }).filter(m => m !== null);
    })();
    """
    try:
        chat_pane = page.query_selector('#main')
        if not chat_pane:
            page.screenshot(path="debug_extract_messages.png")
            return []

        messages = page.evaluate(js_script)
        if max_messages:
            messages = messages[:max_messages]

        return messages
    except Exception as e:
        print(f"❌ JS extraction error: {e}")
        page.screenshot(path="debug_extract_error.png")
        return []


# ==========================
# Celery Tasks
# ==========================
@celery_app.task(name='tasks.chat_extractor.extract_chat_history', bind=True)
def extract_chat_history(self, chat_name=None, chat_id=None, scroll_to_top=True):
    """Extract full chat history and save as JSON."""
    self.update_state(state='PROGRESS', meta={'status': 'Connecting to Chrome...'})

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]

            self.update_state(state='PROGRESS', meta={'status': f'Searching for chat: {chat_name or "First chat"}'})
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
            actual_chat_name = chat_header.inner_text().strip() if chat_header else (chat_name or "Unknown Chat")

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


@celery_app.task(name='tasks.chat_extractor.extract_chat_messages', bind=True)
def extract_chat_messages(self, chat_name=None, max_messages=100):
    """Extract limited number of messages from a chat."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]

            success = open_chat(page, chat_name)
            if not success:
                return {'status': 'error', 'message': f'Could not find chat: {chat_name}'}

            scroll_to_top_of_chat(page, max_scrolls=50)  # partial scroll for recent messages
            messages = extract_messages(page, max_messages=max_messages)
            browser.close()

            return {
                'status': 'success',
                'chat_name': chat_name or "First chat",
                'message_count': len(messages),
                'messages': messages
            }
    except Exception as e:
        print(f"❌ Error in extract_chat_messages: {e}")
        return {'status': 'error', 'message': str(e), 'chat_name': chat_name}


@celery_app.task(name='tasks.chat_extractor.discover_chats')
def discover_chats(timeout=60000):
    """Discover all chats from WhatsApp Web."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]

            page.wait_for_selector("#pane-side", timeout=timeout)
            page.wait_for_timeout(5000)  # pause for rendering

            chat_elements = []
            for _ in range(5):  # retry loop
                chat_elements = page.query_selector_all("div[data-testid='cell-frame-container']")
                if chat_elements:
                    break
                page.wait_for_timeout(2000)

            if not chat_elements:
                page.screenshot(path="debug_chats.png")
                return {"status": "error", "message": "No chats found. Screenshot saved to debug_chats.png"}

            chats = []
            for chat in chat_elements:
                try:
                    name_el = chat.query_selector('span[title]')
                    name = name_el.inner_text().strip() if name_el else ""

                    last_msg_el = chat.query_selector('div._21Ahp span.selectable-text')
                    last_msg = last_msg_el.inner_text().strip() if last_msg_el else ""

                    time_el = chat.query_selector('div._3pkkz span._2fod')
                    last_time = time_el.inner_text().strip() if time_el else ""

                    unread_count = 0
                    unread_el = chat.query_selector('div._1pJ9J span[aria-label]')
                    if unread_el:
                        match = re.search(r"\d+", unread_el.get_attribute("aria-label"))
                        if match:
                            unread_count = int(match.group(0))

                    chats.append({
                        "name": name,
                        "last_message": last_msg,
                        "last_time": last_time,
                        "unread_count": unread_count
                    })
                except Exception as e:
                    print(f"❌ Error parsing chat: {e}")
                    continue

            browser.close()
            return {"status": "success", "chats": chats}

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ==========================
# Standalone Test
# ==========================
if __name__ == "__main__":
    from pathlib import Path
    import json
    from datetime import datetime
    import os

    CHAT_EXPORT_DIR = "exported_chats"
    Path(CHAT_EXPORT_DIR).mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.pages[0]

        success = open_chat(page, chat_name=None)
        if success:
            print("✅ Successfully opened the first chat")
            scroll_count = scroll_to_top_of_chat(page)
            print(f"📜 Scrolled {scroll_count} times to load messages")
            messages = extract_messages(page)
            print(f"Extracted {len(messages)} messages: {messages[:5]}")

            # Save JSON
            chat_header = page.query_selector('#main header span[dir="auto"]')
            chat_name_actual = chat_header.inner_text().strip() if chat_header else "UnknownChat"
            safe_name = re.sub(r'[^a-z0-9]', '_', chat_name_actual.lower())[:50]
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{safe_name}_{timestamp}_chat.json"
            filepath = os.path.join(CHAT_EXPORT_DIR, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    "chat_name": chat_name_actual,
                    "extracted_at": datetime.now().isoformat(),
                    "message_count": len(messages),
                    "messages": messages
                }, f, indent=2, ensure_ascii=False)

            print(f"✅ Chat saved → {filepath}")

        else:
            print("❌ Failed to open the first chat")
        browser.close()

