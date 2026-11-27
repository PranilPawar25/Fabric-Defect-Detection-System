#!/usr/bin/env python3
"""
Simulate Phone Client for Testing Live Stream

This script connects to the live stream WebSocket and sends test frames
without needing an actual phone.
"""

import asyncio
import struct
import time
import sys
import ssl
from pathlib import Path
import cv2
import numpy as np

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import websockets
except ImportError:
    print("ERROR: websockets not installed")
    print("Install with: pip install websockets")
    sys.exit(1)


async def simulate_phone(token, num_frames=20):
    """
    Simulate a phone client sending frames.
    
    Args:
        token: Session token from /live/info
        num_frames: Number of frames to send
    """
    # Create SSL context that doesn't verify certificate (self-signed)
    ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    uri = f"wss://localhost:8443/live/ws/phone?token={token}"
    
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri, ssl=ssl_context) as ws:
            print("✓ Connected")
            
            # Wait for hello
            hello = await ws.recv()
            hello_data = eval(hello)  # JSON parse
            print(f"✓ Received hello: {hello_data}")
            
            min_interval_ms = hello_data.get('min_interval_ms', 200)
            
            # Generate test frame
            test_frame = np.random.randint(100, 150, (480, 640, 3), dtype=np.uint8)
            
            # Add a simulated defect (bright rectangle)
            cv2.rectangle(test_frame, (200, 150), (280, 230), (255, 255, 255), -1)
            
            # Encode to JPEG
            _, jpeg_data = cv2.imencode('.jpg', test_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            jpeg_bytes = jpeg_data.tobytes()
            
            print(f"\nSending {num_frames} frames...")
            
            start_time = time.time()
            
            for seq in range(num_frames):
                client_time_ms = (time.time() - start_time) * 1000
                
                # Build message: [4 bytes seq][8 bytes client_time_ms][JPEG]
                header = struct.pack('>I', seq) + struct.pack('>d', client_time_ms)
                message = header + jpeg_bytes
                
                # Send
                await ws.send(message)
                print(f"  Sent frame {seq + 1}/{num_frames}", end='\r')
                
                # Wait for result
                try:
                    result = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    result_data = eval(result)
                    
                    if result_data.get('type') == 'result':
                        frame_num = result_data.get('frame_number', 0)
                        detections = result_data.get('detections', [])
                        est_length = result_data.get('est_length_m', 0.0)
                        
                        print(f"  Frame {frame_num}: {len(detections)} detection(s), {est_length:.2f}m" + " " * 20)
                    
                except asyncio.TimeoutError:
                    print(f"\n  ⚠ Timeout waiting for result")
                
                # Wait before next frame
                await asyncio.sleep(min_interval_ms / 1000.0)
            
            print(f"\n\n✓ Sent {num_frames} frames successfully")
            
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()


async def main():
    print("="*60)
    print("Live Stream Phone Client Simulator")
    print("="*60)
    print()
    
    # Get token
    if len(sys.argv) > 1:
        token = sys.argv[1]
    else:
        print("Usage: python simulate_phone_client.py <token>")
        print("\nTo get the token:")
        print("1. Start run_live.bat")
        print("2. Open https://localhost:8443")
        print("3. Go to Live Stream tab and start a session")
        print("4. Copy the token from the phone URL")
        print()
        token = input("Enter session token: ").strip()
    
    if not token:
        print("✗ Token required")
        return
    
    num_frames = 20
    print(f"Token: {token}")
    print(f"Frames to send: {num_frames}")
    print()
    
    await simulate_phone(token, num_frames)
    
    print()
    print("="*60)
    print("Check the defect log in the web UI")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
