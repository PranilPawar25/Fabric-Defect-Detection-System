"""
Live Stream Routes - HTTPS with LAN IP for Mobile Camera Access

Provides:
1. Session creation with token-based authentication
2. Phone camera page serving
3. WebSocket endpoints for phone and viewer
4. LAN IP detection and QR code generation
"""

import asyncio
import base64
import io
import os
import socket
import struct
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pathlib import Path

from inference.live_session import (
    create_session, get_session, end_session, process_frame
)
from config import PROJECT_ROOT

router = APIRouter(prefix="/live", tags=["live"])


def get_lan_ip() -> Optional[str]:
    """
    Get the LAN IP address (same logic as generate_cert.py).
    
    Returns:
        str: LAN IP or None
    """
    # Check environment variable override
    env_ip = os.environ.get('LIVE_HOST_IP')
    if env_ip:
        return env_ip
    
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        
        if local_ip.startswith('127.') or local_ip.startswith('169.254.'):
            return None
        
        return local_ip
    except Exception:
        return None


@router.get("/info")
async def get_live_info():
    """
    Get live stream session information.
    
    Returns:
        JSON with lan_ip, port, phone_url, status, qr_code (optional)
    """
    session = await get_session()
    
    lan_ip = get_lan_ip()
    port = 8443
    
    status = "waiting"
    phone_url = None
    token = None
    qr_code_data = None
    
    print(f"[DEBUG /live/info] Session exists: {session is not None}")
    
    if session:
        token = session.token
        status = "connected" if session.phone_connected else "waiting"
        print(f"[DEBUG /live/info] Session token: {token}")
        print(f"[DEBUG /live/info] Session status: {status}")
        
        if lan_ip:
            phone_url = f"https://{lan_ip}:{port}/live/phone?token={token}"
            print(f"[DEBUG /live/info] Phone URL: {phone_url}")
            
            # Generate QR code if available
            try:
                import qrcode
                qr = qrcode.QRCode(version=1, box_size=10, border=4)
                qr.add_data(phone_url)
                qr.make(fit=True)
                
                img = qr.make_image(fill_color="black", back_color="white")
                buffered = io.BytesIO()
                img.save(buffered, format="PNG")
                qr_code_data = base64.b64encode(buffered.getvalue()).decode()
            except ImportError:
                pass  # QR code is optional
        else:
            print(f"[DEBUG /live/info] WARNING: No LAN IP detected")
    else:
        print(f"[DEBUG /live/info] No active session - call /live/session/start first")
    
    return JSONResponse({
        "lan_ip": lan_ip,
        "port": port,
        "phone_url": phone_url,
        "status": status,
        "token": token,
        "qr_code_data": qr_code_data,
        "has_session": session is not None
    })


@router.post("/session/start")
async def start_session():
    """
    Start a new live stream session.
    
    Returns:
        JSON with session_id, token
    """
    try:
        session = await create_session()
        
        print(f"[DEBUG /live/session/start] ✓ Session created")
        print(f"[DEBUG /live/session/start] Session ID: {session.session_id}")
        print(f"[DEBUG /live/session/start] Token: {session.token}")
        
        return JSONResponse({
            "success": True,
            "session_id": session.session_id,
            "token": session.token
        })
    except RuntimeError as e:
        print(f"[DEBUG /live/session/start] ✗ Error: {e}")
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/session/stop")
async def stop_session():
    """
    Stop the current live stream session.
    
    Returns:
        JSON with success status
    """
    await end_session()
    
    return JSONResponse({
        "success": True,
        "message": "Session ended"
    })


@router.get("/ping")
async def ping():
    """
    Simple reachability check page for testing network connectivity.
    
    Returns:
        HTML page confirming laptop is reachable
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Laptop Reachable</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                text-align: center;
                padding: 40px;
                background: rgba(255,255,255,0.1);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
            }
            .checkmark {
                font-size: 72px;
                margin-bottom: 20px;
            }
            h1 {
                margin: 0 0 10px 0;
                font-size: 32px;
            }
            p {
                margin: 0;
                opacity: 0.9;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="checkmark">✓</div>
            <h1>Laptop Reachable</h1>
            <p>Network connection successful</p>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.get("/phone")
async def phone_page(token: str = Query(...)):
    """
    Serve the mobile camera page.
    
    Args:
        token: Session token
        
    Returns:
        HTML page or error
    """
    print(f"\n[DEBUG /live/phone] ──────────────────────────")
    print(f"[DEBUG /live/phone] Received token from query: {token}")
    
    session = await get_session()
    
    print(f"[DEBUG /live/phone] Session exists: {session is not None}")
    if session:
        print(f"[DEBUG /live/phone] Expected token: {session.token}")
        print(f"[DEBUG /live/phone] Tokens match: {session.token == token}")
    else:
        print(f"[DEBUG /live/phone] No session found!")
    
    if not session or session.token != token:
        # Invalid token
        html_content = """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invalid Link</title>
            <style>
                body {
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                }
                .container {
                    text-align: center;
                    padding: 40px;
                    background: rgba(255,255,255,0.1);
                    backdrop-filter: blur(10px);
                    border-radius: 20px;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                }
                h1 {
                    margin: 0 0 20px 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>❌ Invalid Link</h1>
                <p>This session link is not valid.</p>
                <p>Please scan the QR code or copy the link from the laptop again.</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html_content, status_code=403)
    
    # Serve the phone page
    frontend_dir = PROJECT_ROOT / "frontend"
    phone_page_path = frontend_dir / "live_phone.html"
    
    if phone_page_path.exists():
        return FileResponse(phone_page_path)
    else:
        raise HTTPException(status_code=404, detail="Phone page not found")


@router.websocket("/ws/phone")
async def phone_websocket(websocket: WebSocket, token: str = Query(...)):
    """
    WebSocket endpoint for phone connection.
    
    Protocol:
    - Phone sends binary: [4 bytes seq][8 bytes client_time_ms][JPEG data]
    - Server sends JSON text: result messages
    """
    print(f"\n[DEBUG /ws/phone] ──────────────────────────")
    print(f"[DEBUG /ws/phone] WebSocket connection attempt")
    print(f"[DEBUG /ws/phone] Received token from query: {token}")
    
    session = await get_session()
    
    print(f"[DEBUG /ws/phone] Session exists: {session is not None}")
    if session:
        print(f"[DEBUG /ws/phone] Expected token: {session.token}")
        print(f"[DEBUG /ws/phone] Tokens match: {session.token == token}")
        print(f"[DEBUG /ws/phone] Phone already connected: {session.phone_connected}")
    else:
        print(f"[DEBUG /ws/phone] No session found!")
    
    if not session or session.token != token:
        await websocket.close(code=1008, reason="Invalid token")
        return
    
    if session.phone_connected:
        await websocket.close(code=1008, reason="Another phone is already connected")
        return
    
    await websocket.accept()
    session.phone_connected = True
    session.phone_ws = websocket
    
    try:
        # Send hello
        await websocket.send_json({
            "type": "hello",
            "session_id": session.session_id,
            "min_interval_ms": session.min_interval_ms
        })
        
        while True:
            # Receive binary message
            data = await websocket.receive_bytes()
            
            # Validate size
            if len(data) > 2 * 1024 * 1024:  # 2 MB max
                await websocket.send_json({
                    "type": "error",
                    "message": "Frame too large (max 2 MB)"
                })
                continue
            
            if len(data) < 12:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid frame format"
                })
                continue
            
            try:
                # Parse header: 4 bytes seq (big-endian uint32) + 8 bytes time (big-endian float64)
                seq = struct.unpack('>I', data[0:4])[0]
                client_time_ms = struct.unpack('>d', data[4:12])[0]
                jpeg_data = data[12:]
                
                # Process frame
                result = await process_frame(session, jpeg_data, client_time_ms)
                
                # Send result
                await websocket.send_json({
                    "type": "result",
                    "seq": seq,
                    "frame_number": result['frame_number'],
                    "elapsed_s": result['elapsed_s'],
                    "est_length_m": result['est_length_m'],
                    "frame_w": result['frame_w'],
                    "frame_h": result['frame_h'],
                    "detections": result['detections'],
                    "mode": result['mode']
                })
                
                # Broadcast to viewers
                for viewer_ws in list(session.viewer_ws):
                    try:
                        await viewer_ws.send_json({
                            "type": "frame",
                            "frame_number": result['frame_number'],
                            "detections": result['detections'],
                            "elapsed_s": result['elapsed_s'],
                            "est_length_m": result['est_length_m']
                        })
                    except:
                        session.viewer_ws.discard(viewer_ws)
                
                # Send throttle if needed
                if session.should_throttle():
                    await websocket.send_json({
                        "type": "throttle",
                        "min_interval_ms": session.min_interval_ms
                    })
                
            except Exception as e:
                print(f"[Phone WS] Frame processing error: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": str(e)
                })
    
    except WebSocketDisconnect:
        print("[Phone WS] Phone disconnected")
    except Exception as e:
        print(f"[Phone WS] Error: {e}")
    finally:
        session.phone_connected = False
        session.phone_ws = None
        
        # Notify viewers
        for viewer_ws in list(session.viewer_ws):
            try:
                await viewer_ws.send_json({
                    "type": "ended",
                    "message": "Phone disconnected"
                })
            except:
                pass


@router.websocket("/ws/viewer")
async def viewer_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for desktop viewer.
    
    Sends status updates and frame results to the laptop dashboard.
    """
    session = await get_session()
    
    if not session:
        await websocket.close(code=1008, reason="No active session")
        return
    
    await websocket.accept()
    session.viewer_ws.add(websocket)
    
    try:
        # Send initial status
        await websocket.send_json({
            "type": "status",
            "session_id": session.session_id,
            "phone_connected": session.phone_connected,
            "frame_count": session.frame_count,
            "defects_logged": session.defects_logged
        })
        
        # Keep connection alive and handle pings
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )
                
                if message.get("type") == "ping":
                    await websocket.send_json({
                        "type": "pong",
                        "frame_count": session.frame_count,
                        "defects_logged": session.defects_logged,
                        "phone_connected": session.phone_connected
                    })
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive"})
    
    except WebSocketDisconnect:
        print("[Viewer WS] Viewer disconnected")
    except Exception as e:
        print(f"[Viewer WS] Error: {e}")
    finally:
        session.viewer_ws.discard(websocket)
