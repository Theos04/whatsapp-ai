# 🚀 Celery Chat Extraction Setup Guide

## 📋 System Overview

```
┌─────────────────────┐
│ WhatsApp Web Stream │
│  (Playwright CDM)   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Kafka Topic       │
│ (incoming messages) │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Chat Queue Consumer │
│ Filters & Triggers  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│   Celery Queue      │
│   (Redis Broker)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Celery Workers     │
│ Extract Chat History│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  exported_chats/    │
│  (JSON files)       │
└─────────────────────┘
```

---

## 📦 Installation

### 1. Install Dependencies

```bash
pip install -r requirements_celery.txt
```

### 2. Install & Start Redis

**Windows:**
```bash
# Download from: https://github.com/microsoftarchive/redis/releases
# Or use WSL:
wsl
sudo apt update
sudo apt install redis-server
redis-server
```

**Linux/Mac:**
```bash
# Ubuntu/Debian
sudo apt install redis-server
redis-server

# Mac
brew install redis
redis-server
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

### 3. Update .env File

Add these lines to your `.env`:

```bash
# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Chrome CDP (already exists)
REMOTE_DEBUG_PORT_AIBOT=9240
```

---

## 🚀 Running the System

### Step 1: Start All Services in Separate Terminals

#### Terminal 1: Kafka (if not running)
```bash
# Start Zookeeper
bin/zookeeper-server-start.sh config/zookeeper.properties

# Start Kafka (in another terminal)
bin/kafka-server-start.sh config/server.properties
```

#### Terminal 2: Redis
```bash
redis-server
```

#### Terminal 3: WhatsApp Stream Monitor
```bash
python streamwhatsappviakafka.py
```

**Expected Output:**
```
🚀 Starting WhatsApp Stream Monitor...
✅ Connected to WhatsApp
✅ Found 21 chats (9 with unread, 17 total unread messages)
🔍 Monitoring for changes...
```

#### Terminal 4: Celery Worker
```bash
celery -A celery_config worker --loglevel=info --queues=chat_extraction --concurrency=2
```

**Expected Output:**
```
-------------- celery@DESKTOP v5.3.4
--- ***** ----- 
-- ******* ---- Windows-10-10.0.19045-SP0 2025-10-15 05:50:00
- *** --- * --- 
- ** ---------- [config]
- ** ---------- .> app:         whatsapp_chat_processor
- ** ---------- .> transport:   redis://localhost:6379/0
- ** ---------- .> results:     redis://localhost:6379/0
- *** --- * --- .> concurrency: 2 (prefork)
-- ******* ---- .> task events: OFF
--- ***** ----- 
-------------- [queues]
                .> chat_extraction exchange=chat_extraction(direct) key=chat_extraction

[tasks]
  . tasks.chat_extractor.extract_chat_history
  . tasks.chat_extractor.extract_chat_messages

[2025-10-15 05:50:00,000: INFO/MainProcess] Connected to redis://localhost:6379/0
[2025-10-15 05:50:00,000: INFO/MainProcess] celery@DESKTOP ready.
```

#### Terminal 5: Chat Queue Consumer
```bash
python consumer_chat_queue.py
```

**Expected Output:**
```
🎧 Starting Chat Extraction Queue Consumer...
📡 Listening to: incoming_raw_messages
🔍 Waiting for chat events to trigger extraction...

📨 Event: new_message     | Harish1                       | Unread: 5
📦 Queued FULL extraction: Harish1 (Task ID: 12345678-abcd-1234-5678-1234567890ab)
   ✅ Extraction queued (Task: 12345678...)
```

---

## 🎯 Usage Examples

### Automatic Extraction (via Kafka)

Just send messages on WhatsApp - the system will automatically:
1. Detect new messages (via `streamwhatsappviakafka.py`)
2. Filter for important chats (via `consumer_chat_queue.py`)
3. Queue extraction tasks (Celery)
4. Extract and save chat history (JSON files in `exported_chats/`)

### Manual Extraction

```bash
# Extract specific chat (full history)
python consumer_chat_queue.py manual "Harish1" --full

# Extract recent messages only (no scrolling)
python consumer_chat_queue.py manual "Customer Name"
```

### Check Task Status

```bash
# View active tasks
celery -A celery_config inspect active

# View registered tasks
celery -A celery_config inspect registered

# View task stats
celery -A celery_config inspect stats
```

### Monitor with Flower (Optional)

```bash
# Start Flower web UI
celery -A celery_config flower

# Open browser: http://localhost:5555
```

---

## 📁 Project Structure

```
whatsapp-ai/
├── celery_config.py              # Celery configuration
├── tasks/
│   └── chat_extractor.py         # Extraction tasks
├── streamwhatsappviakafka.py     # WhatsApp monitor
├── consumer_chat_queue.py        # Kafka → Celery bridge
├── exported_chats/               # Output JSON files
│   ├── harish1_20251015_054500_chat.json
│   └── customer_xyz_20251015_060000_chat.json
└── requirements_celery.txt       # Dependencies
```

---

## ⚙️ Configuration Options

### Extraction Triggers (in `consumer_chat_queue.py`)

```python
def should_extract_chat(event):
    # Only extract if unread count >= 3
    if unread_count >= 3:
        return True
    
    # Extract new chats with messages
    if event_type == 'new_chat':
        return True
```

**Adjust threshold:**
- Change `>= 3` to `>= 1` for more aggressive extraction
- Change to `>= 10` for less frequent extraction

### Full vs Quick Extraction

```python
# In consumer_chat_queue.py
full_history = unread >= 5  # Full extraction for 5+ unread
```

**Options:**
- **Full History**: Scrolls to top and extracts ALL messages
- **Quick**: Only extracts visible messages (faster)

---

## 📊 Output Format

### Exported JSON Structure

```json
{
  "chat_name": "Harish1",
  "chat_id": "chat_harish1_0",
  "extracted_at": "2025-10-15T05:45:00",
  "message_count": 150,
  "messages": [
    {
      "index": 0,
      "sender": "Harish1",
      "text": "Hello, can you help me?",
      "timestamp": "2025-10-15T05:30:00.000Z",
      "fromBusiness": false,
      "hasMedia": false,
      "mediaType": null,
      "rawMeta": "[5:30 am, 15/10/2025] Harish1:"
    },
    {
      "index": 1,
      "sender": "Harsh",
      "text": "Of course! How can I assist you?",
      "timestamp": "2025-10-15T05:31:00.000Z",
      "fromBusiness": true,
      "hasMedia": false,
      "mediaType": null,
      "rawMeta": "[5:31 am, 15/10/2025] Harsh:"
    }
  ]
}
```

---

## 🐛 Troubleshooting

### Issue: Celery worker not starting
**Solution:**
```bash
# Check Redis is running
redis-cli ping

# Check for port conflicts
netstat -an | findstr 6379
```

### Issue: Tasks not being processed
**Solution:**
```bash
# 1. Check worker is connected
celery -A celery_config inspect active

# 2. Check queue has tasks
celery -A celery_config inspect reserved

# 3. Restart worker with verbose logging
celery -A celery_config worker --loglevel=debug --queues=chat_extraction
```

### Issue: "Could not find chat" error
**Solution:**
- Make sure WhatsApp Web is open and loaded
- Chat name must match exactly (case-sensitive)
- Try searching manually first to verify name

### Issue: Messages not extracting
**Solution:**
```bash
# Test extraction manually
python -c "from tasks.chat_extractor import extract_chat_history; extract_chat_history('Harish1', scroll_to_top=False)"
```

### Issue: Redis connection refused
**Solution:**
```bash
# Windows (WSL)
sudo service redis-server start

# Linux
sudo systemctl start redis

# Mac
brew services start redis
```

---

## 🔧 Advanced Configuration

### Increase Worker Concurrency

```bash
# Run 4 workers in parallel
celery -A celery_config worker --concurrency=4 --queues=chat_extraction
```

### Configure Scrolling Speed

In `tasks/chat_extractor.py`:
```python
SCROLL_PAUSE_TIME = 1.5  # Increase to 2.0 for slower connection
```

### Change Export Directory

In `tasks/chat_extractor.py`:
```python
CHAT_EXPORT_DIR = "exported_chats"  # Change to your preferred path
```

---

## 📈 Monitoring & Logs

### View Worker Logs
```bash
# Real-time logs
celery -A celery_config worker --loglevel=info

# Save logs to file
celery -A celery_config worker --logfile=celery.log
```

### Check Task Results
```python
from celery.result import AsyncResult
from celery_config import celery_app

# Get task result by ID
task_id = "12345678-abcd-1234-5678-1234567890ab"
result = AsyncResult(task_id, app=celery_app)

print(f"Status: {result.state}")
print(f"Result: {result.result}")
```

### Flower Dashboard

Start Flower for web-based monitoring:
```bash
celery -A celery_config flower --port=5555
```

Open http://localhost:5555 to see:
- Active tasks
- Task history
- Worker status
- Task success/failure rates
- Real-time graphs

---

## 🎛️ Integration with Flask

### Add Extraction Endpoint to `app.py`

```python
from tasks.chat_extractor import extract_chat_history

@app.route('/api/chat/extract', methods=['POST'])
def trigger_extraction():
    """Manually trigger chat extraction via API"""
    data = request.json
    chat_name = data.get('chat_name')
    full_history = data.get('full_history', True)
    
    if not chat_name:
        return jsonify({'error': 'Missing chat_name'}), 400
    
    # Queue extraction task
    task = extract_chat_history.delay(
        chat_name=chat_name,
        scroll_to_top=full_history
    )
    
    return jsonify({
        'status': 'queued',
        'task_id': task.id,
        'chat_name': chat_name
    })

@app.route('/api/chat/extract/status/<task_id>')
def extraction_status(task_id):
    """Check status of extraction task"""
    from celery.result import AsyncResult
    
    result = AsyncResult(task_id, app=celery_app)
    
    return jsonify({
        'task_id': task_id,
        'status': result.state,
        'result': result.result if result.ready() else None
    })
```

### API Usage

```bash
# Trigger extraction
curl -X POST http://localhost:5000/api/chat/extract \
  -H "Content-Type: application/json" \
  -d '{"chat_name": "Harish1", "full_history": true}'

# Response
{
  "status": "queued",
  "task_id": "12345678-abcd-1234-5678-1234567890ab",
  "chat_name": "Harish1"
}

# Check status
curl http://localhost:5000/api/chat/extract/status/12345678-abcd-1234-5678-1234567890ab

# Response (completed)
{
  "task_id": "12345678-abcd-1234-5678-1234567890ab",
  "status": "SUCCESS",
  "result": {
    "status": "success",
    "chat_name": "Harish1",
    "message_count": 150,
    "filepath": "exported_chats/harish1_20251015_054500_chat.json"
  }
}
```

---

## 🔄 Workflow Example

### End-to-End Flow

1. **New message arrives on WhatsApp**
   ```
   Harish1: "Hello, can you send me the pricing?"
   ```

2. **Stream monitor detects it** (`streamwhatsappviakafka.py`)
   ```
   📩 NEW_MESSAGE | Harish1 | Unread: 5
   ```

3. **Event pushed to Kafka**
   ```json
   {
     "event_type": "new_message",
     "chat_name": "Harish1",
     "unread_count": 5
   }
   ```

4. **Queue consumer evaluates** (`consumer_chat_queue.py`)
   ```
   ✅ Meets criteria (5 >= 3 threshold)
   📦 Queued FULL extraction
   ```

5. **Celery worker processes**
   ```
   [INFO] Task started: extract_chat_history
   [INFO] Connecting to Chrome...
   [INFO] Searching for chat: Harish1
   [INFO] Scrolling to load messages...
   [INFO] Extracted 150 messages
   [SUCCESS] Saved to: exported_chats/harish1_20251015_054500_chat.json
   ```

6. **JSON file created**
   ```
   exported_chats/
     └── harish1_20251015_054500_chat.json
   ```

---

## 🎯 Best Practices

### 1. Worker Concurrency
- Start with 2-4 workers
- Don't run too many (Chrome instances are resource-heavy)
- Monitor CPU/RAM usage

### 2. Extraction Thresholds
- Set reasonable unread thresholds (3-5 messages)
- Avoid extracting every single message
- Consider business hours

### 3. Error Handling
- Monitor failed tasks regularly
- Set up alerts for repeated failures
- Log extraction errors

### 4. Storage Management
```bash
# Clean up old exports (older than 30 days)
find exported_chats -name "*.json" -mtime +30 -delete
```

### 5. Rate Limiting
- Don't extract too frequently from same chat
- Add cooldown period (track in Redis/DB)

---

## 📚 Quick Reference

### Start Everything (All-in-One Script)

Create `start_all.sh`:
```bash
#!/bin/bash

# Start Redis
redis-server &

# Start WhatsApp Stream Monitor
python streamwhatsappviakafka.py &

# Start Celery Worker
celery -A celery_config worker --loglevel=info --queues=chat_extraction --concurrency=2 &

# Start Queue Consumer
python consumer_chat_queue.py &

# Start Flask App
python app.py &

echo "✅ All services started!"
echo "📊 Monitor at: http://localhost:5000"
```

### Stop Everything

Create `stop_all.sh`:
```bash
#!/bin/bash

# Kill all Python processes
pkill -f "python streamwhatsappviakafka.py"
pkill -f "python consumer_chat_queue.py"
pkill -f "celery -A celery_config"
pkill -f "python app.py"

# Stop Redis
redis-cli shutdown

echo "⏹️ All services stopped!"
```

---

## 🆘 Common Commands Cheat Sheet

```bash
# Check Redis
redis-cli ping

# List Celery workers
celery -A celery_config inspect active_queues

# Purge all tasks
celery -A celery_config purge

# View task results
celery -A celery_config result <task_id>

# Manual extraction
python consumer_chat_queue.py manual "Chat Name" --full

# Test Playwright connection
python streamwhatsappviakafka.py test

# Monitor with Flower
celery -A celery_config flower

# Check exported files
ls -lh exported_chats/
```

---

## 🎉 Success Checklist

- [ ] Redis installed and running
- [ ] Celery worker started and connected
- [ ] WhatsApp Stream Monitor running
- [ ] Queue Consumer listening
- [ ] Test extraction completed successfully
- [ ] JSON file created in `exported_chats/`
- [ ] Monitoring tools accessible

---

## 📞 Next Steps

1. **Test the system** with a manual extraction
2. **Monitor logs** to ensure everything works
3. **Adjust thresholds** based on your needs
4. **Set up Flower** for better monitoring
5. **Integrate with AI** to process extracted chats

Ready to extract! 🚀