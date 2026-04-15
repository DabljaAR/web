#!/usr/bin/env python3
"""Test script for progressive video dubbing system."""

import requests
import json
import time
import websocket
import threading
from urllib.parse import urlencode

# Configuration
BASE_URL = "http://localhost:8000"
LOGIN_URL = f"{BASE_URL}/api/auth/login"
PROGRESSIVE_PIPELINE_URL = f"{BASE_URL}/api/dubbing/progressive-pipeline"

# Test credentials (use existing test user)
TEST_USER = {
    "username": "judy",
    "password": "password123"
}

# Test video ID (you'll need to upload a video first)
TEST_VIDEO_ID = "df21204a-731c-4176-9b82-f570ab889ab0"  # From the upload you did earlier


def login_and_get_token():
    """Login and get access token."""
    print("🔐 Logging in...")
    
    response = requests.post(
        LOGIN_URL,
        data={
            "username": TEST_USER["username"],
            "password": TEST_USER["password"]
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    
    if response.status_code != 200:
        print(f"❌ Login failed: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    token = data.get("access_token")
    print(f"✅ Login successful, token: {token[:20]}...")
    return token


def start_progressive_pipeline(token, video_id):
    """Start the progressive dubbing pipeline."""
    print(f"🚀 Starting progressive pipeline for video {video_id}...")
    
    params = {
        "video_id": video_id,
        "source_lang": "en",
        "target_lang": "arb_Arab"
    }
    
    response = requests.post(
        PROGRESSIVE_PIPELINE_URL,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    
    if response.status_code != 200:
        print(f"❌ Pipeline start failed: {response.status_code} - {response.text}")
        return None
    
    data = response.json()
    job_id = data.get("job_id")
    print(f"✅ Progressive pipeline started successfully!")
    print(f"📋 Job ID: {job_id}")
    print(f"📺 Video ID: {data.get('video_id')}")
    print(f"📊 Status: {data.get('status')}")
    print(f"💬 Message: {data.get('message')}")
    
    return job_id


def websocket_listener(job_id):
    """Listen to WebSocket updates."""
    print(f"🔌 Connecting to WebSocket for job {job_id}...")
    
    ws_url = f"ws://localhost:8000/ws/progressive/{job_id}"
    
    def on_message(ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "initial_state":
                print(f"🎬 Initial state: {data.get('completion_percentage', 0):.1f}% complete")
                print(f"   📊 Segments: {data.get('segments_completed', 0)}/{data.get('total_segments', 0)}")
                
            elif msg_type == "segment_merged":
                print(f"🎯 Segment {data.get('segment_id')} merged! Progress: {data.get('completion_percentage', 0):.1f}%")
                if data.get('video_url'):
                    print(f"   🎥 Current video: {data['video_url']}")
                
            elif msg_type == "video_updated":
                print(f"📹 Video updated: {data.get('video_url')}")
                
            elif msg_type == "job_completed":
                print(f"🎉 Job completed! Final video: {data.get('final_video_url')}")
                print(f"📈 Stats: {data.get('stats')}")
                
            elif msg_type == "error":
                print(f"❌ Error: {data.get('error_message')}")
                
            elif msg_type == "heartbeat":
                print("💓 Heartbeat")
                
            else:
                print(f"📨 {msg_type}: {data}")
                
        except json.JSONDecodeError:
            print(f"📝 Raw message: {message}")
        except Exception as e:
            print(f"❌ Error processing message: {e}")
    
    def on_error(ws, error):
        print(f"❌ WebSocket error: {error}")
    
    def on_close(ws, close_status_code, close_msg):
        print(f"🔌 WebSocket closed: {close_status_code} - {close_msg}")
    
    def on_open(ws):
        print("✅ WebSocket connected!")
        
        # Send a ping every 30 seconds
        def ping_thread():
            while True:
                try:
                    time.sleep(30)
                    ws.send(json.dumps({"type": "ping", "timestamp": time.time()}))
                except:
                    break
        
        threading.Thread(target=ping_thread, daemon=True).start()
    
    # Create WebSocket connection
    ws = websocket.WebSocketApp(
        ws_url,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    
    # Run WebSocket in a separate thread
    ws_thread = threading.Thread(target=ws.run_forever)
    ws_thread.daemon = True
    ws_thread.start()
    
    return ws_thread


def monitor_progress_via_rest(job_id, token, interval=10):
    """Monitor progress via REST API."""
    print(f"📊 Monitoring progress via REST API (every {interval}s)...")
    
    status_url = f"{BASE_URL}/api/progressive/{job_id}/status"
    
    while True:
        try:
            response = requests.get(
                status_url,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                completion = data.get("completion_percentage", 0)
                status = data.get("status", "unknown")
                
                print(f"📈 REST Progress: {completion:.1f}% ({status}) | Segments: {data.get('segments_completed', 0)}/{data.get('total_segments', 0)}")
                
                if data.get("current_video_url"):
                    print(f"   🎥 Current video: {data['current_video_url']}")
                
                if completion >= 100 or status == "completed":
                    print("🎊 Pipeline completed!")
                    break
                    
            else:
                print(f"❌ REST API error: {response.status_code} - {response.text}")
                break
                
            time.sleep(interval)
            
        except KeyboardInterrupt:
            print("👋 Stopping REST monitor...")
            break
        except Exception as e:
            print(f"❌ REST monitor error: {e}")
            time.sleep(interval)


def main():
    """Main test function."""
    print("🧪 Progressive Video Dubbing Test")
    print("=" * 50)
    
    # 1. Login
    token = login_and_get_token()
    if not token:
        return
    
    # 2. Start progressive pipeline
    job_id = start_progressive_pipeline(token, TEST_VIDEO_ID)
    if not job_id:
        return
    
    print("\n" + "=" * 50)
    print("🎯 Pipeline started! Choose monitoring method:")
    print("1. WebSocket + REST (recommended)")
    print("2. WebSocket only")
    print("3. REST only")
    
    try:
        choice = input("Enter choice (1-3): ").strip()
        
        if choice == "1":
            # WebSocket + REST monitoring
            ws_thread = websocket_listener(job_id)
            monitor_progress_via_rest(job_id, token, interval=15)
            
        elif choice == "2":
            # WebSocket only
            ws_thread = websocket_listener(job_id)
            print("🔌 WebSocket monitoring active. Press Ctrl+C to stop...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("👋 Stopping...")
                
        elif choice == "3":
            # REST only
            monitor_progress_via_rest(job_id, token, interval=5)
            
        else:
            print("❌ Invalid choice")
            
    except KeyboardInterrupt:
        print("\n👋 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test error: {e}")


if __name__ == "__main__":
    main()