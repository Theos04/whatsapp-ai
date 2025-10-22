import time
import json
import requests

REMOTE_DEBUG_URL = "http://127.0.0.1:9240"
WHATSAPP_URL = "https://web.whatsapp.com"

# ---------- Updated JS Payloads ----------
JS_UNREAD_OPENER = r"""
(async () => {
    console.log("Starting unread chat opener...");
    try {
        // Helper to wait for an element
        async function waitForElement(selector, timeout = 20000) {
            console.log(`Waiting for element: ${selector}`);
            const start = Date.now();
            while (Date.now() - start < timeout) {
                const el = document.querySelector(selector);
                if (el) {
                    console.log(`Found element: ${selector}`);
                    return el;
                }
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            console.error(`Element not found: ${selector}`);
            return null;
        }

        // Step 1: Try to find and click the unread filter button
        console.log("Searching for unread filter button...");
        let unreadButton = document.getElementById('unread-filter');
        if (!unreadButton) {
            unreadButton = document.querySelector('button[aria-label*="unread" i], button[title*="unread" i], button span[title*="unread" i], div[aria-label*="unread" i], div[title*="unread" i], button._ak0l, div._ak0l');
            if (!unreadButton) {
                console.error("Unread filter button not found! Tried ID 'unread-filter' and fallback selectors.");
                console.log("Available buttons/divs:", Array.from(document.querySelectorAll('button, div[aria-label], div[title], ._ak0l')).slice(0, 10).map(el => ({
                    tag: el.tagName,
                    id: el.id,
                    ariaLabel: el.getAttribute('aria-label'),
                    title: el.getAttribute('title'),
                    class: el.className,
                    text: el.innerText.slice(0, 50)
                })));
                return { success: false, error: 'Unread filter button not found', debug: 'Check available buttons/divs in console' };
            }
        }

        console.log("Clicking unread filter button...");
        try {
            unreadButton.click();
            console.log("Unread filter clicked.");
        } catch (err) {
            console.error("Error clicking unread filter button:", err.message);
            return { success: false, error: `Failed to click unread filter: ${err.message}`, debug: 'Check console for stack trace' };
        }

        // Step 2: Wait for the chat list to update
        console.log("Waiting for chat list to update...");
        await new Promise(resolve => setTimeout(resolve, 5000));

        // Step 3: Check if there are any chats in the list
        const chatList = document.querySelector('#pane-side');
        if (!chatList || chatList.innerHTML.includes('No chats')) {
            console.warn("No chats found in the chat list. Possibly no unread chats.");
            return { success: false, error: 'No unread chats available', debug: 'Check chat list in #pane-side' };
        }

        // Step 4: Find the search input box
        console.log("Searching for search input box...");
        const inputBox = await waitForElement('div[role="textbox"][contenteditable="true"], div[aria-label*="search" i][contenteditable="true"], div[contenteditable="true"], div[role="search"], input[type="text"], textarea, div._akbu, div._ak8n');
        if (!inputBox) {
            console.error("Search input box not found! Tried multiple selectors.");
            console.log("Available inputs:", Array.from(document.querySelectorAll('div[contenteditable="true"], div[role="textbox"], div[role="search"], input, textarea, ._akbu, ._ak8n')).slice(0, 10).map(el => ({
                tag: el.tagName,
                ariaLabel: el.getAttribute('aria-label'),
                role: el.getAttribute('role'),
                id: el.id,
                class: el.className
            })));
            return { success: false, error: 'Search input box not found', debug: 'Check available inputs in console' };
        }

        // Step 5: Focus and clear the search box
        console.log("Focusing search input...");
        try {
            inputBox.focus();
            const range = document.createRange();
            range.selectNodeContents(inputBox);
            range.deleteContents();
        } catch (err) {
            console.error("Error focusing/clearing search input:", err.message);
            return { success: false, error: `Failed to focus search input: ${err.message}`, debug: 'Check console for stack trace' };
        }

        // Step 6: Simulate Enter keypress to select the first unread chat
        console.log("Simulating Enter keypress...");
        try {
            inputBox.dispatchEvent(new KeyboardEvent("keydown", {
                bubbles: true,
                cancelable: true,
                key: "Enter",
                code: "Enter",
                keyCode: 13,
                which: 13
            }));
            console.log("Enter keypress simulated to select first unread chat.");
        } catch (err) {
            console.error("Error simulating Enter keypress:", err.message);
            return { success: false, error: `Failed to simulate Enter keypress: ${err.message}`, debug: 'Check console for stack trace' };
        }

        // Step 7: Verify chat selection
        console.log("Verifying chat selection...");
        await new Promise(resolve => setTimeout(resolve, 2000));
        const activeChat = await waitForElement('div[aria-selected="true"], div[aria-current="true"], div._ak8i, div._ak8l, div._ak8n');
        if (activeChat) {
            console.log("First unread chat successfully selected:", activeChat);
            return { success: true, selectedChat: true };
        } else {
            console.error("No chat selected! Possible issues: no unread chats or Enter keypress failed.");
            console.log("Chat pane state:", document.querySelector('#pane-side')?.innerHTML.substring(0, 200) || "No #pane-side found");
            return { success: false, error: 'No chat selected', debug: 'Check chat pane state in console' };
        }
    } catch (err) {
        console.error("Unexpected error in unread chat opener:", err.message, err.stack);
        return { success: false, error: `JavaScript error: ${err.message}`, debug: 'Check console for stack trace' };
    }
})();
"""

JS_EXTRACTOR = r"""
(async () => {
    console.log("Starting message extractor...");
    try {
        // Helper to wait for an element
        async function waitForElement(selector, timeout = 20000) {
            console.log(`Waiting for element: ${selector}`);
            const start = Date.now();
            while (Date.now() - start < timeout) {
                const el = document.querySelector(selector);
                if (el) return el;
                await new Promise(resolve => setTimeout(resolve, 100));
            }
            return null;
        }

        const chat = await waitForElement("#main");
        if (!chat) {
            console.error("❌ Chat window not found. Open a chat first.");
            console.log("Sidebar state:", document.querySelector('#pane-side')?.innerHTML.substring(0, 200) || "No #pane-side found");
            return { success: false, error: 'Chat window not found', messages: [] };
        }

        const messages = [];
        const seenMessageIds = new Set();
        const bubbles = chat.querySelectorAll("div[role='row'], div._akbu, div._ak8n");
        console.log(`Found ${bubbles.length} message bubbles`);

        bubbles.forEach((bubble, index) => {
            console.log(`Processing bubble ${index + 1}`);
            const msgObj = {};

            // Get a unique identifier for the message (e.g., data-id attribute or text content hash)
            const messageId = bubble.getAttribute('data-id') || bubble.innerText.slice(0, 50);
            if (seenMessageIds.has(messageId)) {
                console.log(`Skipping duplicate message ${index + 1} with ID: ${messageId}`);
                return;
            }
            seenMessageIds.add(messageId);

            // 1️⃣ TEXT MESSAGE
            const textEl = bubble.querySelector("div.copyable-text span.selectable-text span, span.selectable-text, div._akbu, span._ak8n");
            if (textEl && textEl.innerText.trim()) {
                msgObj.type = "text";
                msgObj.text = textEl.innerText.trim();
            }

            // 2️⃣ IMAGE MESSAGE
            const imgs = Array.from(bubble.querySelectorAll("img")).filter((img) => {
                const src = img.src || "";
                return (
                    src.includes("mmg.whatsapp.net") || // WhatsApp CDN
                    src.startsWith("blob:") ||         // Temporary blob
                    src.includes("/media/")            // Internal media path
                ) && !src.includes("data:image/gif"); // Exclude emoji GIFs
            });

            if (imgs.length > 0) {
                msgObj.type = "image";
                msgObj.images = imgs.map((i) => ({
                    src: i.src,
                    alt: i.alt || null,
                }));
            }

            // 3️⃣ TIMESTAMP
            const timeEl = bubble.querySelector("span[data-pre-plain-text], div._akbu > span:not(.selectable-text), span._ak8n:not(.selectable-text), div[data-testid='msg-time']");
            if (timeEl) {
                msgObj.timestamp = timeEl.getAttribute("data-pre-plain-text") || timeEl.innerText.trim() || "";
            }

            if (Object.keys(msgObj).length > 0) {
                console.log(`Message ${index + 1}:`, msgObj);
                messages.push(msgObj);
            }
        });

        console.log("✅ Extracted messages:", messages);
        return { success: true, messages };
    } catch (err) {
        console.error("Unexpected error in message extractor:", err.message, err.stack);
        return { success: false, error: `JavaScript error: ${err.message}`, messages: [] };
    }
})();
"""

# ---------- Chrome DevTools Protocol Implementation ----------
class ChromeTab:
    """Simple Chrome DevTools Protocol tab connector"""
    
    def __init__(self, ws_url):
        import websocket
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0
        
    def connect(self):
        """Connect to the tab via WebSocket"""
        import websocket
        try:
            self.ws = websocket.create_connection(self.ws_url, timeout=20)
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            raise
        
    def send_command(self, method, params=None):
        """Send a command to Chrome DevTools"""
        self.msg_id += 1
        message = {
            "id": self.msg_id,
            "method": method,
            "params": params or {}
        }
        self.ws.send(json.dumps(message))
        responses = []
        while True:
            try:
                response = json.loads(self.ws.recv())
                responses.append(response)
                if "id" in response and response["id"] == self.msg_id:
                    return responses
            except Exception as e:
                print(f"Error receiving DevTools response: {e}")
                return responses
    
    def evaluate_js(self, script):
        """Evaluate JavaScript and return the result"""
        try:
            responses = self.send_command("Runtime.evaluate", {
                "expression": script,
                "returnByValue": True,
                "awaitPromise": True
            })
            for response in responses:
                print(f"Raw DevTools response: {json.dumps(response, indent=2)}")
                if "id" in response and "result" in response and "result" in response["result"]:
                    return response["result"]["result"].get("value")
                elif "error" in response:
                    print(f"JavaScript error from DevTools: {response.get('error')}")
            print("No result or error returned from JavaScript execution")
            return None
        except Exception as e:
            print(f"Error executing JavaScript: {e}")
            return None
    
    def close(self):
        """Close the WebSocket connection"""
        if self.ws:
            self.ws.close()

# ---------- Helper Functions ----------
def get_whatsapp_tab():
    """Find WhatsApp tab using direct HTTP request"""
    try:
        print("\n🔍 Fetching tabs from Chrome DevTools...")
        response = requests.get(f"{REMOTE_DEBUG_URL}/json")
        
        if response.status_code != 200:
            print(f"❌ Failed to connect to Chrome DevTools on port 9240")
            print(f"   Status code: {response.status_code}")
            return None
            
        tabs_data = response.json()
        
        print(f"✅ Found {len(tabs_data)} tab(s)")
        
        for i, tab_data in enumerate(tabs_data):
            title = tab_data.get('title', 'No title')
            url = tab_data.get('url', 'No URL')
            tab_type = tab_data.get('type', 'unknown')
            
            print(f"\n  Tab {i+1}:")
            print(f"    Title: {title}")
            print(f"    URL: {url}")
            print(f"    Type: {tab_type}")
            
            if "web.whatsapp.com" in url.lower():
                print(f"\n✅ Found WhatsApp tab!")
                return tab_data
        
        print("\n❌ No WhatsApp Web tab found in the browser")
        return None
        
    except requests.exceptions.ConnectionError:
        print(f"❌ Could not connect to Chrome DevTools at {REMOTE_DEBUG_URL}")
        print("   Make sure Chrome is running with --remote-debugging-port=9240")
        return None
    except Exception as e:
        print(f"❌ Error fetching tabs: {e}")
        import traceback
        traceback.print_exc()
        return None

# ---------- Main Workflow ----------
def main():
    print("=" * 70)
    print("🤖 WhatsApp Chat Orchestrator")
    print("=" * 70)
    
    try:
        import websocket
    except ImportError:
        print("\n❌ Missing required package: websocket-client")
        print("Install it with: pip install websocket-client")
        return
    
    try:
        # Find WhatsApp tab
        tab_data = get_whatsapp_tab()
        
        if not tab_data:
            print("\n" + "=" * 70)
            print("❌ TROUBLESHOOTING")
            print("=" * 70)
            print("\n1. Start Chrome with remote debugging AND allow origins:")
            print('   & "D:\\Win_1130649_chrome-win\\chrome-win\\chrome.exe" `')
            print('     --user-data-dir="C:\\Users\\mailt\\AppData\\Local\\Chromium\\User Data\\Default" `')
            print('     --remote-debugging-port=9240 `')
            print('     --remote-allow-origins=* `')
            print('     --start-maximized "https://web.whatsapp.com"')
            print("\n2. Make sure WhatsApp Web is logged in")
            print("\n3. Verify Chrome DevTools is accessible:")
            print(f"   Open in browser: {REMOTE_DEBUG_URL}/json")
            print("=" * 70)
            return
        
        ws_url = tab_data.get('webSocketDebuggerUrl')
        if not ws_url:
            print("❌ No WebSocket URL found for the tab")
            return
        
        print(f"\n🔌 Connecting to tab via WebSocket...")
        print(f"   URL: {ws_url}")
        
        tab = ChromeTab(ws_url)
        tab.connect()
        print("✅ Connected successfully!")
        
        # Enable Runtime domain
        print("\n🚀 Enabling Runtime domain...")
        tab.send_command("Runtime.enable")
        
        # Inject unread opener
        print("\n🔧 Injecting unread chat opener...")
        opener_result = tab.evaluate_js(JS_UNREAD_OPENER)
        print(f"Unread opener result: {opener_result}")
        
        if opener_result is None:
            print("\n⚠️ Unread chat opener returned None. Check browser console for JavaScript errors.")
            print("Possible reasons:")
            print("  • JavaScript execution failed (e.g., syntax error or timeout)")
            print("  • WhatsApp Web DOM structure changed")
            print("  • No unread chats available")
            print("  • DevTools Protocol issue")
            print("\nDebug steps:")
            print("  1. Open Chrome DevTools (F12) on WhatsApp Web tab")
            print("  2. Check Console for logs from 'Starting unread chat opener...'")
            print("  3. Inspect DOM for updated selectors (unread button, search input, active chat)")
            print("  4. Verify unread chats exist in WhatsApp Web")
            tab.close()
            return
        elif not opener_result.get('success'):
            print(f"\n⚠️ Failed to open unread chat: {opener_result.get('error')}")
            print(f"Debug info: {opener_result.get('debug', 'No additional debug info')}")
            print("Check the browser console for detailed logs.")
            tab.close()
            return

        # Wait for chat to open
        print("⏳ Waiting 10 seconds for chat to open...")
        time.sleep(10)

        # Extract messages
        print("\n📥 Extracting messages from chat...")
        extract_result = tab.evaluate_js(JS_EXTRACTOR)
        
        if extract_result is None:
            print("\n⚠️ Message extraction returned None. Check browser console for JavaScript errors.")
            print("Possible reasons:")
            print("  • JavaScript execution failed")
            print("  • Chat window not loaded")
            print("  • WhatsApp Web DOM structure changed")
        elif not isinstance(extract_result, dict):
            print(f"\n⚠️ Unexpected extract result format: {extract_result}")
            print("Expected a dictionary with 'success' and 'messages' keys.")
        elif extract_result.get('success'):
            messages = extract_result.get('messages', [])
            print(f"\n✅ Successfully extracted {len(messages)} message(s)!")
            if messages:
                print("\n" + "=" * 70)
                print("MESSAGES:")
                print("=" * 70)
                print(json.dumps(messages, indent=2, ensure_ascii=False))
                print("=" * 70)
            else:
                print("\n⚠️ No messages found in the chat.")
        else:
            print(f"\n⚠️ Failed to extract messages: {extract_result.get('error', 'Unknown error')}")
            print("Possible reasons:")
            print("  • No chat is currently open")
            print("  • No messages in the chat")
            print("  • Chat window hasn't fully loaded")
            print("  • WhatsApp Web DOM structure changed")
            print("Check the browser console for detailed logs.")
        
        # Close connection
        print("\n🔌 Closing connection...")
        tab.close()
        print("✅ Disconnected")
            
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("✨ Done!")
    print("=" * 70)

if __name__ == "__main__":
    main()