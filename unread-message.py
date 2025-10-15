from playwright.sync_api import sync_playwright
import json

CDP_URL = "http://127.0.0.1:9240"  # Chrome DevTools port where WhatsApp is running

def open_and_download_unread_chat():
    """Open the first unread WhatsApp chat and download its messages as JSON."""
    js_open_unread = """
        (function() {
            // Step 1: Click the unread filter button
            const unreadButton = document.getElementById('unread-filter');
            if (!unreadButton) {
                console.error("Unread filter button not found! Verify the button ID is 'unread-filter'.");
                console.log("Available IDs:", Array.from(document.querySelectorAll('[id]')).map(el => el.id));
                throw new Error("Unread filter button not found");
            }
            unreadButton.click();
            console.log("Unread filter clicked...");

            // Step 2: Wait for the chat list to update
            setTimeout(function() {
                // Step 3: Find the search input box to simulate selection
                const inputBox = document.querySelector('div[aria-label="Search input textbox"][contenteditable="true"]');
                if (!inputBox) {
                    console.error("Search input box not found! Verify the selector 'div[aria-label=\\"Search input textbox\\"][contenteditable=\\"true\\"]'.");
                    throw new Error("Search input box not found");
                }

                // Step 4: Focus the search box and simulate Enter to select the first chat
                inputBox.focus();
                console.log("Search input focused...");

                // Optional: Clear the search box
                const range = document.createRange();
                range.selectNodeContents(inputBox);
                range.deleteContents();

                // Step 5: Simulate Enter keypress to select the first chat in the filtered list
                inputBox.dispatchEvent(new KeyboardEvent("keydown", {
                    bubbles: true,
                    cancelable: true,
                    key: "Enter",
                    code: "Enter",
                    keyCode: 13,
                    which: 13
                }));
                console.log("Enter keypress simulated to select first unread chat!");

                // Step 6: Verify selection by checking the active chat
                setTimeout(function() {
                    const activeChat = document.querySelector('div[aria-selected="true"]');
                    if (!activeChat) {
                        console.error("No chat selected! Possible issues: no unread chats or Enter keypress failed.");
                        console.log("Current DOM state for chat list (first 200 chars):", 
                                    document.querySelector('#pane-side')?.innerHTML.substring(0, 200) || "No #pane-side found");
                        throw new Error("No unread chat selected");
                    }
                    console.log("First unread chat successfully selected:", activeChat);
                }, 1000);
            }, 2000);
        })();
    """

    js_extract_messages = """
        (function() {
            // 1. Get Chat Name (from header)
            const chatHeaderEl = document.querySelector('#main header span[dir="auto"]');
            const chatName = chatHeaderEl ? chatHeaderEl.textContent.trim() : 'unknown_chat';
            const safeFileName = chatName.replace(/[^a-z0-9]/gi, '_').toLowerCase();

            // 2. Collect All Messages
            const messageDivs = [...document.querySelectorAll('div[data-pre-plain-text]')];

            const extracted = messageDivs.map(div => {
                const meta = div.getAttribute('data-pre-plain-text') || '';

                const timeMatch = meta.match(/\\[(.*?)\\]/); // Extract timestamp
                const rawTimestamp = timeMatch ? timeMatch[1] : null;
                const timestamp = rawTimestamp ? new Date(rawTimestamp).toISOString() : null;

                const senderMatch = meta.match(/\\] (.*?):/);
                const sender = senderMatch ? senderMatch[1].trim() : 'Unknown';

                const textEl = div.querySelector('span.selectable-text');
                const text = textEl ? textEl.innerText.trim() : '';

                return {
                    sender,
                    text,
                    timestamp,
                    fromBusiness: sender.toLowerCase().includes('harsh')
                };
            }).filter(m => m.text);

            // 3. Prepare JSON for download
            const jsonString = JSON.stringify(extracted, null, 2);
            const blob = new Blob([jsonString], { type: "application/json" });
            const url = URL.createObjectURL(blob);

            const downloadLink = document.createElement("a");
            downloadLink.href = url;
            downloadLink.download = `${safeFileName}_chat.json`;
            document.body.appendChild(downloadLink);
            downloadLink.click();
            document.body.removeChild(downloadLink);

            console.log(`✅ Saved ${extracted.length} messages from: "${chatName}"`);
            return { chatName, messageCount: extracted.length };
        })();
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            
            # Wait for WhatsApp chat pane to load
            page.wait_for_selector("#pane-side", timeout=10000)
            print(f"Page URL: {page.url}")  # Debug the current page

            # Step 1: Open the first unread chat
            print("Executing script to open unread chat...")
            page.evaluate(js_open_unread)

            # Step 2: Wait for chat to load
            page.wait_for_selector("#main header", timeout=10000)
            print("Chat opened, extracting messages...")

            # Step 3: Extract and download messages
            result = page.evaluate(js_extract_messages)
            print(f"Extracted messages: {result}")

            browser.close()
            return result
    except Exception as e:
        print(f"Playwright error: {str(e)}")
        raise

if __name__ == "__main__":
    result = open_and_download_unread_chat()
    print(f"Result: {result}")