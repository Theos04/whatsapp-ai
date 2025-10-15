import pychrome
import time
import json
import sys

# Connect to the running Chrome instance
browser = pychrome.Browser(url="http://127.0.0.1:9240")

# Find the WhatsApp Web tab
def find_whatsapp_tab():
    for t in browser.list_tab():
        try:
            if t.url and "web.whatsapp" in t.url:
                return t
            if t.title and "WhatsApp" in t.title:
                return t
        except Exception:
            continue
    tabs = browser.list_tab()
    if not tabs:
        raise RuntimeError("No tabs found on remote Chrome.")
    return tabs[0]

tab = find_whatsapp_tab()
print("✅ Using tab:", getattr(tab, "url", ""), getattr(tab, "title", ""))

# Start the tab (attach)
tab.start()

# Enable required domains
tab.DOM.enable()
tab.Runtime.enable()
tab.Page.enable()

# Helper to evaluate JS and return value
def eval_js(expression, timeout=8):
    try:
        res = tab.Runtime.evaluate(
            expression=expression,
            returnByValue=True,
            awaitPromise=True,
            timeout=timeout
        )
        return res.get("result", {}).get("value", None)
    except Exception as e:
        print("⚠️ eval_js error:", e)
        return None

# Ensure WhatsApp chat list container exists
exists = eval_js('!!document.querySelector("#pane-side > div > div > div")')
if not exists:
    print("❌ ERROR: #pane-side not found. Please open WhatsApp Web and ensure the chat list is visible.")
    tab.stop()
    sys.exit(1)

print("✅ Found chat container. Starting incremental scroll and capture...")

# Scroll to load all chats
max_iterations = 200
sleep_between_scrolls = 0.45
stable_rounds_required = 3

prev_count = -1
stable_rounds = 0
iteration = 0

get_count_js = 'document.querySelectorAll("#pane-side > div > div > div > div").length'

while iteration < max_iterations and stable_rounds < stable_rounds_required:
    iteration += 1
    eval_js('var p=document.querySelector("#pane-side > div > div > div"); if(p){p.scrollBy(0,1000);}')
    time.sleep(sleep_between_scrolls)

    curr_count = eval_js(get_count_js)
    try:
        curr_count = int(curr_count)
    except:
        curr_count = -1

    print(f"📜 Scroll {iteration}: {curr_count} chats visible")

    if curr_count == prev_count:
        stable_rounds += 1
    else:
        stable_rounds = 0
        prev_count = curr_count

print("✅ Finished scrolling. Extracting structured chat data...")

# Main extraction JS (your provided logic)
extract_js = '''
(function(){
  const chats = [...document.querySelectorAll("#pane-side > div > div > div > div")].map(chat => {
    const name =
      chat.querySelector("div._ak8l._ap1_ > div._ak8o")?.innerText?.trim() || "";
    const lastMsg =
      chat.querySelector("div._ak8l._ap1_ > div._ak8j > div._ak8k")?.innerText?.trim() || "";
    const time =
      chat.querySelector("div._ak8l._ap1_ > div._ak8o > div._ak8i.false")?.innerText?.trim() || "";
    const unreadAria =
      chat.querySelector("div._ak8l._ap1_ > div._ak8j > div._ak8i span[aria-label]")?.getAttribute("aria-label") || "";
    return { name, lastMsg, time, unread: unreadAria };
  });
  return chats;
})()
'''

chat_data = eval_js(extract_js)

# Save to JSON
if chat_data and isinstance(chat_data, list):
    with open("chats_detailed.json", "w", encoding="utf-8") as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)
    print(f"💾 Saved {len(chat_data)} chats to chats_detailed.json")
else:
    print("⚠️ No structured chat data extracted (empty or null).")

# Stop and detach
tab.stop()
print("✅ Done.")
