from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9240"  # Chrome DevTools port where WhatsApp is running

def get_recent_chats():
    js_script = """
        (function() {
            return [...document.querySelectorAll("#pane-side > div > div > div > div")].map(chat => {
                const name = chat.querySelector("div._ak8l._ap1_ > div._ak8o")?.innerText?.trim() || "";
                const lastMsg = chat.querySelector("div._ak8l._ap1_ > div._ak8j > div._ak8k")?.innerText?.trim() || "";
                const time = chat.querySelector("div._ak8l._ap1_ > div._ak8o > div._ak8i.false")?.innerText?.trim() || "";
                const unreadAria = chat.querySelector("div._ak8l._ap1_ > div._ak8j > div._ak8i span[aria-label]")?.getAttribute("aria-label") || "";
                return { name, lastMsg, time, unread: unreadAria };
            });
        })();
    """

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(CDP_URL)
            context = browser.contexts[0]
            page = context.pages[0]
            # Wait for pane-side to ensure the chat list is loaded
            page.wait_for_selector("#pane-side", timeout=10000)
            print(f"Page URL: {page.url}")  # Debug the current page
            print(f"Executing JS: {js_script}")  # Debug the exact script
            chats = page.evaluate(js_script)
            print(f"Fetched chats: {chats}")  # Debug the result
            browser.close()
            return chats
    except Exception as e:
        print(f"Playwright error: {str(e)}")
        raise

if __name__ == "__main__":
    data = get_recent_chats()
    for chat in data:
        print(chat)