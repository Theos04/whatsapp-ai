"""
Enhanced Test Script for Celery Chat Extraction System with Chat Discovery
"""

import time
import sys
import json
from celery.result import AsyncResult
from celery_config import celery_app
from tasks.chat_extractor import extract_chat_history, extract_chat_messages

def test_redis_connection():
    """Test if Redis is accessible"""
    print("1️⃣  Testing Redis connection...")
    try:
        celery_app.backend.client.ping()
        print("   ✅ Redis is running and accessible\n")
        return True
    except Exception as e:
        print(f"   ❌ Redis connection failed: {e}")
        print("   💡 Start Redis: redis-server\n")
        return False

def test_celery_worker():
    """Test if Celery worker is running"""
    print("2️⃣  Testing Celery worker...")
    try:
        inspect = celery_app.control.inspect()
        active_workers = inspect.active_queues()
        
        if active_workers:
            print(f"   ✅ Found {len(active_workers)} active worker(s)")
            for worker, queues in active_workers.items():
                print(f"      - {worker}: {[q['name'] for q in queues]}")
            print()
            return True
        else:
            print("   ❌ No active workers found")
            print("   💡 Start worker: celery -A celery_config worker --loglevel=info --queues=chat_extraction\n")
            return False
    except Exception as e:
        print(f"   ❌ Worker check failed: {e}\n")
        return False

def test_chrome_whatsapp_connection():
    """Test Chrome connection and WhatsApp readiness"""
    print("3️⃣  Testing Chrome/WhatsApp connection...")
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://127.0.0.1:9240")
            context = browser.contexts[0]
            page = context.pages[0]
            
            url = page.url
            if "whatsapp.com" not in url:
                print(f"   ❌ Not on WhatsApp Web: {url}")
                print("   💡 Open: chrome --remote-debugging-port=9240 https://web.whatsapp.com")
                browser.close()
                return False
            
            # Check if WhatsApp is ready (no QR code or connection issues)
            try:
                # Wait a bit for page to stabilize
                page.wait_for_timeout(2000)
                
                # Check for QR code or connection issues
                qr_elements = page.query_selector_all("canvas[aria-label*='Scan']")
                connection_issues = page.query_selector("span[data-testid='connection-status']")
                
                if qr_elements:
                    print("   ❌ WhatsApp not logged in (QR code detected)")
                    print("   💡 Scan QR code with your phone")
                    browser.close()
                    return False
                elif connection_issues:
                    print("   ⚠️  Connection issues detected")
                    browser.close()
                    return False
                else:
                    print(f"   ✅ Connected to WhatsApp Web: {url}")
                    browser.close()
                    return True
            except Exception as e:
                print(f"   ⚠️  WhatsApp readiness check: {e}")
                browser.close()
                return False
                
    except Exception as e:
        print(f"   ❌ Chrome connection failed: {e}")
        print("   💡 Start Chrome: chrome --remote-debugging-port=9240 --user-data-dir=./chrome-data https://web.whatsapp.com")
        return False

def discover_available_chats():
    """Discover and list all available chats"""
    print("🔍 Discovering available chats...")
    try:
        # Create a special discovery task or use existing functionality
        # This assumes you have a discovery function in your tasks
        from tasks.chat_extractor import discover_chats  # Add this function to your tasks
        
        task = discover_chats.delay()
        result = task.get(timeout=30)
        
        if result['status'] == 'success':
            chats = result['chats']
            print(f"   ✅ Found {len(chats)} chats:")
            for i, chat in enumerate(chats[:20], 1):  # Show first 20
                print(f"      {i:2d}. {chat}")
            if len(chats) > 20:
                print(f"      ... and {len(chats) - 20} more")
            return chats
        else:
            print(f"   ❌ Chat discovery failed: {result.get('message', 'Unknown error')}")
            return []
    except Exception as e:
        print(f"   ❌ Chat discovery error: {e}")
        print("   💡 Manually check WhatsApp Web for chat names")
        return []

def test_chat_search(chat_name):
    """Test if specific chat can be found and selected"""
    print(f"🔎 Testing chat search: '{chat_name}'...")
    try:
        # Test search functionality
        task = extract_chat_history.delay(chat_name, test_search_only=True)
        result = task.get(timeout=30)
        
        if result['status'] == 'success':
            print(f"   ✅ Chat '{chat_name}' found and accessible!")
            print(f"      Current title: {result.get('current_title', 'N/A')}")
            return True
        else:
            print(f"   ❌ Chat search failed: {result.get('message', 'Unknown error')}")
            if 'available_chats' in result:
                print(f"   📋 Available chats sample: {result['available_chats'][:5]}")
            print()
            return False
    except Exception as e:
        print(f"   ❌ Search test failed: {e}")
        return False

def test_quick_extraction(chat_name=None):
    """Test quick message extraction (no scrolling)"""
    if not chat_name:
        print("4️⃣  Skipping quick extraction test (no chat name)")
        print("   💡 Usage: python test_celery_extraction.py quick \"Exact Chat Name\"\n")
        return True
    
    print(f"4️⃣  Testing quick extraction: {chat_name}...")
    try:
        task = extract_chat_messages.delay(chat_name, max_messages=5)
        print(f"   📦 Task ID: {task.id}")
        
        result = task.get(timeout=45)
        
        if result['status'] == 'success':
            print(f"   ✅ Quick extraction successful!")
            print(f"      Messages found: {result.get('message_count', 0)}")
            if result.get('messages'):
                sample_msg = result['messages'][0]
                print(f"      Sample: {sample_msg.get('text', 'No text')[:100]}...")
            print()
            return True
        else:
            print(f"   ❌ Quick extraction failed: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed: {e}\n")
        return False

def test_full_extraction(chat_name=None):
    """Test full extraction with scrolling"""
    if not chat_name:
        print("5️⃣  Skipping full extraction test")
        return True
    
    print(f"5️⃣  Testing full extraction: {chat_name}...")
    print("   ⚠️  This tests scrolling - may take 1-3 minutes...")
    
    try:
        task = extract_chat_history.delay(chat_name, scroll_to_top=True, max_scrolls=3)
        print(f"   📦 Task ID: {task.id}")
        
        result = task.get(timeout=180)
        
        if result['status'] == 'success':
            print(f"   ✅ Full extraction successful!")
            print(f"      Total messages: {result.get('message_count', 0)}")
            print(f"      Output file: {result.get('filename', 'N/A')}")
            return True
        else:
            print(f"   ❌ Full extraction failed: {result.get('message', 'Unknown error')}")
            return False
            
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
        return False

def interactive_chat_selection(available_chats):
    """Interactive mode to select chat for testing"""
    if not available_chats:
        return None
    
    print("\n🎯 Select a chat for testing:")
    print("   0. Enter custom chat name")
    for i, chat in enumerate(available_chats[:10], 1):
        print(f"   {i}. {chat}")
    
    try:
        choice = input("\nEnter number (0-10) or exact chat name: ").strip()
        
        if choice == '0':
            return input("Enter exact chat name: ").strip()
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(available_chats):
                return available_chats[idx]
        else:
            # Check if custom input matches any chat
            for chat in available_chats:
                if choice.lower() in chat.lower():
                    return chat
            return choice  # Use as-is if no match
    except:
        pass
    
    return None

def run_all_tests(test_type='basic', chat_name=None):
    """Run comprehensive system tests"""
    print("\n" + "="*70)
    print("🧪 Enhanced Celery WhatsApp Extraction System Test")
    print("="*70 + "\n")
    
    results = []
    
    # Core infrastructure tests
    results.append(("Redis Connection", test_redis_connection()))
    results.append(("Celery Worker", test_celery_worker()))
    results.append(("Chrome/WhatsApp", test_chrome_whatsapp_connection()))
    
    # Chat discovery
    available_chats = discover_available_chats()
    results.append(("Chat Discovery", bool(available_chats)))
    
    # Specific chat tests
    if chat_name:
        results.append(("Chat Search", test_chat_search(chat_name)))
        
        if test_type == 'quick':
            results.append(("Quick Extraction", test_quick_extraction(chat_name)))
        elif test_type == 'full':
            results.append(("Full Extraction", test_full_extraction(chat_name)))
    
    # Interactive mode for basic tests
    if test_type == 'basic' and available_chats:
        print("\n🎮 Interactive Testing Mode")
        selected_chat = interactive_chat_selection(available_chats)
        if selected_chat:
            print(f"\n🧪 Testing extraction for: {selected_chat}")
            results.append(("Interactive Quick Test", test_quick_extraction(selected_chat)))
    
    # Summary
    print("\n" + "="*70)
    print("📊 Comprehensive Test Summary")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} {test_name}")
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total and available_chats:
        print("\n✅ System is fully operational!")
        print("\n🚀 Ready for production:")
        print("   • Start monitoring: python streamwhatsappviakafka.py")
        print("   • Process queue: python consumer_chat_queue.py")
        print("   • Extract chats: extract_chat_history.delay('Chat Name')")
    elif available_chats:
        print("\n⚠️  Partial success - check chat names match exactly")
        print("💡 Common issues:")
        print("   • Chat names may contain numbers/emojis")
        print("   • Use exact display name from WhatsApp")
        print("   • Try partial matching in your search logic")
    else:
        print("\n❌ Critical issues detected")
        print("🔧 Fix infrastructure first, then retry")
    
    return passed == total and bool(available_chats)

# Add this helper function to your tasks/chat_extractor.py

def discover_available_chats():
    """Discover and list all available chats using Playwright"""
    print("🔍 Discovering available chats...")
    try:
        from test_playwright import get_recent_chats
        chats_data = get_recent_chats()
        if not chats_data:
            print("   ❌ No chats fetched.")
            return []

        chats = []
        for chat in chats_data:
            # Format: "Name (Unread: X)" if there are unread messages
            unread_count = chat['unread'] or "0"
            display_name = f"{chat['name']} (Unread: {unread_count})" if unread_count != "0" else chat['name']
            chats.append(display_name)

        print(f"   ✅ Found {len(chats)} chats:")
        for i, c in enumerate(chats[:20], 1):
            print(f"      {i:2d}. {c}")
        if len(chats) > 20:
            print(f"      ... and {len(chats) - 20} more")
        return chats

    except Exception as e:
        print(f"   ❌ Chat discovery error: {e}")
        return []



if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test WhatsApp extraction system")
    parser.add_argument('mode', nargs='?', default='basic', 
                       choices=['basic', 'quick', 'full', 'debug'],
                       help="Test mode")
    parser.add_argument('chat_name', nargs='?', help="Exact chat name to test")
    parser.add_argument('--list-chats', action='store_true', help="List all chats")
    
    args = parser.parse_args()
    
    if args.list_chats:
        print("🔍 Listing all available chats...")
        chats = discover_available_chats()
        if chats:
            for chat in sorted(chats):
                print(f"  • {chat}")
        sys.exit(0)
    
    success = run_all_tests(args.mode, args.chat_name)
    sys.exit(0 if success else 1)