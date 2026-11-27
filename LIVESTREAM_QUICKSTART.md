# Live Stream Feature - Quick Start Guide

## 🎯 What Is This?

Turn your mobile phone into a real-time fabric defect detector! Point your phone's camera at fabric, and the AI will detect and classify defects instantly.

## 🚀 Quick Start (3 Steps)

### Step 1: Start the Server

```bash
# On Windows
run.bat

# On Linux/Mac
./run.sh
```

Server will start at: `http://localhost:8000`

### Step 2: Create Live Stream Session

1. Open `http://localhost:8000` in your **desktop browser**
2. Click the **"Live Stream"** tab
3. Click **"Start Live Stream"** button
4. A QR code will appear

### Step 3: Connect Mobile Device

**Option A - QR Code (Easiest):**
1. Open your phone's camera app
2. Point at the QR code on screen
3. Tap the notification to open link
4. Allow camera permissions
5. Tap "Start Detection"

**Option B - Manual URL:**
1. Copy the URL shown on desktop
2. Open in your mobile browser
3. Allow camera permissions
4. Tap "Start Detection"

## 📱 Mobile Controls

- **▶ Start Detection** - Begin scanning fabric
- **⏹ Stop** - Pause detection
- **🔄 Flip Camera** - Switch front/back camera

## 💻 Desktop View

Watch live results in real-time:
- **Frames Processed** - Total frames analyzed
- **Defects Detected** - Number of defects found
- **Defect Log** - List of all detected defects

## 🔧 Network Setup

### Same WiFi Network (Recommended)
Both desktop and mobile should be on the same WiFi network.

1. Find your computer's IP address:
   ```bash
   # Windows
   ipconfig
   
   # Linux/Mac
   ifconfig
   ```

2. Update the mobile URL if needed:
   ```
   http://YOUR_COMPUTER_IP:8000/mobile-camera/SESSION_ID
   ```

### Testing Locally
If both devices are the same computer (for testing):
- Use `localhost` or `127.0.0.1`
- This works for testing with browser dev tools

## ✅ System Requirements

### Desktop
- Windows/Linux/Mac
- Python 3.10+
- Modern browser (Chrome, Firefox, Edge, Safari)
- 4GB RAM minimum

### Mobile
- iOS 12+ or Android 6+
- Modern browser with camera support
- Good WiFi signal
- Camera with 5MP+ recommended

## 🎥 Tips for Best Results

### Lighting
- ✅ Well-lit environment
- ✅ Consistent lighting
- ❌ Avoid shadows
- ❌ Avoid backlighting

### Camera Position
- Distance: **30-50cm** from fabric
- Angle: **Perpendicular** to fabric
- Movement: **Slow and steady**

### Fabric Setup
- Flat surface preferred
- Contrasting background
- Wrinkle-free if possible

## 📊 Performance

| Metric | Value |
|--------|-------|
| Frame Rate | ~10 FPS |
| Latency | 100-200ms |
| Detection Speed | Real-time |
| Resolution | 1280x720 |

## ❓ Troubleshooting

### "Camera access denied"
→ Check browser permissions, try reloading

### "Connection Error"
→ Ensure desktop server is running
→ Check WiFi connection
→ Verify firewall settings

### No defects detected
→ Adjust sensitivity on desktop
→ Improve lighting
→ Ensure defects are visible

### Low FPS (< 5)
→ Check WiFi signal strength
→ Close other apps on mobile
→ Reduce camera resolution

## 🔒 Security Notes

- Sessions expire after inactivity
- Unique session IDs for each connection
- Camera access only during active session
- No video stored on server

## 📖 Full Documentation

See `backend/docs/LIVESTREAM_GUIDE.md` for complete documentation including:
- API reference
- Advanced configuration
- Architecture details
- Security considerations

## 🆘 Support

1. Check troubleshooting section above
2. Review full documentation
3. Check browser console for errors
4. Verify network connectivity

---

**Ready to try it?** Run `run.bat` and open `http://localhost:8000`!
