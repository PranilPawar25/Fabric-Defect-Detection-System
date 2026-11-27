# Live Stream Defect Detection Guide

## Overview

The Live Stream feature allows you to use your mobile phone's camera as a real-time defect detection device. This is perfect for:

- Quick fabric inspections
- Field testing
- Real-time quality checks
- Demonstrations

## How It Works

```
Desktop PC (Main UI)  →  Creates Session  →  Generates QR Code/URL
                                                     ↓
Mobile Phone  →  Opens URL  →  Accesses Camera  →  Sends Frames
                                                     ↓
Backend Server  →  Processes Frames  →  Detects Defects  →  Updates Log
                                                     ↓
Desktop PC (Main UI)  ←  Shows Results in Real-Time
```

## Step-by-Step Instructions

### 1. Start Live Stream Session (Desktop)

1. Open the web interface on your desktop computer
2. Navigate to the **Live Stream** tab
3. Click **Start Live Stream** button
4. A QR code and URL will be generated

### 2. Connect Mobile Device

**Option A: Scan QR Code (Easiest)**
1. Open your mobile phone's camera app
2. Point at the QR code displayed on screen
3. Tap the notification to open the link
4. Grant camera permissions when prompted

**Option B: Manual URL**
1. Copy the displayed URL
2. Open your mobile browser (Chrome/Safari recommended)
3. Paste and navigate to the URL
4. Grant camera permissions when prompted

### 3. Start Detection (Mobile)

1. Position your phone to view the fabric
2. Tap **Start Detection** button
3. Move the camera slowly over the fabric
4. Defects will be detected in real-time
5. Tap **Stop** when finished

### 4. View Results (Desktop)

1. Watch the **Defect Log** update in real-time
2. See frame count and defect count increase
3. Review detected defects with timestamps
4. Export results to CSV if needed

### 5. End Session

1. Return to desktop
2. Click **End Session** button
3. Session data is saved to database

## Features

### Real-Time Processing
- Processes frames at ~10 FPS
- Low latency detection (< 200ms per frame)
- Automatic classification of defect types

### Mobile Camera Controls
- **Flip Camera**: Switch between front/back cameras
- **Start/Stop**: Control detection on demand
- **FPS Counter**: Monitor processing performance
- **Live Stats**: See frame count and defects detected

### Desktop Monitoring
- **Session Status**: Track connected devices
- **Frame Count**: Total frames processed
- **Defect Count**: Total defects found
- **Auto-Refresh**: Log updates automatically

## Technical Details

### WebSocket Communication

The system uses WebSocket for real-time bidirectional communication:

```javascript
// Mobile → Server
{
  "type": "frame",
  "data": "base64_encoded_jpeg"
}

// Server → Mobile
{
  "type": "result",
  "detections": [...],
  "annotated_frame": "base64_encoded_jpeg",
  "frame_count": 123,
  "defect_count": 5
}
```

### Supported Browsers

**Mobile:**
- ✅ Chrome (Android/iOS)
- ✅ Safari (iOS)
- ✅ Firefox (Android)
- ✅ Edge (Android)

**Desktop:**
- ✅ All modern browsers

### Network Requirements

**Same Network (Recommended):**
- Mobile and desktop on same WiFi
- Lowest latency
- Best performance

**Remote Access:**
- Requires HTTPS/WSS
- May have higher latency
- Needs proper firewall configuration

### Performance

| Metric | Value |
|--------|-------|
| Frame Rate | ~10 FPS |
| Latency | 100-200ms |
| Resolution | 1280x720 (ideal) |
| Bandwidth | ~500 KB/s |

## Troubleshooting

### Camera Not Accessible

**Problem:** "Camera access denied or not available"

**Solutions:**
1. Check browser permissions
2. Reload page and grant permissions
3. Try different browser
4. Check if camera is used by another app

### Connection Failed

**Problem:** "Connection Error" or disconnects

**Solutions:**
1. Verify desktop server is running
2. Check WiFi connection
3. Ensure firewall allows WebSocket connections
4. Try refreshing the mobile page

### Low Frame Rate

**Problem:** FPS counter shows < 5 FPS

**Solutions:**
1. Reduce camera resolution
2. Improve WiFi signal
3. Close other apps on mobile
4. Check server CPU usage

### No Defects Detected

**Problem:** Camera works but no defects found

**Solutions:**
1. Adjust sensitivity settings (desktop)
2. Ensure good lighting
3. Hold camera steady over defect
4. Check if defects are visible/clear

## API Reference

### Create Session
```http
POST /api/livestream/create-session
```

**Response:**
```json
{
  "session_id": "uuid",
  "mobile_url": "/mobile-camera/uuid",
  "desktop_url": "/desktop-viewer/uuid",
  "qr_code_data": "base64_png",
  "status": "success"
}
```

### Get Session Status
```http
GET /api/livestream/session/{session_id}/status
```

**Response:**
```json
{
  "session_id": "uuid",
  "status": "active",
  "frame_count": 123,
  "defect_count": 5,
  "connected_clients": 1,
  "created_at": "2026-09-04T12:00:00"
}
```

### End Session
```http
DELETE /api/livestream/session/{session_id}
```

**Response:**
```json
{
  "session_id": "uuid",
  "status": "ended",
  "message": "Session ended successfully"
}
```

### WebSocket Endpoint
```
ws://localhost:8000/api/livestream/ws/{session_id}
```

## Best Practices

### For Best Results

1. **Lighting**: Ensure fabric is well-lit
2. **Distance**: Hold camera 30-50cm from fabric
3. **Stability**: Move slowly and steadily
4. **Focus**: Ensure camera is focused on fabric
5. **Coverage**: Scan fabric systematically

### Security Considerations

1. **Session IDs**: Use unique session IDs for each connection
2. **Timeouts**: Sessions auto-cleanup after inactivity
3. **HTTPS**: Use HTTPS in production
4. **Authentication**: Add authentication for production use

### Performance Optimization

1. **Frame Rate**: 10 FPS is optimal balance
2. **JPEG Quality**: 85% quality reduces bandwidth
3. **Resolution**: 1280x720 is recommended
4. **Batch Size**: Process one frame at a time

## Future Enhancements

- [ ] Multi-camera support
- [ ] Recording/playback functionality
- [ ] Advanced filters and preprocessing
- [ ] AR overlays on mobile
- [ ] Session sharing with multiple viewers
- [ ] Cloud storage integration
- [ ] Analytics dashboard

## Support

For issues or questions:
- Check troubleshooting section
- Review API documentation
- Check browser console for errors
- Verify network connectivity

---

**Last Updated:** September 4, 2026  
**Version:** 1.0.0
