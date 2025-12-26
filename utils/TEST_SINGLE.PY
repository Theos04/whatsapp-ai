import time
import json
import requests
import websocket
import argparse
import psutil
from typing import List, Set, Optional
import gspread
from google.oauth2.service_account import Credentials
import hashlib
from datetime import datetime

CREDENTIALS_PATH = r"E:\whatsapp-ai\credentials.json"
SHEET_ID = "1q1k4rFwcLVy7DQLeQQ8Pqt-eqRFPI6E39Jd3GrGxHo4"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# === SHEET SETUP ===
SHEET_CONFIG = {
    "Contacts": ["UID", "Name", "Number", "Notes"],
    "Leads": ["UID", "leadsID", "Source", "Status", "follow-up", "created-date"],
    "Calls": ["UID", "CallID", "date", "caller-name", "task-name", "description", "status", "priority", "action", "tags", "follow-up", "whatsapp-message", "product-details"],
    "Whatsapp": ["UID", "messageID", "date", "time", "message from you", "message from them"]
}

# Parse command-line arguments
parser = argparse.ArgumentParser(description="WhatsApp single chat automation with Google search")
parser.add_argument("--port", type=int, default=9240, help="Chrome DevTools port (default: 9240)")
args = parser.parse_args()
REMOTE_DEBUG_URL = f"http://127.0.0.1:{args.port}"
WHATSAPP_URL = "https://web.whatsapp.com"
GOOGLE_URL = "https://www.google.com"

# ---------- JS Scripts ----------
JS_UNREAD_OPENER = r"""
(async () => {
    console.log("Starting unread chat opener...");
    try {
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

        console.log("Waiting for chat list to update...");
        await new Promise(resolve => setTimeout(resolve, 5000));

        const chatList = document.querySelector('#pane-side');
        if (!chatList || chatList.innerHTML.includes('No chats')) {
            console.warn("No chats found in the chat list. Possibly no unread chats.");
            return { success: false, error: 'No unread chats available', debug: 'Check chat list in #pane-side' };
        }

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

        console.log("Verifying chat selection...");
        await new Promise(resolve => setTimeout(resolve, 2000));
        const activeChat = await waitForElement('div[aria-selected="true"], div[aria-current="true"], div._ak8i, div._ak0l, div._ak8n');
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
  console.log("Starting enhanced WhatsApp message extractor (copyable-text based)...");

  try {
    // Helper: wait for #main chat to load
    async function waitForElement(selector, timeout = 20000) {
      console.log(`⏳ Waiting for element: ${selector}`);
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
      return { success: false, error: "Chat window not found", messages: [] };
    }

    const selector = "#main div.copyable-text";
    const divs = chat.querySelectorAll(selector);

    if (divs.length === 0) {
      console.warn("⚠️ No messages with 'copyable-text' found.");
      return { success: false, error: "No messages found", messages: [] };
    }

    console.log(`✅ Found ${divs.length} message elements`);
    const messages = [];

    divs.forEach((div, index) => {
      const msgObj = {};

      // Extract [time, date, sender] from data-pre-plain-text
      const timeAttr = div.getAttribute("data-pre-plain-text");
      if (timeAttr) {
        // Example: "[12:34 PM, 10/24/2025] John: "
        const match = timeAttr.match(/\[(.*?)\]/);
        msgObj.time = match ? match[1] : "N/A";
      }

      // Extract message text
      msgObj.text = div.innerText.trim();

      // Optional: direction inference (in/out) based on parent classes
      const parent = div.closest("div.message-in, div.message-out");
      msgObj.direction = parent
        ? parent.classList.contains("message-in")
          ? "in"
          : "out"
        : "unknown";

      messages.push(msgObj);
      console.log(`#${index + 1} [${msgObj.direction}] 🕒 ${msgObj.time} → ${msgObj.text}`);
    });

    console.log("\n📊 Extracted messages summary:");
    console.table(messages);

    return { success: true, messages };
  } catch (err) {
    console.error("❌ Unexpected error in message extractor:", err.message);
    return { success: false, error: err.message, messages: [] };
  }
})();

"""

JS_OPEN_IMAGE_AND_SEARCH = r"""
(async () => {
  console.log("🚀 Starting image opener + conditional custom search + next image navigation...");

  async function waitForElement(selector, timeout = 20000) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const el = document.querySelector(selector);
      if (el) return el;
      await new Promise(r => setTimeout(r, 100));
    }
    return null;
  }

  // Step 1: Collect all images in chat
  const images = Array.from(document.querySelectorAll("img")).filter(img =>
    (img.src.includes("mmg.whatsapp.net") || img.src.startsWith("blob:") || img.src.includes("/media/")) &&
    !img.src.includes("data:image/gif")
  );

  if (images.length === 0) {
    console.warn("❌ No images found in chat.");
    return { success: false, error: "No images found", totalImages: 0, results: [] };
  }

  console.log(`🖼️ Found ${images.length} images.`);

  // Step 2: Click the first image to open viewer
  const firstImage = images[0];
  console.log(`\n🖼️ Opening image 1/${images.length}:`, firstImage.src);
  firstImage.click();
  await new Promise(r => setTimeout(r, 12000)); // Wait for viewer to open

  // Step 3: Confirm viewer opened
  const viewer = await waitForElement(
    'div[aria-label*="media viewer" i], div[data-testid*="media-viewer"], div[class*="media-viewer"], div[role="dialog"], div[aria-label*="image" i], div[aria-label*="photo" i], div[aria-label*="viewer" i], div._a3gq',
    15000
  );

  if (!viewer) {
    console.error("❌ Image viewer did not open.");
    return { success: false, error: "Viewer not opened", totalImages: images.length, results: [] };
  }

  console.log("✅ Image viewer opened.");

  // Step 4: Process images in the viewer
  const results = [];
  let currentIndex = 1;

  while (currentIndex <= images.length) {
    console.log(`\n📸 Processing image ${currentIndex}/${images.length}`);
    const imgResult = { src: images[currentIndex - 1].src, success: true, buttonResults: [] };

    // Check container text for "you"
    const containerSelector = '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(4) > div > div > div:nth-child(1) > div > div.x16uhe5s.x78zum5.x1okw0bk.x15zctf7.x6s0dn4.xng8ra.x1280gxy';
    const container = await waitForElement(containerSelector, 5000);

    if (container && container.innerText.toLowerCase().includes("you")) {
      console.log("⚠️ Container contains 'you' — skipping custom search.");
      imgResult.buttonResults.push({ button: "skipped", reason: "Container contains 'you'" });
    } else {
      // Execute custom search buttons
      const selectors = [
        '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(4) > div > div > div:nth-child(1) > div > div.x16uhe5s.x78zum5.x1okw0bk.x15zctf7.x6s0dn4.xng8ra.x1280gxy.xqu7myx > div.x9ek82g.xzj7eog > div > div:nth-child(7) > button',
        '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(8) > div > ul > div > div:nth-child(1) > li > div > span',
        '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(3) > div > div > div > div > div > div > div.x78zum5.x8hhl5t.x13a6bvl.x13crsa5.x1gabggj.x18d9i69.xaso8d8.xp4054r.xuxw1ft > div > div:nth-child(2) > div > div.html-div.xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu.x18d9i69.x78zum5.xl56j7k.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x1so62im.x1syfmzz.x1ja2u2z.x1s928wv.x1j6awrg.x4eaejv.x1wsn0xg.x1r0yslu.x2q1x1w.xapdjt.xr6f91l.x5rv0tg.x1akc3lz.xikp0eg.x1xl5mkn.x1mfml39.x1l5mzlr.xgmdoj8.x1f1wgk5.x1x3ic1u.xfn3atn.x1pse0pq.x1yxkqql.x9f619.xt8t1vi.x1xc408v.x129tdwq.x15urzxu.x1vqgdyp.x4m7ku4.xyo0t3i.xb0esv5'
      ];

      for (const [i, selector] of selectors.entries()) {
        const el = document.querySelector(selector);
        if (el) {
          el.click();
          console.log(`✅ Clicked custom search button ${i + 1}`);
          imgResult.buttonResults.push({ button: `Button ${i + 1}`, success: true });
        } else {
          console.warn(`❌ Custom search button ${i + 1} not found`);
          imgResult.buttonResults.push({ button: `Button ${i + 1}`, success: false, error: "Button not found" });
        }
        await new Promise(r => setTimeout(r, 1000));
      }
    }

    results.push(imgResult);

    // Navigate to next image or exit
    if (currentIndex < images.length) {
      const nextBtnSelector = '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(4) > div > div > div:nth-child(1) > div > div.x9f619.x78zum5.xc8qplx.x1q0g3np.x6s0dn4.x1qughib.x4t50tc.x889kno.xr1496l > div.xauphjq.x1n2onr6.xzj7eog.x1p6ui73 > div > div > span';
      const nextBtn = await waitForElement(nextBtnSelector, 10000);

      if (nextBtn) {
        nextBtn.click();
        console.log("➡️ Navigated to next image.");
        await new Promise(r => setTimeout(r, 3000)); // Wait for next image to load
      } else {
        console.log("⚠️ Next button not found — stopping.");
        imgResult.success = false;
        imgResult.error = "Next button not found";
        break;
      }
    } else {
      console.log("🏁 Last image reached.");
    }

    currentIndex++;
  }

  console.log("✅ All images processed.");

  // Close the viewer
  const backBtnSelector = '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(4) > div > div > div:nth-child(1) > div > div.x16uhe5s.x78zum5.x1okw0bk.x15zctf7.x6s0dn4.xng8ra.x1280gxy.xqu7myx > div.x9ek82g.xzj7eog > div > div:nth-child(8) > button';
  const backBtn = await waitForElement(backBtnSelector, 5000);

  if (backBtn) {
    backBtn.click();
    console.log("⬅️ Closed viewer - returned to chat.");
  } else {
    console.warn("❌ Back button not found.");
  }

  return { success: true, totalImages: images.length, results };
})();
"""

JS_EXECUTE_CUSTOM_SEARCH = r"""
async function clickButtons() {
  const selectors = [
    '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(4) > div > div > div:nth-child(1) > div > div.x16uhe5s.x78zum5.x1okw0bk.x15zctf7.x6s0dn4.xng8ra.x1280gxy.xqu7myx > div.x9ek82g.xzj7eog > div > div:nth-child(7) > button',
    '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(8) > div > ul > div > div:nth-child(1) > li > div > span',
    '#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > span:nth-child(3) > div > div > div > div > div > div > div.x78zum5.x8hhl5t.x13a6bvl.x13crsa5.x1gabggj.x18d9i69.xaso8d8.xp4054r.xuxw1ft > div > div:nth-child(2) > div > div.html-div.xdj266r.x14z9mp.xat24cr.x1lziwak.xexx8yu.x18d9i69.x78zum5.xl56j7k.x1ejq31n.x18oe1m7.x1sy0etr.xstzfhl.x1so62im.x1syfmzz.x1ja2u2z.x1s928wv.x1j6awrg.x4eaejv.x1wsn0xg.x1r0yslu.x2q1x1w.xapdjt.xr6f91l.x5rv0tg.x1akc3lz.xikp0eg.x1xl5mkn.x1mfml39.x1l5mzlr.xgmdoj8.x1f1wgk5.x1x3ic1u.xfn3atn.x1pse0pq.x1yxkqql.x9f619.xt8t1vi.x1xc408v.x129tdwq.x15urzxu.x1vqgdyp.x4m7ku4.xyo0t3i.xb0esv5'
  ];

  for (const [i, selector] of selectors.entries()) {
    const el = document.querySelector(selector);
    if (el) {
      el.click();
      console.log(`✅ Clicked button ${i + 1}`);
    } else {
      console.warn(`❌ Button ${i + 1} not found`);
    }
    await new Promise(r => setTimeout(r, 1000)); // wait 1 second between clicks
  }
}

clickButtons();
"""

JS_GET_GOOGLE_SEARCH_DATA_PART_A = r"""
(async () => {
  console.log("🔍 Starting Google AI Mode Extractor (Wait → Poll → Click → Poll → Return)");

  const delay = (ms) => new Promise(res => setTimeout(res, ms));
  const aiButtonSelector =
    "#cnt > div.Fgyi2e.rZj61.caNvfd > div > div.YNk70c > div > div > div.beZ0tf.O1uzAe > div:nth-child(1) > div > div > a > div";

  // STEP 1: Wait 10s
  console.log("⏳ Waiting 10s for page stabilization...");
  await delay(10000);

  // STEP 2: Print any short AI summary if present (before click)
  const placeholderEl = document.querySelector(".LT6XE");
  if (placeholderEl) {
    console.log("👀 AI placeholder found before click:\n", placeholderEl.innerText.trim());
  } else {
    console.log("⚠️ No AI placeholder found before click.");
  }

  // STEP 3: Click AI Mode button
  const aiButton = document.querySelector(aiButtonSelector);
  if (!aiButton) {
    console.error("❌ AI Mode button not found.");
    return { success: false, reason: "Button not found" };
  }

  aiButton.scrollIntoView({ behavior: "smooth", block: "center" });
  await delay(1000);

  const safeClick = (el) => {
    try {
      el.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
      console.log("🟢 Clicked AI Mode button!");
      return true;
    } catch (err) {
      console.warn("⚠️ Click failed:", err.message);
      return false;
    }
  };

  let clicked = safeClick(aiButton);
  if (!clicked) {
    let parent = aiButton.parentElement;
    while (parent) {
      if (safeClick(parent)) {
        clicked = true;
        break;
      }
      parent = parent.parentElement;
    }
  }

  if (!clicked) {
    console.error("❌ Could not click AI Mode button or any parent.");
    return { success: false, reason: "Click failed" };
  }

  // STEP 4: Poll for full AI summary (.LT6XE)
  console.log("⏳ Polling for full AI summary...");
  let aiText = "";
  for (let i = 0; i < 30; i++) { // up to 30s
    const aiEl = document.querySelector(".LT6XE");
    if (aiEl) {
      const text = aiEl.innerText.trim();
      if (text.length > 100) { // ignore short "Listen" snippet
        aiText = text;
        console.log("🧠 Full AI summary loaded:\n", aiText);
        return { success: true, aiText };
      } else {
        console.log(`👀 AI summary too short (${text.length} chars), waiting...`);
      }
    } else {
      console.log("❌ .LT6XE not found yet, waiting...");
    }
    await delay(1000);
  }

  console.warn("⚠️ Timed out waiting for full AI summary.");
  return { success: false, reason: "Full AI summary not found" };
})();

"""

JS_GET_GOOGLE_SEARCH_DATA_PART_B = r"""
(async () => {
    console.log("Starting get-google-search-data-part-b...");
    try {
        await new Promise(resolve => setTimeout(resolve, 5000)); // Wait for page stability
        let element = null;
        for (let i = 0; i < 24; i++) {
            element = document.querySelector(
                "#cnt > div:nth-child(12) > div, " +
                "#rso > div, #search > div, div[data-ri]"
            );
            if (element) break;
            await new Promise(r => setTimeout(r, 500));
        }
        const result = {
            textContent: element ? element.innerText.trim() || "No text content" : "Element not found",
            htmlContent: element ? element.innerHTML.substring(0, 1000) || "No HTML content" : "No HTML content"
        };
        const images = Array.from(document.querySelectorAll('#islrg img, #rso img, #search img, div[data-ri] img')).slice(0, 5).map(img => ({
            src: img.src || "No src",
            alt: img.alt || "No alt text"
        }));
        console.log("Element text content:", result.textContent);
        console.log("Element HTML content:", result.htmlContent);
        console.log("Images:", images);
        return { success: !!element, data: { ...result, images } };
    } catch (err) {
        console.error("Error in get-google-search-data-part-b:", err.message, err.stack);
        return { success: false, error: `JavaScript error: ${err.message}`, data: {} };
    }
})();
"""

JS_CLICK_HEADER = r"""
(() => {
  const el = document.querySelector('#main > header > div.x78zum5.xdt5ytf.x1iyjqo2.xl56j7k.xeuugli.xtnn1bt.x9v5kkp.xmw7ebm.xrdum7p > div > div');
  if (el) {
    el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    console.log('✅ Clicked header element successfully');
    return { success: true };
  } else {
    console.error('❌ Element not found for selector');
    return { success: false, error: 'Header element not found' };
  }
})();
"""

JS_EXTRACT_CONTACT_INFO = r"""
(() => {
  const sectionSelector = "#app > div._aiwn._aiwm.app-wrapper-web.font-fix.os-win.x1px0edx.xoeyzqq > div > div.x78zum5.xdt5ytf.x5yr21d > div > div._aig-._as6h.x9f619.x1n2onr6.x5yr21d.x6ikm8r.x10wlt62.x17dzmu4.x1i1dayz.x2ipvbc.xjdofhw.xpilrb4.x1t7ytsu.x1vb5itz.x1c4vz4f.x2lah0s.x1oy9qf3.xwfak60.x5hsz1j.x17dq4o0.x10e4vud > span > div > span > div > div > section";
  const section = document.querySelector(sectionSelector);

  if (!section) {
    console.error("❌ Section not found");
    return { success: false, error: "Section not found" };
  }

  // Extract raw text (visible)
  const textContent = section.innerText || "";

  // Optionally, extract HTML (structured form)
  const htmlContent = section.innerHTML || "";

  console.log(`✅ Extracted section: ${textContent.length} chars of text`);
  return {
    success: true,
    textLength: textContent.length,
    text: textContent.trim(),
    html: htmlContent.trim()
  };
})();
"""

# ---------- Chrome DevTools Protocol ----------
class ChromeTab:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self.msg_id = 0

    def connect(self) -> bool:
        for attempt in range(5):
            try:
                self.ws = websocket.create_connection(self.ws_url, timeout=60)  # Increased timeout
                self.send_command("Page.enable")
                self.send_command("Runtime.enable")
                self.send_command("Log.enable")
                print(f"Connected to WebSocket: {self.ws_url}")
                return True
            except Exception as e:
                print(f"WebSocket connection attempt {attempt + 1} failed: {e}")
                time.sleep(5)
        print("Failed to connect to WebSocket after retries")
        return False

    def send_command(self, method: str, params: Optional[dict] = None) -> dict:
        self.msg_id += 1
        message = {"id": self.msg_id, "method": method, "params": params or {}}
        try:
            self.ws.send(json.dumps(message))
            start_time = time.time()
            while (time.time() - start_time) < 120:  # Increased timeout
                response_str = self.ws.recv()
                response = json.loads(response_str)
                if response.get("method") == "Log.entryAdded":
                    entry = response.get("params", {}).get("entry", {})
                    print(f"[BROWSER LOG - {entry.get('level')}]: {entry.get('text')}")
                if "id" in response and response["id"] == self.msg_id:
                    return response
            print(f"Timeout waiting for response to command {method}")
            return {"error": "Timeout waiting for response"}
        except Exception as e:
            print(f"Error sending command {method}: {e}")
            return {"error": f"Command failed: {str(e)}"}

    def evaluate_js(self, script: str) -> dict:
        for attempt in range(5):
            try:
                response = self.send_command("Runtime.evaluate", {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True,
                    "userGesture": True
                })
                if "result" in response and "result" in response["result"]:
                    return response["result"]["result"].get("value", {})
                elif "error" in response:
                    print(f"JS evaluation error: {response['error']}")
                    return {"success": False, "error": response["error"]}
                time.sleep(5)  # Increased delay
            except Exception as e:
                print(f"JS evaluation attempt {attempt + 1} failed: {e}")
                time.sleep(5)
        print("JS evaluation failed after retries")
        return {"success": False, "error": "JS evaluation failed after retries"}

    def close(self):
        if self.ws:
            try:
                self.ws.close()
                print("WebSocket connection closed.")
            except Exception as e:
                print(f"Error closing WebSocket: {e}")

# ---------- Helper Functions ----------
def check_chrome_running(port: int) -> bool:
    try:
        for proc in psutil.process_iter(['name', 'cmdline']):
            if proc.info['name'].lower() in ['chrome.exe', 'google chrome'] and proc.info['cmdline']:
                if any(f'--remote-debugging-port={port}' in arg for arg in proc.info['cmdline']):
                    print(f"Chrome found running with remote debugging on port {port}")
                    return True
        print(f"No Chrome instance found with remote debugging on port {port}")
        return False
    except Exception as e:
        print(f"Error checking Chrome processes: {e}")
        return False

def find_tab_by_url_or_title(keyword: str, max_retries: int = 10) -> Optional[ChromeTab]:
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{REMOTE_DEBUG_URL}/json", timeout=10)
            tabs = response.json()
            print(f"Available tabs: {len(tabs)} found")
            print("Tab details:", json.dumps([{
                'id': tab.get('id'),
                'url': tab.get('url', 'No URL'),
                'title': tab.get('title', 'No title'),
                'ws_url': tab.get('webSocketDebuggerUrl', 'No WebSocket')
            } for tab in tabs], indent=2))
            matching_tabs = [
                tab for tab in tabs
                if tab.get('type') == 'page' and
                (keyword.lower() in (tab.get('url') or "").lower() or
                 keyword.lower() in (tab.get('title') or "").lower()) and
                not tab.get('url', '').startswith('https://accounts.google.com')
            ]
            if not matching_tabs:
                print(f"No tab found for '{keyword}'. Retrying...")
                time.sleep(5)
                continue

            for tab in sorted(matching_tabs, key=lambda x: x.get('id', '')):
                ws_url = tab.get('webSocketDebuggerUrl')
                if ws_url:
                    tab_conn = ChromeTab(ws_url)
                    if tab_conn.connect():
                        print(f"Connected to tab: {tab.get('url')} (Title: {tab.get('title')})")
                        return tab_conn
                else:
                    print(f"No WebSocket URL for tab: {tab.get('url')} (Title: {tab.get('title')})")
            print(f"No connectable tab found for '{keyword}'.")
            time.sleep(5)
        except Exception as e:
            print(f"Error finding tab (attempt {attempt + 1}): {e}")
            time.sleep(5)
    print(f"Failed to find tab for '{keyword}' after {max_retries} retries")
    print("Please ensure WhatsApp Web is open at https://web.whatsapp.com and a chat is selected.")
    return None

def open_google_search_tab(search_query: str) -> Optional[ChromeTab]:
    try:
        response = requests.get(f"{REMOTE_DEBUG_URL}/json/version", timeout=10)
        browser_ws_url = response.json().get('webSocketDebuggerUrl')
        if not browser_ws_url:
            print("No browser WebSocket URL found.")
            return None

        tab_conn = ChromeTab(browser_ws_url)
        if not tab_conn.connect():
            print("Failed to connect to browser WebSocket")
            return None
        tab_conn.send_command("Page.navigate", {"url": f"https://www.google.com/search?q={search_query}&tbm=isch"})
        time.sleep(15)  # Increased delay for tab registration
        tab_conn.close()
        google_tab = find_tab_by_url_or_title("google.com")
        return google_tab
    except Exception as e:
        print(f"Error opening Google search tab: {e}")
        return None

def execute_js_on_tab(tab_connection: ChromeTab, js_scripts: List[str], tab_name: str = "Unknown") -> List[dict]:
    results = []
    for idx, js_code in enumerate(js_scripts):
        print(f"Executing script {idx+1}/{len(js_scripts)} on {tab_name}...")
        res = tab_connection.evaluate_js(js_code)
        results.append(res)
        print(f"Script {idx+1} result: {json.dumps(res, indent=2)[:500]}...")
    return results

def process_all_images_in_chat(tab_connection: ChromeTab, initial_tab_ids: Set[str]) -> dict:
    print("Processing images and executing custom search...")
    result = execute_js_on_tab(tab_connection, [JS_OPEN_IMAGE_AND_SEARCH], tab_name="WhatsApp")[0]
    
    if not result.get("success", False):
        print(f"Image processing failed: {result.get('error')}")
        return {"success": False, "error": result.get('error'), "imagesProcessed": 0, "buttonResults": []}

    images_processed = result.get("totalImages", 0)
    results = result.get("results", [])
    print(f"Processed {images_processed} images")
    print(f"Results: {json.dumps(results, indent=2)}")

    button_results = []
    google_tab_ids = set()

    for img_result in results:
        img_info = {
            "image": img_result.get("src"),
            "success": img_result.get("success", False),
            "buttonResults": img_result.get("buttonResults", [])
        }
        
        if not img_result.get("success"):
            img_info["error"] = img_result.get("error", "Unknown error")
            print(f"Skipping Google search for image {img_info['image']}: {img_info['error']}")
            button_results.append(img_info)
            continue

        # Check if any button result indicates "you" was found
        skipped_due_to_you = any(
            btn.get("button") == "skipped" and "you" in btn.get("reason", "").lower()
            for btn in img_result.get("buttonResults", [])
        )

        if skipped_due_to_you:
            print(f"⚠️ Skipping Google search for image {img_result.get('src')} - container contains 'you'")
            img_info["googleSearchSuccess"] = False
            img_info["googleSearchSkipped"] = True
            img_info["skipReason"] = "Container contains 'you'"
            button_results.append(img_info)
            continue

        print(f"Image {img_result.get('src')} processed successfully, checking for Google search tab...")
        
        # Wait for Google tab to open with retries
        google_tab = None
        for attempt in range(5):
            try:
                google_tab = find_tab_by_url_or_title("google.com")
                if google_tab:
                    tabs = requests.get(f"{REMOTE_DEBUG_URL}/json", timeout=10).json()
                    for tab in tabs:
                        if tab.get('type') == 'page' and 'google.com/search' in tab.get('url', '') and tab.get('id') not in initial_tab_ids:
                            google_tab_ids.add(tab.get('id'))
                            print(f"Added Google tab ID: {tab.get('id')}")
                    break
                print(f"Google tab not found, retrying... (Attempt {attempt + 1}/5)")
                time.sleep(5)
            except Exception as e:
                print(f"Error checking tabs (attempt {attempt + 1}): {e}")
                time.sleep(5)

        if google_tab:
            try:
                print(f"Executing Google search scripts for image {img_result.get('src')}")
                google_result = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
                print(f"Google search data result (Part A): {json.dumps(google_result, indent=2)}")
                time.sleep(10)
                google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
                print(f"Google search data result (Part B): {json.dumps(google_result_b, indent=2)}")
                img_info["googleSearchSuccess"] = google_result.get("success", False) and google_result_b.get("success", False)
                img_info["googleSearchData"] = {
                    "partA": google_result.get("data", {}),
                    "partB": google_result_b.get("data", {})
                }
            except Exception as e:
                print(f"Error executing Google search scripts: {e}")
                img_info["googleSearchSuccess"] = False
                img_info["error"] = f"Google search script execution failed: {str(e)}"
            finally:
                try:
                    google_tab.close()
                    print(f"Closed Google tab for image {img_result.get('src')}")
                except Exception as e:
                    print(f"Error closing Google tab: {e}")
        else:
            print(f"No Google search tab found for image {img_result.get('src')}.")
            img_info["googleSearchSuccess"] = False
            img_info["error"] = "No Google search tab opened"

        button_results.append(img_info)

    # Close only non-Google and non-initial tabs
    try:
        tabs = requests.get(f"{REMOTE_DEBUG_URL}/json", timeout=10).json()
        print(f"Final tab cleanup - initial_tab_ids: {initial_tab_ids}, google_tab_ids: {google_tab_ids}")
        for tab in tabs:
            tab_id = tab.get('id')
            if tab.get('type') == 'page' and tab_id not in initial_tab_ids and tab_id not in google_tab_ids:
                try:
                    tab_conn = ChromeTab(tab.get('webSocketDebuggerUrl'))
                    if tab_conn.connect():
                        tab_conn.send_command("Page.close")
                        tab_conn.close()
                        print(f"Closed tab: {tab.get('url')}")
                except Exception as e:
                    print(f"Error closing tab {tab.get('url')}: {e}")
    except Exception as e:
        print(f"Error during final tab cleanup: {e}")

    return {"success": images_processed > 0, "imagesProcessed": images_processed, "buttonResults": button_results}

def test_single_chat(google_search_query: str = "example"):
    print("="*60)
    print("Starting WhatsApp single chat automation...")
    print("="*60)
    print("INSTRUCTIONS: Open WhatsApp Web[](https://web.whatsapp.com) and manually select a chat with images before running this script.")
    print("Press Enter to continue after selecting a chat...")
    input()

    if not check_chrome_running(args.port):
        print(f"ERROR: Chrome is not running with remote debugging on port {args.port}")
        print("Please start Chrome with: chrome.exe --remote-debugging-port=9240 --user-data-dir=<path>")
        return

    whatsapp_tab = find_tab_by_url_or_title("web.whatsapp.com")
    if not whatsapp_tab:
        print("WhatsApp tab not found. Exiting.")
        return

    try:
        # Verify chat is open
        chat_check = execute_js_on_tab(whatsapp_tab, ["document.querySelector('#main') ? { success: true, chatOpen: true } : { success: false, error: 'No chat open' }"], tab_name="WhatsApp")[0]
        if not chat_check.get("success", False):
            print(f"Failed to verify chat: {chat_check.get('error')}")
            return

        print("Chat verified. Extracting messages...")
        messages_result = execute_js_on_tab(whatsapp_tab, [JS_EXTRACTOR], tab_name="WhatsApp")[0]
        print(f"Extracted {len(messages_result.get('messages', []))} messages")

        initial_tabs_response = requests.get(f"{REMOTE_DEBUG_URL}/json", timeout=10).json()
        initial_tab_ids = set(t['id'] for t in initial_tabs_response if t.get('type') == 'page')
        img_results = process_all_images_in_chat(whatsapp_tab, initial_tab_ids)
        print(f"Image processing results: {img_results}")

        print("Attempting to process Google search page...")
        google_tab = find_tab_by_url_or_title("google.com")
        if not google_tab:
            print(f"No Google search tab found. Opening new tab with query: {google_search_query}")
            google_tab = open_google_search_tab(google_search_query)
            if not google_tab:
                print("Failed to open Google search tab. Skipping Google search.")
            else:
                google_result_a = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
                print(f"Google search data result (Part A): {google_result_a}")
                time.sleep(10)
                google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
                print(f"Google search data result (Part B): {google_result_b}")
                time.sleep(5)
                google_tab.close()
        else:
            google_result_a = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
            print(f"Google search data result (Part A): {google_result_a}")
            time.sleep(10)
            google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
            print(f"Google search data result (Part B): {google_result_b}")
            time.sleep(5)
            google_tab.close()

    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("Closing connection...")
        whatsapp_tab.close()
        print("Connection closed.")


def test_single_chat(google_search_query: str = "example"):
    print("="*60)
    print("Starting WhatsApp single chat automation...")
    print("="*60)
    print("INSTRUCTIONS: Open WhatsApp подходящий Web[](https://web.whatsapp.com) and manually select a chat with images before running this script.")
    print("Press Enter to continue after selecting a chat...")
    input()

    if not check_chrome_running(args.port):
        print(f"ERROR: Chrome is not running with remote debugging on port {args.port}")
        print("Please start Chrome with: chrome.exe --remote-debugging-port=9240 --user-data-dir=<path>")
        return

    whatsapp_tab = find_tab_by_url_or_title("web.whatsapp.com")
    if not whatsapp_tab:
        print("WhatsApp tab not found. Exiting.")
        return

    try:
        # Verify chat is open
        chat_check = execute_js_on_tab(whatsapp_tab, ["document.querySelector('#main') ? { success: true, chatOpen: true } : { success: false, error: 'No chat open' }"], tab_name="WhatsApp")[0]
        if not chat_check.get("success", False):
            print(f"Failed to verify chat: {chat_check.get('error')}")
            return

        print("Chat verified. Extracting messages...")
        messages_result = execute_js_on_tab(whatsapp_tab, [JS_EXTRACTOR], tab_name="WhatsApp")[0]
        print(f"Extracted {len(messages_result.get('messages', []))} messages")

        initial_tabs_response = requests.get(f"{REMOTE_DEBUG_URL}/json", timeout=10).json()
        initial_tab_ids = set(t['id'] for t in initial_tabs_response if t.get('type') == 'page')
        img_results = process_all_images_in_chat(whatsapp_tab, initial_tab_ids)
        print(f"Image processing results: {img_results}")

        print("Attempting to process Google search page...")
        google_tab = find_tab_by_url_or_title("google.com")
        if not google_tab:
            print(f"No Google search tab found. Opening new tab with query: {google_search_query}")
            google_tab = open_google_search_tab(google_search_query)
            if not google_tab:
                print("Failed to open Google search tab. Skipping Google search.")
            else:
                google_result_a = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
                print(f"Google search data result (Part A): {google_result_a}")
                time.sleep(10)
                google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
                print(f"Google search data result (Part B): {google_result_b}")
                time.sleep(5)
                google_tab.close()
        else:
            google_result_a = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
            print(f"Google search data result (Part A): {google_result_a}")
            time.sleep(10)
            google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
            print(f"Google search data result (Part B): {google_result_b}")
            time.sleep(5)
            google_tab.close()

        # --- New Code: Extract Name and Number ---
        print("Attempting to extract contact name and number...")
        # Click the chat header to open contact info
        header_result = execute_js_on_tab(whatsapp_tab, [JS_CLICK_HEADER], tab_name="WhatsApp")[0]
        print(f"Header click result: {json.dumps(header_result, indent=2)}")
        if not header_result.get("success", False):
            print(f"Failed to click header: {header_result.get('error', 'Unknown error')}")
        else:
            # Wait for contact info panel to load
            time.sleep(5)
            # Extract contact information
            contact_result = execute_js_on_tab(whatsapp_tab, [JS_EXTRACT_CONTACT_INFO], tab_name="WhatsApp")[0]
            print(f"Contact info extraction result: {json.dumps(contact_result, indent=2)}")
            if contact_result.get("success", False):
                print(f"Extracted contact info: {contact_result.get('text', 'No text extracted')}")
            else:
                print(f"Failed to extract contact info: {contact_result.get('error', 'Unknown error')}")

    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("Closing connection...")
        whatsapp_tab.close()
        print("Connection closed.")


def generate_uid(identifier: str) -> str:
    """Generate a unique ID based on an identifier (e.g., phone number or timestamp)."""
    return hashlib.md5(identifier.encode()).hexdigest()[:8]

def setup_google_sheets() -> gspread.Spreadsheet:
    """Authenticate and return the Google Sheet client."""
    try:
        creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_ID)
        print(f"Connected to Google Sheet: {SHEET_ID}")
        return sheet
    except Exception as e:
        print(f"Failed to connect to Google Sheets: {e}")
        raise

def ensure_sheets_exist(sheet: gspread.Spreadsheet, sheet_names: List[str]) -> None:
    """Ensure all required sheets exist, create them if they don't."""
    existing_sheets = [ws.title for ws in sheet.worksheets()]
    for name in sheet_names:
        if name not in existing_sheets:
            print(f"Creating sheet: {name}")
            sheet.add_worksheet(title=name, rows=100, cols=len(SHEET_CONFIG[name]))
            worksheet = sheet.worksheet(name)
            worksheet.append_row(SHEET_CONFIG[name])  # Add header row
        else:
            worksheet = sheet.worksheet(name)
            # Verify header row
            headers = worksheet.row_values(1)
            if headers != SHEET_CONFIG[name]:
                print(f"Updating headers for {name}")
                worksheet.update('A1', [SHEET_CONFIG[name]])

import gspread
from datetime import datetime
import hashlib
import json

def generate_uid(seed: str) -> str:
    """Generate a short UID from a seed string."""
    return hashlib.sha256(seed.encode()).hexdigest()[:8]

def push_to_google_sheets(
    sheet: gspread.Spreadsheet,
    contact_result: dict,
    messages_result: dict,
    img_results: dict,
    google_search_results_a: dict = None,
) -> None:
    """
    Push extracted contact + WhatsApp messages + image + Google Search (Part A & B merged) results to Google Sheets.
    Only includes Google search results for images where container didn't contain 'you'.
    """
    try:
        print("Pushing data to Google Sheets...")

        # ===== CONTACT DETAILS =====
        contact_text = contact_result.get("text", "")
        name = phone_number = ""
        if contact_text:
            lines = contact_text.split("\n")
            name = lines[0].strip() if lines else ""
            phone_number = lines[1].strip() if len(lines) > 1 else ""
        uid = generate_uid(phone_number or str(datetime.now()))

        contacts_sheet = sheet.worksheet("Contacts")
        contacts_row = [uid, name, phone_number, ""]
        contacts_sheet.append_row(contacts_row)
        print(f"Pushed to Contacts: {contacts_row}")

        # ===== PREPARE MERGED IMAGE SUMMARIES (Part A + Part B) =====
        img_summaries = []
        for idx, img_result in enumerate(img_results.get("buttonResults", [])):
            img_url = img_result.get("image", "")
            
            # Check if Google search was skipped
            if img_result.get("googleSearchSkipped", False):
                skip_reason = img_result.get("skipReason", "Unknown reason")
                print(f"⚠️ Skipping summary for image {idx + 1}: {skip_reason}")
                continue
            
            google_data = img_result.get("googleSearchData", {})
            
            # Extract Part A (AI Summary)
            partA = google_data.get("partA", {})
            ai_summary = partA.get("aiText", "").strip()
            
            # Extract Part B (Detailed Search Results)
            partB = google_data.get("partB", {})
            detailed_results = partB.get("textContent", "").strip()
            
            # Merge both parts into one comprehensive summary
            merged_summary = ""
            
            if ai_summary:
                # Clean up AI summary - remove "Listen" prefix and extra whitespace
                ai_lines = [line.strip() for line in ai_summary.split('\n') if line.strip() and line.strip().lower() != 'listen']
                if ai_lines:
                    merged_summary += "🤖 AI Summary:\n" + '\n'.join(ai_lines)
            
            if detailed_results:
                # Clean up detailed results
                detail_lines = [line.strip() for line in detailed_results.split('\n') if line.strip()]
                # Remove common headers
                filtered_lines = [
                    line for line in detail_lines 
                    if not any(skip in line.lower() for skip in ['thinking', 'getting info from', 'putting it all together', 'maps'])
                ]
                
                if filtered_lines:
                    if merged_summary:
                        merged_summary += "\n\n"
                    merged_summary += "🔍 Detailed Information:\n" + '\n'.join(filtered_lines[:50])
            
            if merged_summary:
                # Add image source URL
                final_summary = f"📸 Image {idx + 1}\n{merged_summary}"
                if img_url:
                    final_summary += f"\n🔗 Source: {img_url}"
                
                img_summaries.append(final_summary)
                print(f"✅ Prepared merged summary for image {idx + 1}: {len(final_summary)} chars")
            else:
                print(f"⚠️ No summary data for image {idx + 1}")

        print(f"📊 Total merged summaries prepared: {len(img_summaries)}")

        # ===== WHATSAPP MESSAGES =====
        whatsapp_sheet = sheet.worksheet("Whatsapp")
        messages = messages_result.get("messages", [])

        # Counter for image summaries
        img_index = 0

        for idx, msg in enumerate(messages):
            message_id = generate_uid(f"{uid}_{idx}")
            direction = msg.get("direction", "").lower().strip() or "in"

            # Parse timestamp
            raw_time = msg.get("time") or msg.get("timestamp") or ""
            date, time_str = "", ""
            if raw_time:
                try:
                    if "," in raw_time:
                        parts = [p.strip() for p in raw_time.split(",")]
                        if len(parts) == 2:
                            time_str, date = parts
                        else:
                            time_str = raw_time
                    else:
                        time_str = raw_time
                except Exception as e:
                    print(f"⚠️ Error parsing time '{raw_time}': {e}")

            text = msg.get("text", "").strip()
            message_from_you = text if direction == "out" else ""
            message_from_them = text if direction == "in" else ""

            # ===== APPEND MERGED IMAGE DESCRIPTION FOR INCOMING MESSAGES =====
            if direction == "in" and img_index < len(img_summaries):
                if message_from_them:
                    message_from_them += "\n\n" + "="*50 + "\n"
                message_from_them += img_summaries[img_index]
                img_index += 1
                print(f"✅ Added merged image summary (A+B) to message {idx + 1}")

            # ===== Append to Google Sheet =====
            pushed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            whatsapp_row = [
                uid,
                message_id,
                date,
                time_str,
                message_from_you,
                message_from_them,
                direction,
                pushed_at
            ]
            whatsapp_sheet.append_row(whatsapp_row)
            print(f"Pushed to Whatsapp: {whatsapp_row[:6]}... (truncated)")

        # ===== APPEND REMAINING IMAGE SUMMARIES AS SEPARATE ENTRIES =====
        while img_index < len(img_summaries):
            message_id = generate_uid(f"{uid}_img_{img_index}")
            pushed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            whatsapp_row = [
                uid,
                message_id,
                "",  # date
                "",  # time
                "",  # message_from_you
                f"📋 Additional Image Analysis:\n\n{img_summaries[img_index]}",  # message_from_them
                "in",  # direction
                pushed_at
            ]
            whatsapp_sheet.append_row(whatsapp_row)
            print(f"✅ Pushed additional image summary {img_index + 1}")
            img_index += 1

        print(f"✅ Successfully pushed {len(messages)} messages + {len(img_summaries)} image summaries to Google Sheets")

    except Exception as e:
        print(f"❌ Error pushing to Google Sheets: {e}")
        import traceback
        traceback.print_exc()


def test_single_chat(google_search_query: str = "example"):
    print("="*60)
    print("Starting WhatsApp single chat automation...")
    print("="*60)
    print("INSTRUCTIONS: Open WhatsApp Web and manually select a chat with images before running this script.")
    print("Press Enter to continue after selecting a chat...")
    input()

    if not check_chrome_running(args.port):
        print(f"ERROR: Chrome is not running with remote debugging on port {args.port}")
        print("Please start Chrome with: chrome.exe --remote-debugging-port=9240 --user-data-dir=<path>")
        return

    # Setup Google Sheets
    try:
        sheet = setup_google_sheets()
        ensure_sheets_exist(sheet, SHEET_CONFIG.keys())
    except Exception as e:
        print(f"Google Sheets setup failed: {e}")
        return

    whatsapp_tab = find_tab_by_url_or_title("web.whatsapp.com")
    if not whatsapp_tab:
        print("WhatsApp tab not found. Exiting.")
        return

    try:
        # Verify chat is open
        chat_check = execute_js_on_tab(whatsapp_tab, ["document.querySelector('#main') ? { success: true, chatOpen: true } : { success: false, error: 'No chat open' }"], tab_name="WhatsApp")[0]
        if not chat_check.get("success", False):
            print(f"Failed to verify chat: {chat_check.get('error')}")
            return

        print("Chat verified. Extracting messages...")
        messages_result = execute_js_on_tab(whatsapp_tab, [JS_EXTRACTOR], tab_name="WhatsApp")[0]
        print(f"Extracted {len(messages_result.get('messages', []))} messages")

        initial_tabs_response = requests.get(f"{REMOTE_DEBUG_URL}/json", timeout=10).json()
        initial_tab_ids = set(t['id'] for t in initial_tabs_response if t.get('type') == 'page')
        img_results = process_all_images_in_chat(whatsapp_tab, initial_tab_ids)
        print(f"Image processing results: {img_results}")

        print("Attempting to process Google search page...")
        google_tab = find_tab_by_url_or_title("google.com")
        if not google_tab:
            print(f"No Google search tab found. Opening new tab with query: {google_search_query}")
            google_tab = open_google_search_tab(google_search_query)
            if not google_tab:
                print("Failed to open Google search tab. Skipping Google search.")
            else:
                google_result_a = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
                print(f"Google search data result (Part A): {google_result_a}")
                time.sleep(10)
                google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
                print(f"Google search data result (Part B): {google_result_b}")
                time.sleep(5)
                google_tab.close()
        else:
            google_result_a = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_A], tab_name="Google Search Part A")[0]
            print(f"Google search data result (Part A): {google_result_a}")
            time.sleep(10)
            google_result_b = execute_js_on_tab(google_tab, [JS_GET_GOOGLE_SEARCH_DATA_PART_B], tab_name="Google Search Part B")[0]
            print(f"Google search data result (Part B): {google_result_b}")
            time.sleep(5)
            google_tab.close()

        print("Attempting to extract contact name and number...")
        header_result = execute_js_on_tab(whatsapp_tab, [JS_CLICK_HEADER], tab_name="WhatsApp")[0]
        print(f"Header click result: {json.dumps(header_result, indent=2)}")
        contact_result = {}
        if not header_result.get("success", False):
            print(f"Failed to click header: {header_result.get('error', 'Unknown error')}")
        else:
            time.sleep(5)  # Wait for contact info panel
            contact_result = execute_js_on_tab(whatsapp_tab, [JS_EXTRACT_CONTACT_INFO], tab_name="WhatsApp")[0]
            print(f"Contact info extraction result: {json.dumps(contact_result, indent=2)}")
            if contact_result.get("success", False):
                print(f"Extracted contact info: {contact_result.get('text', 'No text extracted')}")
            else:
                print(f"Failed to extract contact info: {contact_result.get('error', 'Unknown error')}")

        # Push data to Google Sheets
        print("Pushing data to Google Sheets...")
        push_to_google_sheets(sheet, contact_result, messages_result, img_results)

    except KeyboardInterrupt:
        print("Interrupted by user.")
    except Exception as e:
        print(f"Unexpected error: {e}")
    finally:
        print("Closing connection...")
        whatsapp_tab.close()
        print("Connection closed.")

# ---------- Entry Point ----------
if __name__ == "__main__":
    test_single_chat(google_search_query="example")
