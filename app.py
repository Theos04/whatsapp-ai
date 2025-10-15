from kafka_client import get_producer
from config import KAFKA_TOPIC_INCOMING_raw_messages, KAFKA_TOPIC_REPLIES
producer = get_producer()

from flask import Flask, render_template, request, redirect, url_for, jsonify
import subprocess, os
from dotenv import load_dotenv
import threading
import time
from playwright.sync_api import sync_playwright
from test_playwright import get_recent_chats

app = Flask(__name__)
load_dotenv()

# ==================== ENV CONFIG ====================
CHROME_PATH = os.getenv("CHROME_PATH")
AIBOT_PROFILE = os.getenv("AIBOT_PROFILE")
REMOTE_DEBUG_PORT_AIBOT = os.getenv("REMOTE_DEBUG_PORT_AIBOT", "9240")
WHATSAPP_URL = os.getenv("WHATSAPP_URL", "https://web.whatsapp.com")

# ==================== BOT STATUS ====================
bot_status = {
    "running": False,
    "port": REMOTE_DEBUG_PORT_AIBOT,
    "monitoring": False,
    "stream_active": False
}

monitoring_thread = None
stream_process = None
stop_monitoring = threading.Event()

# In-memory cache for chat data (updated by streaming)
chat_cache = {
    "chats": [],
    "last_updated": None,
    "total_unread_chats": 0,
    "total_unread_messages": 0
}

# ==================== CORE FUNCTIONS ====================

def is_whatsapp_open():
    """Check if WhatsApp is already open in a Chrome instance on the given port."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{REMOTE_DEBUG_PORT_AIBOT}")
            for context in browser.contexts:
                for page in context.pages:
                    if WHATSAPP_URL in page.url:
                        browser.close()
                        return True
            browser.close()
    except Exception:
        pass
    return False

def launch_chrome(profile_path, port):
    """Launch Chrome with specified user profile and remote debugging port."""
    if not profile_path or not CHROME_PATH:
        print("❌ ERROR: Chrome path or profile path not set.")
        return False
    
    os.makedirs(profile_path, exist_ok=True)
    command = [
        CHROME_PATH,
        f'--user-data-dir={profile_path}',
        f'--remote-debugging-port={port}',
        '--start-maximized',
        WHATSAPP_URL
    ]
    print(f"🚀 Launching Chrome with profile {profile_path} on port {port}")
    subprocess.Popen(command, shell=True)
    bot_status["running"] = True
    return True

def start_whatsapp_stream():
    """Start the WhatsApp streaming monitor as a subprocess"""
    global stream_process
    
    if stream_process is not None and stream_process.poll() is None:
        print("ℹ️ Stream already running")
        return True
    
    try:
        # Start streamwhatsappviakafka.py as subprocess
        stream_process = subprocess.Popen(
            ['python', 'streamwhatsappviakafka.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        bot_status["stream_active"] = True
        print("✅ WhatsApp stream monitor started")
        return True
    except Exception as e:
        print(f"❌ Failed to start stream: {e}")
        return False

def stop_whatsapp_stream():
    """Stop the WhatsApp streaming monitor"""
    global stream_process
    
    if stream_process is not None:
        stream_process.terminate()
        stream_process.wait(timeout=5)
        stream_process = None
        bot_status["stream_active"] = False
        print("⏹️ WhatsApp stream monitor stopped")

# ==================== ROUTES ====================

@app.route('/')
def landing():
    """Landing page"""
    return render_template('index.html')

@app.route('/choose')
def choose():
    """Choose bot type page"""
    return render_template('choose.html')

@app.route('/personas')
def personas():
    return render_template('persona.html')

@app.route('/launch', methods=['POST'])
def launch_bot():
    """Launch selected bot type"""
    bot_type = request.form.get('bot_type')

    if bot_type == "ai":
        if not is_whatsapp_open():
            success = launch_chrome(AIBOT_PROFILE, REMOTE_DEBUG_PORT_AIBOT)
            if not success:
                return redirect(url_for('choose'))
        else:
            print("ℹ️ WhatsApp is already open, skipping launch.")
            bot_status["running"] = True
        
        # Start streaming monitor
        start_whatsapp_stream()
        
        return redirect(url_for('aibot_dashboard'))

    elif bot_type == "bulky":
        return redirect(url_for('bulky_dashboard'))

    return redirect(url_for('choose'))

@app.route('/aibot-dashboard')
def aibot_dashboard():
    """AI Bot Dashboard"""
    return render_template('aibot-info.html', 
                         port=REMOTE_DEBUG_PORT_AIBOT,
                         running=bot_status["running"],
                         monitoring=bot_status["stream_active"])

@app.route('/bulky-dashboard')
def bulky_dashboard():
    """Bulk Messaging Bot Dashboard"""
    return render_template('bulky_dashboard.html')

@app.route("/api/chats/list")
def list_chats():
    """
    Get chat list - now using cached data from stream
    Falls back to direct extraction if cache is empty
    """
    try:
        # If cache is empty or old, fetch directly
        if not chat_cache["chats"] or chat_cache["last_updated"] is None:
            chats = get_recent_chats()
            # Update cache
            chat_cache["chats"] = chats
            chat_cache["last_updated"] = time.time()
        else:
            chats = chat_cache["chats"]
        
        return jsonify(chats)
    except Exception as e:
        print(f"Error in /api/chats/list: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stream/status')
def stream_status():
    """Get streaming monitor status"""
    return jsonify({
        "active": bot_status["stream_active"],
        "running": bot_status["running"],
        "cache_size": len(chat_cache["chats"]),
        "last_updated": chat_cache["last_updated"]
    })

@app.route('/api/stream/start', methods=['POST'])
def start_stream():
    """Manually start streaming monitor"""
    success = start_whatsapp_stream()
    return jsonify({"success": success, "active": bot_status["stream_active"]})

@app.route('/api/stream/stop', methods=['POST'])
def stop_stream():
    """Manually stop streaming monitor"""
    stop_whatsapp_stream()
    return jsonify({"success": True, "active": bot_status["stream_active"]})

@app.route('/api/incoming', methods=['POST'])
def incoming_message():
    """
    Receive raw WhatsApp messages (via your Playwright automation)
    and push them to Kafka for async processing.
    """
    data = request.json
    phone = data.get("phone")
    message = data.get("message")

    if not phone or not message:
        return jsonify({"error": "Missing phone or message"}), 400

    payload = {
        "phone": phone,
        "message": message,
        "source": "whatsapp",
        "timestamp": time.time()
    }

    producer.send(KAFKA_TOPIC_INCOMING_raw_messages, payload)
    producer.flush()
    print(f"🔥 Queued incoming message from {phone}: {message}")

    return jsonify({"status": "queued", "topic": KAFKA_TOPIC_INCOMING_raw_messages})

# ==================== CLEANUP ====================

def cleanup():
    """Cleanup function to stop streaming on app shutdown"""
    stop_whatsapp_stream()

import atexit
atexit.register(cleanup)

# ==================== ENTRY POINT ====================

if __name__ == '__main__':
    print("🌐 Running on http://127.0.0.1:5000")
    app.run(debug=True, threaded=True, use_reloader=False)