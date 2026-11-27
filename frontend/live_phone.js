/**
 * Mobile Phone Camera Client for Live Defect Detection
 * 
 * Handles camera access, frame capture, WebSocket communication,
 * and real-time defect visualization.
 */

// Global state
let stream = null;
let ws = null;
let isRunning = false;
let currentCamera = 'environment';
let captureCanvas = null;
let captureCtx = null;
let overlayCanvas = null;
let overlayCtx = null;
let video = null;
let wakeLock = null;

// Stats
let frameCount = 0;
let defectCount = 0;
let seq = 0;
let cameraStartTime = 0;
let fpsFrameCount = 0;
let lastFpsTime = 0;
let minIntervalMs = 200;
let waitingForResult = false;
let pendingTimeout = null;

// Defect type colors (BGR from backend → RGB for canvas)
const DEFECT_COLORS = {
    'hole': 'rgb(255, 0, 0)',           // Blue → Red
    'stain': 'rgb(255, 165, 0)',        // Orange
    'knot': 'rgb(0, 255, 0)',           // Green
    'double_knot': 'rgb(255, 255, 0)',  // Yellow
    'broken_thread': 'rgb(255, 0, 255)' // Magenta
};

// Elements
const elements = {};

// Initialize on load
document.addEventListener('DOMContentLoaded', init);

async function init() {
    // Get DOM elements
    elements.video = document.getElementById('video-feed');
    elements.overlayCanvas = document.getElementById('overlay-canvas');
    elements.loading = document.getElementById('loading');
    elements.errorBanner = document.getElementById('error-banner');
    elements.startBtn = document.getElementById('start-btn');
    elements.stopBtn = document.getElementById('stop-btn');
    elements.flipBtn = document.getElementById('flip-btn');
    elements.statusPill = document.getElementById('status-pill');
    elements.statsOverlay = document.getElementById('stats-overlay');
    elements.frameCountEl = document.getElementById('frame-count');
    elements.defectCountEl = document.getElementById('defect-count');
    elements.estLengthEl = document.getElementById('est-length');
    elements.fpsCounter = document.getElementById('fps-counter');
    elements.wakeLockIndicator = document.getElementById('wake-lock-indicator');

    video = elements.video;
    overlayCanvas = elements.overlayCanvas;
    overlayCtx = overlayCanvas.getContext('2d');

    // Create off-screen canvas for capture
    captureCanvas = document.createElement('canvas');
    captureCtx = captureCanvas.getContext('2d');

    // Check browser support
    if (!checkBrowserSupport()) {
        return;
    }

    // Enable start button
    elements.startBtn.style.display = 'flex';
    elements.startBtn.disabled = false;
    elements.stopBtn.style.display = 'none';
    elements.flipBtn.disabled = true;
    elements.statusPill.textContent = 'Ready';
    elements.loading.style.display = 'none';

    // Event listeners
    elements.startBtn.addEventListener('click', startCamera);
    elements.stopBtn.addEventListener('click', stopDetection);
    elements.flipBtn.addEventListener('click', flipCamera);

    // Handle page visibility
    document.addEventListener('visibilitychange', handleVisibilityChange);
}

function checkBrowserSupport() {
    if (!window.isSecureContext) {
        showError('❌ Must use HTTPS link\n\nOpen the https:// link shown on the laptop.\n(Camera access requires a secure connection)');
        return false;
    }

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showError('❌ Camera not available\n\nYour browser doesn\'t support camera access.');
        return false;
    }

    return true;
}

async function startCamera() {
    elements.startBtn.disabled = true;
    elements.loading.style.display = 'flex';
    elements.loading.querySelector('div:last-child').textContent = 'Requesting camera access...';

    try {
        // Request camera
        const constraints = {
            video: {
                facingMode: { ideal: currentCamera },
                width: { ideal: 1280 },
                height: { ideal: 720 }
            },
            audio: false
        };

        stream = await navigator.mediaDevices.getUserMedia(constraints);
        video.srcObject = stream;

        // Wait for video to be ready
        await new Promise((resolve, reject) => {
            video.onloadedmetadata = resolve;
            video.onerror = reject;
        });

        // Set up canvas sizes
        const videoWidth = video.videoWidth;
        const videoHeight = video.videoHeight;
        overlayCanvas.width = videoWidth;
        overlayCanvas.height = videoHeight;

        // Set capture canvas to max 640px width
        const scale = Math.min(1.0, 640 / videoWidth);
        captureCanvas.width = Math.floor(videoWidth * scale);
        captureCanvas.height = Math.floor(videoHeight * scale);

        elements.loading.style.display = 'none';
        elements.startBtn.style.display = 'none';
        elements.stopBtn.style.display = 'flex';
        elements.stopBtn.disabled = false;
        elements.flipBtn.disabled = false;
        elements.statsOverlay.style.display = 'block';

        // Connect WebSocket
        await connectWebSocket();

        // Request wake lock
        requestWakeLock();

    } catch (err) {
        console.error('Camera error:', err);
        elements.loading.style.display = 'none';
        elements.startBtn.disabled = false;

        if (err.name === 'NotAllowedError') {
            showError('❌ Camera permission denied\n\nTo fix:\n1. Tap the lock icon in the address bar\n2. Go to Permissions → Camera → Allow\n3. Reload this page');
        } else if (err.name === 'NotFoundError') {
            showError('❌ No camera found\n\nMake sure your device has a camera.');
        } else if (err.name === 'NotReadableError') {
            showError('❌ Camera in use\n\nClose other apps using the camera and try again.');
        } else if (err.name === 'OverconstrainedError') {
            // Retry with simpler constraints
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                video.srcObject = stream;
                showError('⚠️ Using fallback camera settings', 3000);
            } catch (err2) {
                showError('❌ Camera access failed\n\n' + err2.message);
            }
        } else {
            showError('❌ Camera error\n\n' + err.message);
        }
    }
}

async function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = new URLSearchParams(window.location.search).get('token');
    const wsUrl = `${protocol}//${window.location.host}/live/ws/phone?token=${token}`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
        console.log('[WS] Connected');
        elements.statusPill.textContent = 'Connected';
        elements.statusPill.classList.add('connected');
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        } catch (err) {
            console.error('[WS] Parse error:', err);
        }
    };

    ws.onerror = (err) => {
        console.error('[WS] Error:', err);
        showError('Connection error', 3000);
    };

    ws.onclose = () => {
        console.log('[WS] Closed');
        elements.statusPill.textContent = 'Disconnected';
        elements.statusPill.classList.remove('connected');

        if (isRunning) {
            // Try to reconnect
            setTimeout(() => {
                if (isRunning) {
                    connectWebSocket();
                }
            }, 2000);
        }
    };

    // Wait for hello message
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Connection timeout')), 5000);
        
        ws.addEventListener('message', function handler(event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'hello') {
                    clearTimeout(timeout);
                    ws.removeEventListener('message', handler);
                    
                    minIntervalMs = data.min_interval_ms || 200;
                    isRunning = true;
                    cameraStartTime = performance.now();
                    lastFpsTime = Date.now();
                    
                    // Start capture loop
                    captureNextFrame();
                    
                    resolve();
                }
            } catch (err) {
                // Ignore parse errors
            }
        });
    });
}

function handleServerMessage(data) {
    switch (data.type) {
        case 'result':
            waitingForResult = false;
            if (pendingTimeout) {
                clearTimeout(pendingTimeout);
                pendingTimeout = null;
            }

            // Update stats
            frameCount = data.frame_number;
            elements.frameCountEl.textContent = frameCount;
            elements.estLengthEl.textContent = data.est_length_m.toFixed(2) + ' m';

            // Update FPS
            fpsFrameCount++;
            const now = Date.now();
            if (now - lastFpsTime >= 1000) {
                const fps = Math.round(fpsFrameCount * 1000 / (now - lastFpsTime));
                elements.fpsCounter.textContent = `FPS: ${fps}`;
                fpsFrameCount = 0;
                lastFpsTime = now;
            }

            // Draw detections
            drawDetections(data.detections, data.frame_w, data.frame_h);

            // Schedule next frame
            if (isRunning) {
                setTimeout(() => captureNextFrame(), minIntervalMs);
            }
            break;

        case 'throttle':
            minIntervalMs = data.min_interval_ms || 200;
            console.log(`[WS] Throttled to ${minIntervalMs}ms`);
            break;

        case 'error':
            console.error('[WS] Server error:', data.message);
            showError('Processing error: ' + data.message, 3000);
            waitingForResult = false;
            if (isRunning) {
                setTimeout(() => captureNextFrame(), minIntervalMs * 2);
            }
            break;

        case 'ended':
            showError('Session ended', 3000);
            stopDetection();
            break;
    }
}

function captureNextFrame() {
    if (!isRunning || !ws || ws.readyState !== WebSocket.OPEN) {
        return;
    }

    if (waitingForResult) {
        // Still waiting for previous result, skip this frame
        setTimeout(() => captureNextFrame(), 100);
        return;
    }

    try {
        // Draw video frame to capture canvas (downscaled)
        captureCtx.drawImage(video, 0, 0, captureCanvas.width, captureCanvas.height);

        // Convert to JPEG blob
        captureCanvas.toBlob((blob) => {
            if (!blob || !isRunning) return;

            blob.arrayBuffer().then((buffer) => {
                // Build message: [4 bytes seq][8 bytes client_time_ms][JPEG data]
                const clientTimeMs = performance.now() - cameraStartTime;
                const header = new ArrayBuffer(12);
                const view = new DataView(header);
                
                // Write seq (big-endian uint32)
                view.setUint32(0, seq, false);
                
                // Write client_time_ms (big-endian float64)
                view.setFloat64(4, clientTimeMs, false);

                // Combine header + JPEG
                const message = new Uint8Array(12 + buffer.byteLength);
                message.set(new Uint8Array(header), 0);
                message.set(new Uint8Array(buffer), 12);

                // Send
                ws.send(message.buffer);
                
                seq++;
                waitingForResult = true;

                // Set timeout in case server doesn't respond
                pendingTimeout = setTimeout(() => {
                    waitingForResult = false;
                    if (isRunning) {
                        captureNextFrame();
                    }
                }, 3000);
            });
        }, 'image/jpeg', 0.6);

    } catch (err) {
        console.error('[Capture] Error:', err);
        waitingForResult = false;
        if (isRunning) {
            setTimeout(() => captureNextFrame(), minIntervalMs);
        }
    }
}

function drawDetections(detections, frameW, frameH) {
    // Clear overlay
    overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

    if (!detections || detections.length === 0) {
        return;
    }

    // Update defect count (total unique from server)
    // For display purposes, show current frame detections
    elements.defectCountEl.textContent = detections.length;

    // Scale from server frame size to display size
    const scaleX = overlayCanvas.width / frameW;
    const scaleY = overlayCanvas.height / frameH;

    detections.forEach(det => {
        const x = det.x * scaleX;
        const y = det.y * scaleY;
        const w = det.w * scaleX;
        const h = det.h * scaleY;

        const color = DEFECT_COLORS[det.type] || 'rgb(255, 0, 0)';

        // Draw rectangle
        overlayCtx.strokeStyle = color;
        overlayCtx.lineWidth = 3;
        overlayCtx.strokeRect(x, y, w, h);

        // Draw label
        const label = `${det.type.replace('_', ' ')} · ${Math.round(det.confidence)}%`;
        overlayCtx.font = 'bold 14px sans-serif';
        const metrics = overlayCtx.measureText(label);
        const labelW = metrics.width + 10;
        const labelH = 20;

        // Label background
        overlayCtx.fillStyle = color;
        overlayCtx.fillRect(x, y - labelH - 5, labelW, labelH);

        // Label text
        overlayCtx.fillStyle = '#fff';
        overlayCtx.fillText(label, x + 5, y - 10);
    });
}

function stopDetection() {
    isRunning = false;

    if (pendingTimeout) {
        clearTimeout(pendingTimeout);
        pendingTimeout = null;
    }

    if (ws) {
        ws.close();
        ws = null;
    }

    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
    }

    if (wakeLock) {
        wakeLock.release();
        wakeLock = null;
        elements.wakeLockIndicator.classList.remove('active');
    }

    video.srcObject = null;

    // Reset UI
    elements.startBtn.style.display = 'flex';
    elements.startBtn.disabled = false;
    elements.stopBtn.style.display = 'none';
    elements.stopBtn.disabled = true;
    elements.flipBtn.disabled = true;
    elements.statsOverlay.style.display = 'none';
    elements.statusPill.textContent = 'Stopped';
    elements.statusPill.classList.remove('connected');

    // Clear overlay
    if (overlayCtx) {
        overlayCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
    }
}

async function flipCamera() {
    currentCamera = currentCamera === 'environment' ? 'user' : 'environment';
    elements.flipBtn.disabled = true;

    const wasRunning = isRunning;
    
    if (wasRunning) {
        stopDetection();
    }

    // Small delay
    await new Promise(resolve => setTimeout(resolve, 300));

    if (wasRunning) {
        await startCamera();
    }

    elements.flipBtn.disabled = false;
}

async function requestWakeLock() {
    if ('wakeLock' in navigator) {
        try {
            wakeLock = await navigator.wakeLock.request('screen');
            elements.wakeLockIndicator.classList.add('active');
            console.log('[Wake Lock] Acquired');

            wakeLock.addEventListener('release', () => {
                console.log('[Wake Lock] Released');
                elements.wakeLockIndicator.classList.remove('active');
            });
        } catch (err) {
            console.warn('[Wake Lock] Failed:', err);
        }
    }
}

function handleVisibilityChange() {
    if (document.hidden) {
        if (wakeLock) {
            wakeLock.release();
            wakeLock = null;
        }
    } else if (isRunning) {
        requestWakeLock();
    }
}

function showError(message, duration = 0) {
    elements.errorBanner.textContent = message;
    elements.errorBanner.classList.add('show');

    if (duration > 0) {
        setTimeout(() => {
            elements.errorBanner.classList.remove('show');
        }, duration);
    }
}

console.log('[Phone Client] Initialized');
