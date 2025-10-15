# ⚡ Quick Start Guide - Celery Chat Extraction

## 🎯 Goal
Automatically extract WhatsApp chat history to JSON files when new messages arrive.

---

## 📋 Prerequisites Checklist

- [ ] Python 3.8+ installed
- [ ] Chrome browser installed
- [ ] Redis installed
- [ ] Kafka running (Zookeeper + Kafka broker)

---

## 🚀 Setup (5 Minutes)

### 1. Install Dependencies
```bash
pip install celery redis playwright kafka-python flask python-dotenv
playwright install chromium
```

### 2. Start Redis
```bash
# Windows (WSL) or Linux
redis-server

# Mac
brew services start redis

# Verify
redis-cli ping  # Should return: PONG
```

### 3. Update .env File
Add to your `.env`:
```bash
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
REMOTE_DEBUG_PORT_AIBOT=9240
```

### 4. Create Required Files

Download/create these files in your project:
- `celery_config.py`
- `tasks/chat_extractor.py`
- `consumer_chat_queue.py`
- `streamwhatsappviakafka.py` (already exists)

Create `tasks/` folder:
```bash
mkdir tasks
touch tasks/__init__.py
```

---

## 🧪 Test the System

```bash
# Run all tests
python test_celery_extraction.py

# Expected output:
# ✅ Redis is running
# ✅ Celery worker active
# ✅ Chrome/WhatsApp connected
# 🎯 Result: 3/3 tests passed
```

---

## 🎬 Start Everything

Open **4 separate terminals**:

### Terminal 1: Celery Worker
```bash
celery -A celery_config worker --loglevel=info --queues=chat_extraction --concurrency=2
```
**Wait for:** `celery@DESKTOP ready.`

### Terminal 2: WhatsApp Stream Monitor
```bash
python streamwhatsappviakafka.py
```
**Wait for:** `🔍 Monitoring for changes...`

### Terminal 3: Queue Consumer
```bash
python consumer_chat_queue.py
```
**Wait for:** `🎧 Starting Chat Extraction Queue Consumer...`

### Terminal 4: Flask App (Optional)
```bash
python app.py
```
**Visit:** http://localhost:5000/aibot-dashboard

---

## ✅ Verify It's Working

### Method 1: Send a Test Message
1. Open WhatsApp Web in Chrome (should already be open)
2. Send yourself a message or have someone message you
3. Watch Terminal 2 (Stream Monitor):
   ```
   📩 NEW_MESSAGE | TestChat | Unread: 5
   ```
4. Watch Terminal 3 (Queue Consumer):
   ```
   📦 Queued FULL extraction: TestChat
   ✅ Extraction queued
   ```
5. Watch Terminal 1 (Celery Worker):
   ```
   [INFO] Task started: extract_chat_history
   [INFO] Extracted 150 messages
   [SUCCESS] Saved to: exported_chats/testchat_20251015_120000_chat.json
   ```

### Method 2: Manual Extraction
```bash
python consumer_chat_queue.py manual "Harish1" --full
```

### Method 3: Check Output
```bash
ls -lh exported_chats/
# Should show JSON files
```

---

## 📁 Expected Output

After a successful extraction, you'll find:

```
exported_chats/
└── harish1_20251015_120000_chat.json
```

**File contents:**
```json
{
  "chat_name": "Harish1",
  "extracted_at": "2025-10-15T12:00:00",
  "message_count": 150,
  "messages": [
    {
      "sender": "Harish1",
      "text": "Hello, can you help me?",
      "timestamp": "2025-10-15T05:30:00.000Z",
      "fromBusiness": false
    }
  ]
}
```

---

## 🎛️ Configuration

### Adjust Extraction Threshold

Edit `consumer_chat_queue.py`:
```python
def should_extract_chat(event):
    # Change this value:
    if unread_count >= 3:  # Lower = more extractions
        return True
```

**Recommended values:**
- `>= 1`: Extract every new message (aggressive)
- `>= 3`: Balance (default)
- `>= 10`: Only important chats

### Full vs Quick Extraction

Edit `consumer_chat_queue.py`:
```python
# Change this line:
full_history = unread >= 5  # Full extraction threshold
```

---

## 🛠️ Common Issues & Fixes

### ❌ "Redis connection refused"
```bash
# Start Redis
redis-server

# Or on Mac
brew services start redis
```

### ❌ "No Celery workers"
```bash
# Start worker in new terminal
celery -A celery_config worker --loglevel=info --queues=chat_extraction
```

### ❌ "Could not find chat"
- Make sure chat name is **exact match** (case-sensitive)
- Try searching in WhatsApp Web first to verify name
- Check if WhatsApp Web is loaded

### ❌ "Chrome connection failed"
```bash
# Make sure Chrome is running with remote debugging
# Check in app.py if Chrome was launched correctly
```

---

## 📊 Monitor Tasks

### View Active Tasks
```bash
celery -A celery_config inspect active
```

### Check Task Status
```python
from celery.result import AsyncResult
from celery_config import celery_app

result = AsyncResult('task-id-here', app=celery_app)
print(result.state)  # SUCCESS, PENDING, FAILURE
print(result.result)  # Task output
```

### Web Dashboard (Optional)
```bash
# Install Flower
pip install flower

# Start dashboard
celery -A celery_config flower

# Open: http://localhost:5555
```

---

## 🎯 Next Steps

1. ✅ Verify all 4 terminals are running
2. ✅ Send a test message on WhatsApp
3. ✅ Check `exported_chats/` folder for JSON
4. ✅ Integrate with AI for processing chats
5. ✅ Set up monitoring dashboard

---

## 🔍 Quick Commands

```bash
# Test system
python test_celery_extraction.py

# Manual extraction
python consumer_chat_queue.py manual "Chat Name" --full

# Check exported files
ls -lh exported_chats/

# View last extraction
cat exported_chats/*.json | jq '.message_count'

# Clear old exports (30+ days)
find exported_chats -name "*.json" -mtime +30 -delete

# Restart all
pkill -f celery && pkill -f consumer_chat_queue && pkill -f streamwhatsapp
```

---

## 💡 Tips

1. **Start with quick extraction** to test, then enable full history
2. **Monitor CPU usage** - each Chrome instance uses resources
3. **Don't extract every message** - set reasonable thresholds
4. **Use Flower dashboard** for better visibility
5. **Backup JSON files** regularly

---

## 🆘 Getting Help

If something doesn't work:

1. Check all 4 terminals for error messages
2. Run: `python test_celery_extraction.py`
3. Check Redis: `redis-cli ping`
4. Check Chrome: Visit http://127.0.0.1:9240 in browser
5. Review logs in Terminal 1 (Celery Worker)

---

## ✅ Success Indicators

You know it's working when:

- ✅ Terminal 1 shows: `celery@DESKTOP ready`
- ✅ Terminal 2 shows: `🔍 Monitoring for changes`
- ✅ Terminal 3 shows: `🎧 Starting Chat Extraction`
- ✅ New messages trigger: `📦 Queued extraction`
- ✅ Files appear in: `exported_chats/`

**You're all set! 🎉**