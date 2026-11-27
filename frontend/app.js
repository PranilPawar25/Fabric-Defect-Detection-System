// Fabric Defect Detection System - Frontend Application
// ================================================================

// Global State
const state = {
    currentTab: 'image',
    imageFile: null,
    videoFile: null,
    detectionMode: 'unknown',
    currentSession: null,
    seekTimestamp: null,  // Store timestamp for video seeking
    videoFrameData: [],   // Store per-frame detection data for visualization
    videoInfo: null,      // Store video metadata (fps, duration, etc.)
    config: {
        k_sigma: 2.5,
        feed_speed: 10.0,
        min_confidence: 30.0
    }
};

// API Base URL
const API_BASE = window.location.origin;

// ================================================================
// Initialization
// ================================================================

document.addEventListener('DOMContentLoaded', () => {
    console.log('Fabric Defect Detection System - Initializing...');
    
    initializeTabs();
    initializeUploads();
    initializeConfig();
    initializeLog();
    checkSystemHealth();
    loadConfiguration();
});

// ================================================================
// Video Player Control
// ================================================================

function jumpToFrame(timestampSeconds) {
    // Check if we're on the video tab
    if (state.currentTab !== 'video') {
        // Auto-switch to video tab
        switchTab('video');
        
        // Small delay to ensure tab is visible
        setTimeout(() => {
            seekVideo(timestampSeconds);
        }, 100);
    } else {
        seekVideo(timestampSeconds);
    }
}

function seekVideo(timestampSeconds) {
    // Get the video element
    const videoElement = document.getElementById('video-playback');
    
    // Check if we have a video file loaded
    if (!state.videoFile) {
        showStatus('Please load a video first to jump to frame', 'error');
        return;
    }
    
    // Check if video element exists
    if (!videoElement) {
        showStatus('Video player not initialized. Please analyze a video first.', 'error');
        return;
    }
    
    // Seek to timestamp and pause
    videoElement.currentTime = timestampSeconds;
    videoElement.pause();
    
    // Show notification
    showStatus(`Jumped to ${formatTimestamp(timestampSeconds)}`, 'success');
    
    console.log(`Seeked to ${timestampSeconds}s`);
}

function formatTimestamp(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// ================================================================
// System Health & Configuration
// ================================================================

async function checkSystemHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        
        state.detectionMode = data.mode;
        document.getElementById('detection-mode').textContent = 
            data.mode === 'autoencoder' ? 'Autoencoder' : 'Heuristic Fallback';
        document.getElementById('system-status').textContent = 'Ready';
        
        console.log(`System ready in ${data.mode} mode`);
    } catch (error) {
        console.error('Health check failed:', error);
        document.getElementById('system-status').textContent = 'Error';
        document.getElementById('system-status').classList.remove('status-ready');
    }
}

async function loadConfiguration() {
    try {
        const response = await fetch(`${API_BASE}/config/`);
        const data = await response.json();
        
        if (data.success) {
            state.config = data.config;
            updateConfigUI();
        }
    } catch (error) {
        console.error('Failed to load configuration:', error);
    }
}

function updateConfigUI() {
    document.getElementById('sensitivity-slider').value = state.config.k_sigma;
    document.getElementById('sensitivity-value').textContent = state.config.k_sigma.toFixed(1);
    
    document.getElementById('feed-speed-input').value = state.config.feed_speed;
    
    document.getElementById('min-confidence-slider').value = state.config.min_confidence;
    document.getElementById('min-confidence-value').textContent = Math.round(state.config.min_confidence);
}

// ================================================================
// Tab Navigation
// ================================================================

function initializeTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tab = button.dataset.tab;
            switchTab(tab);
        });
    });
}

function switchTab(tabName) {
    state.currentTab = tabName;
    
    // Update buttons
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    
    // Update panels
    document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === `${tabName}-tab`);
    });
}

// ================================================================
// File Uploads
// ================================================================

function initializeUploads() {
    // Image upload
    const imageUpload = document.getElementById('image-upload');
    const imageLabel = imageUpload.nextElementSibling;
    const analyzeImageBtn = document.getElementById('analyze-image-btn');
    
    imageUpload.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            state.imageFile = file;
            analyzeImageBtn.disabled = false;
            
            // Update label to show filename and size
            const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
            imageLabel.innerHTML = `<span class="file-icon">📷</span><span>📁 ${file.name} — ${sizeMB} MB</span>`;
            
            console.log('Image selected:', file.name);
        }
    });
    
    analyzeImageBtn.addEventListener('click', () => {
        if (!state.imageFile) {
            showStatus('Please select an image file first', 'error');
            return;
        }
        analyzeImage();
    });
    
    // Video upload
    const videoUpload = document.getElementById('video-upload');
    const videoLabel = videoUpload.nextElementSibling;
    const analyzeVideoBtn = document.getElementById('analyze-video-btn');
    
    videoUpload.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            state.videoFile = file;
            analyzeVideoBtn.disabled = false;
            
            // Update label to show filename and size
            const sizeMB = (file.size / (1024 * 1024)).toFixed(2);
            videoLabel.innerHTML = `<span class="file-icon">🎥</span><span>📹 ${file.name} — ${sizeMB} MB</span>`;
            
            console.log('Video selected:', file.name);
        }
    });
    
    analyzeVideoBtn.addEventListener('click', () => {
        if (!state.videoFile) {
            showStatus('Please select a video file first', 'error');
            return;
        }
        analyzeVideo();
    });
    
    // Live stream
    const analyzeStreamBtn = document.getElementById('analyze-stream-btn');
    analyzeStreamBtn.addEventListener('click', () => analyzeLiveStream());
}

// ================================================================
// Configuration Controls
// ================================================================

function initializeConfig() {
    // Sensitivity slider
    const sensitivitySlider = document.getElementById('sensitivity-slider');
    const sensitivityValue = document.getElementById('sensitivity-value');
    
    sensitivitySlider.addEventListener('input', (e) => {
        sensitivityValue.textContent = parseFloat(e.target.value).toFixed(1);
    });
    
    // Min confidence slider
    const minConfidenceSlider = document.getElementById('min-confidence-slider');
    const minConfidenceValue = document.getElementById('min-confidence-value');
    
    minConfidenceSlider.addEventListener('input', (e) => {
        minConfidenceValue.textContent = e.target.value;
    });
    
    // Update button
    document.getElementById('update-config-btn').addEventListener('click', updateConfiguration);
    
    // Reset button
    document.getElementById('reset-config-btn').addEventListener('click', resetConfiguration);
}

async function updateConfiguration() {
    const k_sigma = parseFloat(document.getElementById('sensitivity-slider').value);
    const feed_speed = parseFloat(document.getElementById('feed-speed-input').value);
    const min_confidence = parseFloat(document.getElementById('min-confidence-slider').value);
    
    try {
        const response = await fetch(`${API_BASE}/config/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ k_sigma, feed_speed, min_confidence })
        });
        
        const data = await response.json();
        
        if (data.success) {
            state.config = data.config;
            showStatus('Configuration updated successfully', 'success');
        }
    } catch (error) {
        console.error('Failed to update configuration:', error);
        showStatus('Failed to update configuration', 'error');
    }
}

async function resetConfiguration() {
    try {
        const response = await fetch(`${API_BASE}/config/reset`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            state.config = data.config;
            updateConfigUI();
            showStatus('Configuration reset to defaults', 'success');
        }
    } catch (error) {
        console.error('Failed to reset configuration:', error);
        showStatus('Failed to reset configuration', 'error');
    }
}

// ================================================================
// Image Analysis
// ================================================================

async function analyzeImage() {
    if (!state.imageFile) {
        showStatus('Please select an image file first', 'error');
        return;
    }
    
    const analyzeBtn = document.getElementById('analyze-image-btn');
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Uploading...';
    
    try {
        const formData = new FormData();
        formData.append('file', state.imageFile);
        
        // Change to analyzing state
        analyzeBtn.textContent = 'Analyzing...';
        
        const response = await fetch(`${API_BASE}/analyze/image`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            state.currentSession = data.session_id;
            
            // Log the response for debugging
            console.log('Image analysis response:', data);
            console.log('Detections:', data.detections);
            
            displayImageResults(data);
            updateResultsSummary(data.detections);
            showStatus(`Found ${data.count} defect(s)`, 'success');
        } else {
            showStatus('Analysis failed', 'error');
        }
    } catch (error) {
        console.error('Image analysis error:', error);
        showStatus('Analysis failed: ' + error.message, 'error');
    } finally {
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze Image';
    }
}

function displayImageResults(data) {
    const container = document.getElementById('image-preview-container');
    const canvas = document.getElementById('image-canvas');
    const ctx = canvas.getContext('2d');
    
    // Load and display image with annotations
    const img = new Image();
    img.onload = () => {
        // Set canvas to match image dimensions
        canvas.width = img.width;
        canvas.height = img.height;
        
        // Draw the image
        ctx.drawImage(img, 0, 0);
        
        // Draw detections on top
        console.log(`Drawing ${data.detections.length} detections on canvas`);
        data.detections.forEach((det, index) => {
            console.log(`Drawing detection ${index + 1}:`, det);
            drawDetection(ctx, det);
        });
        
        container.style.display = 'block';
    };
    
    img.onerror = () => {
        console.error('Failed to load image for display');
        showStatus('Failed to display image', 'error');
    };
    
    img.src = URL.createObjectURL(state.imageFile);
}

// ================================================================
// Video Analysis
// ================================================================

let videoPollingInterval = null;

async function analyzeVideo() {
    if (!state.videoFile) {
        showStatus('Please select a video file first', 'error');
        return;
    }
    
    const analyzeBtn = document.getElementById('analyze-video-btn');
    const progressContainer = document.getElementById('video-progress');
    const progressFill = document.getElementById('video-progress-fill');
    const progressText = document.getElementById('video-progress-text');
    
    analyzeBtn.disabled = true;
    analyzeBtn.textContent = 'Uploading...';
    progressContainer.style.display = 'block';
    progressFill.style.width = '0%';
    progressText.textContent = 'Uploading video...';
    
    try {
        const formData = new FormData();
        formData.append('file', state.videoFile);
        
        // Submit video for background processing
        const response = await fetch(`${API_BASE}/analyze/video`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success && data.job_id) {
            // Start polling for progress
            analyzeBtn.textContent = 'Processing...';
            progressText.textContent = 'Processing video: 0%';
            pollVideoProgress(data.job_id, progressFill, progressText, analyzeBtn, progressContainer);
        } else {
            showStatus('Failed to start video analysis', 'error');
            progressContainer.style.display = 'none';
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = 'Analyze Video';
        }
    } catch (error) {
        console.error('Video analysis error:', error);
        showStatus('Analysis failed: ' + error.message, 'error');
        progressContainer.style.display = 'none';
        analyzeBtn.disabled = false;
        analyzeBtn.textContent = 'Analyze Video';
    }
}

async function pollVideoProgress(jobId, progressFill, progressText, analyzeBtn, progressContainer) {
    // Clear any existing polling interval
    if (videoPollingInterval) {
        clearInterval(videoPollingInterval);
    }
    
    // Poll every 500ms
    videoPollingInterval = setInterval(async () => {
        try {
            const response = await fetch(`${API_BASE}/analyze/video/status/${jobId}`);
            const data = await response.json();
            
            // Update progress bar
            const percent = data.progress_percent || 0;
            progressFill.style.width = `${percent}%`;
            
            // Update progress text
            if (data.status === 'queued') {
                progressText.textContent = 'Queued...';
            } else if (data.status === 'processing') {
                const frames = data.frames_processed || 0;
                const total = data.frames_to_process || '?';
                progressText.textContent = `Processing: ${percent}% (${frames}/${total} frames)`;
            } else if (data.status === 'complete') {
                // Processing complete
                clearInterval(videoPollingInterval);
                videoPollingInterval = null;
                
                progressFill.style.width = '100%';
                progressText.textContent = 'Complete!';
                
                // Store results
                state.currentSession = data.session_id;
                state.videoFrameData = data.frame_data || [];  // Store per-frame detection data
                
                // Update UI
                updateResultsSummary(data.detections);
                displayVideoResults(data);
                showStatus(`Processed video: ${data.count} defect(s) found`, 'success');
                
                // Hide progress after delay
                setTimeout(() => {
                    progressContainer.style.display = 'none';
                    progressFill.style.width = '0%';
                }, 2000);
                
                // Re-enable button
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = 'Analyze Video';
            } else if (data.status === 'error') {
                // Processing failed
                clearInterval(videoPollingInterval);
                videoPollingInterval = null;
                
                const errorMsg = data.error || 'Unknown error';
                progressText.textContent = 'Error!';
                showStatus(`Video analysis failed: ${errorMsg}`, 'error');
                
                console.error('Video analysis error:', data.error);
                if (data.error_trace) {
                    console.error('Full traceback:', data.error_trace);
                }
                
                // Hide progress after delay
                setTimeout(() => {
                    progressContainer.style.display = 'none';
                    progressFill.style.width = '0%';
                }, 3000);
                
                // Re-enable button
                analyzeBtn.disabled = false;
                analyzeBtn.textContent = 'Analyze Video';
            }
        } catch (error) {
            console.error('Error polling video progress:', error);
            clearInterval(videoPollingInterval);
            videoPollingInterval = null;
            
            showStatus('Error checking video progress', 'error');
            progressContainer.style.display = 'none';
            analyzeBtn.disabled = false;
            analyzeBtn.textContent = 'Analyze Video';
        }
    }, 500);  // Poll every 500ms
}

function displayVideoResults(data) {
    // Store video info for playback visualization
    state.videoInfo = data.video_info;
    
    // Show video preview container
    const container = document.getElementById('video-preview-container');
    const canvas = document.getElementById('video-canvas');
    container.style.display = 'block';
    
    // Create or get video element
    let videoElement = document.getElementById('video-playback');
    if (!videoElement) {
        // Create video element if it doesn't exist
        videoElement = document.createElement('video');
        videoElement.id = 'video-playback';
        videoElement.controls = true;
        videoElement.style.display = 'none';  // Hidden, we'll use canvas for display
        container.insertBefore(videoElement, canvas);
    }
    
    // Set video source from uploaded file
    videoElement.src = URL.createObjectURL(state.videoFile);
    
    // Setup canvas to match video dimensions
    videoElement.addEventListener('loadedmetadata', () => {
        canvas.width = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;
        
        // Start rendering loop
        renderVideoWithDetections(videoElement, canvas);
    });
    
    // Setup video controls
    setupVideoControls(videoElement, canvas);
    
    console.log('Video analysis complete:', {
        detections: data.count,
        frames_with_defects: data.frame_data ? data.frame_data.length : 0,
        video_info: data.video_info
    });
}

function renderVideoWithDetections(videoElement, canvas) {
    const ctx = canvas.getContext('2d');
    
    function draw() {
        if (videoElement.paused && videoElement.currentTime === 0) {
            // Video hasn't started, show first frame
            ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
        } else if (!videoElement.ended) {
            // Clear canvas
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Draw current video frame
            ctx.drawImage(videoElement, 0, 0, canvas.width, canvas.height);
            
            // Find and draw detections for current timestamp
            const currentTime = videoElement.currentTime;
            drawDetectionsAtTimestamp(ctx, currentTime);
        }
        
        // Continue animation loop
        requestAnimationFrame(draw);
    }
    
    draw();
}

function drawDetectionsAtTimestamp(ctx, currentTime) {
    if (!state.videoFrameData || state.videoFrameData.length === 0) {
        return;
    }
    
    // Find frames within 0.2 seconds of current time
    const threshold = 0.2;
    const relevantFrames = state.videoFrameData.filter(frameData => {
        return Math.abs(frameData.timestamp_seconds - currentTime) < threshold;
    });
    
    // Draw all detections from relevant frames
    relevantFrames.forEach(frameData => {
        frameData.detections.forEach(det => {
            drawDetection(ctx, det);
        });
    });
}

function setupVideoControls(videoElement, canvas) {
    // Create control panel if it doesn't exist
    let controls = document.getElementById('video-controls-custom');
    if (!controls) {
        controls = document.createElement('div');
        controls.id = 'video-controls-custom';
        controls.className = 'video-controls';
        controls.innerHTML = `
            <button id="video-play-btn" class="video-control-btn">▶️ Play</button>
            <button id="video-pause-btn" class="video-control-btn">⏸️ Pause</button>
            <input type="range" id="video-seek-slider" class="video-seek-slider" min="0" max="100" value="0">
            <span id="video-time-display" class="video-time">00:00 / 00:00</span>
        `;
        canvas.parentElement.appendChild(controls);
    }
    
    const playBtn = document.getElementById('video-play-btn');
    const pauseBtn = document.getElementById('video-pause-btn');
    const seekSlider = document.getElementById('video-seek-slider');
    const timeDisplay = document.getElementById('video-time-display');
    
    // Play button
    playBtn.addEventListener('click', () => {
        videoElement.play();
    });
    
    // Pause button
    pauseBtn.addEventListener('click', () => {
        videoElement.pause();
    });
    
    // Seek slider
    seekSlider.addEventListener('input', (e) => {
        const percent = parseFloat(e.target.value);
        videoElement.currentTime = (percent / 100) * videoElement.duration;
    });
    
    // Update slider and time display as video plays
    videoElement.addEventListener('timeupdate', () => {
        if (videoElement.duration) {
            const percent = (videoElement.currentTime / videoElement.duration) * 100;
            seekSlider.value = percent;
            
            const current = formatTimestamp(videoElement.currentTime);
            const total = formatTimestamp(videoElement.duration);
            timeDisplay.textContent = `${current} / ${total}`;
        }
    });
}

function formatTimestamp(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// ================================================================
// Live Stream Analysis - Mobile Camera
// ================================================================

let currentLiveSession = null;
let sessionStatusInterval = null;

async function analyzeLiveStream() {
    const streamBtn = document.getElementById('analyze-stream-btn');
    
    // If session is active, end it
    if (currentLiveSession) {
        await endLiveSession();
        return;
    }
    
    // Create new session
    streamBtn.disabled = true;
    streamBtn.textContent = 'Creating Session...';
    
    try {
        const response = await fetch(`${API_BASE}/api/livestream/create-session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            currentLiveSession = data.session_id;
            
            // Display mobile URL
            displayLiveStreamSession(data);
            
            // Start polling session status
            startSessionStatusPolling();
            
            // Update button
            streamBtn.textContent = 'End Session';
            streamBtn.disabled = false;
            streamBtn.classList.remove('btn-primary');
            streamBtn.classList.add('btn-danger');
            
            showStatus('Live session created! Open URL on mobile device', 'success');
        } else {
            throw new Error('Failed to create session');
        }
    } catch (error) {
        console.error('Session creation error:', error);
        showStatus('Error: ' + error.message, 'error');
        streamBtn.disabled = false;
        streamBtn.textContent = 'Start Live Stream';
    }
}

function displayLiveStreamSession(data) {
    const container = document.getElementById('live-tab');
    
    // Remove any existing session display
    let sessionDisplay = container.querySelector('.session-display');
    if (sessionDisplay) {
        sessionDisplay.remove();
    }
    
    // Create new display
    sessionDisplay = document.createElement('div');
    sessionDisplay.className = 'session-display';
    sessionDisplay.innerHTML = `
        <div class="session-info">
            <h3>📱 Mobile Camera Access</h3>
            
            <div class="qr-section">
                ${data.qr_code_data ? `
                    <img src="data:image/png;base64,${data.qr_code_data}" 
                         alt="QR Code" 
                         style="width: 200px; height: 200px; margin: 20px auto; display: block; background: white; padding: 10px; border-radius: 8px;">
                    <p class="help-text" style="text-align: center;">Scan this QR code with your mobile device</p>
                ` : ''}
            </div>
            
            <div class="url-section">
                <label>Or enter this URL on your mobile browser:</label>
                <div class="url-display">
                    <input type="text" 
                           readonly 
                           value="${window.location.origin}${data.mobile_url}" 
                           id="mobile-url-input"
                           style="width: 100%; padding: 10px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px; margin-top: 8px;">
                    <button onclick="copyMobileUrl()" 
                            style="margin-top: 8px; padding: 8px 16px; background: #3b82f6; color: white; border: none; border-radius: 4px; cursor: pointer;">
                        📋 Copy URL
                    </button>
                </div>
            </div>
            
            <div class="session-stats" style="margin-top: 20px; padding: 15px; background: #f3f4f6; border-radius: 8px;">
                <div class="stat-row">
                    <span>Session ID:</span>
                    <span><code>${data.session_id.substring(0, 8)}...</code></span>
                </div>
                <div class="stat-row">
                    <span>Frames Processed:</span>
                    <span id="live-frame-count">0</span>
                </div>
                <div class="stat-row">
                    <span>Defects Found:</span>
                    <span id="live-defect-count">0</span>
                </div>
                <div class="stat-row">
                    <span>Connected Devices:</span>
                    <span id="live-connected-count">0</span>
                </div>
            </div>
            
            <p class="help-text" style="margin-top: 15px; color: #6b7280;">
                <strong>Instructions:</strong><br>
                1. Open the URL on your mobile device<br>
                2. Grant camera permissions<br>
                3. Point camera at fabric<br>
                4. Click "Start Detection" on mobile<br>
                5. Defects will appear in the log below
            </p>
        </div>
    `;
    
    // Insert after the upload section
    const uploadSection = container.querySelector('.upload-section');
    uploadSection.after(sessionDisplay);
}

function copyMobileUrl() {
    const input = document.getElementById('mobile-url-input');
    input.select();
    input.setSelectionRange(0, 99999); // For mobile devices
    
    try {
        document.execCommand('copy');
        showStatus('URL copied to clipboard!', 'success');
    } catch (err) {
        showStatus('Failed to copy URL', 'error');
    }
}

function startSessionStatusPolling() {
    if (sessionStatusInterval) {
        clearInterval(sessionStatusInterval);
    }
    
    sessionStatusInterval = setInterval(async () => {
        if (!currentLiveSession) {
            clearInterval(sessionStatusInterval);
            return;
        }
        
        try {
            const response = await fetch(
                `${API_BASE}/api/livestream/session/${currentLiveSession}/status`
            );
            const data = await response.json();
            
            // Update UI
            document.getElementById('live-frame-count').textContent = data.frame_count || 0;
            document.getElementById('live-defect-count').textContent = data.defect_count || 0;
            document.getElementById('live-connected-count').textContent = data.connected_clients || 0;
            
            // Refresh defect log
            if (data.defect_count > 0) {
                await refreshDefectLog();
            }
        } catch (error) {
            console.error('Status polling error:', error);
        }
    }, 2000); // Poll every 2 seconds
}

async function endLiveSession() {
    if (!currentLiveSession) return;
    
    const streamBtn = document.getElementById('analyze-stream-btn');
    streamBtn.disabled = true;
    streamBtn.textContent = 'Ending Session...';
    
    try {
        await fetch(`${API_BASE}/api/livestream/session/${currentLiveSession}`, {
            method: 'DELETE'
        });
        
        // Clean up
        currentLiveSession = null;
        
        if (sessionStatusInterval) {
            clearInterval(sessionStatusInterval);
            sessionStatusInterval = null;
        }
        
        // Remove session display
        const sessionDisplay = document.querySelector('.session-display');
        if (sessionDisplay) {
            sessionDisplay.remove();
        }
        
        // Reset button
        streamBtn.textContent = 'Start Live Stream';
        streamBtn.disabled = false;
        streamBtn.classList.add('btn-primary');
        streamBtn.classList.remove('btn-danger');
        
        showStatus('Live session ended', 'info');
    } catch (error) {
        console.error('End session error:', error);
        streamBtn.disabled = false;
        streamBtn.textContent = 'End Session';
    }
}

// ================================================================
// Results Display
// ================================================================

function updateResultsSummary(detections) {
    const counts = {
        total: detections.length,
        hole: 0,
        stain: 0,
        knot: 0,
        double_knot: 0,
        broken_thread: 0
    };
    
    detections.forEach(det => {
        if (counts.hasOwnProperty(det.type)) {
            counts[det.type]++;
        }
    });
    
    document.getElementById('total-defects').textContent = counts.total;
    document.getElementById('count-hole').textContent = counts.hole;
    document.getElementById('count-stain').textContent = counts.stain;
    document.getElementById('count-knot').textContent = counts.knot;
    document.getElementById('count-double_knot').textContent = counts.double_knot;
    document.getElementById('count-broken_thread').textContent = counts.broken_thread;
    
    // Update log
    addToLog(detections);
}

function drawDetection(ctx, detection) {
    const { x, y, w, h, type, confidence } = detection;
    
    // Get color for defect type
    const colors = {
        'hole': 'rgb(0, 0, 255)',
        'stain': 'rgb(0, 165, 255)',
        'knot': 'rgb(0, 255, 0)',
        'double_knot': 'rgb(255, 255, 0)',
        'broken_thread': 'rgb(255, 0, 255)'
    };
    
    const color = colors[type] || 'rgb(255, 255, 255)';
    
    // Draw bounding box
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, w, h);
    
    // Draw label background
    const label = `${type.replace('_', ' ')} ${confidence.toFixed(1)}%`;
    ctx.font = 'bold 14px monospace';
    const textWidth = ctx.measureText(label).width;
    
    ctx.fillStyle = color;
    ctx.fillRect(x, y - 25, textWidth + 10, 25);
    
    // Draw label text
    ctx.fillStyle = 'white';
    ctx.fillText(label, x + 5, y - 7);
}

// ================================================================
// Defect Log
// ================================================================

function initializeLog() {
    document.getElementById('export-log-btn').addEventListener('click', exportLog);
    document.getElementById('clear-log-btn').addEventListener('click', clearLog);
    
    // Load existing log
    loadLog();
}

async function loadLog() {
    try {
        const response = await fetch(`${API_BASE}/log/?limit=50`);
        const data = await response.json();
        
        if (data.success && data.defects.length > 0) {
            displayLog(data.defects);
        }
    } catch (error) {
        console.error('Failed to load log:', error);
    }
}

function displayLog(defects) {
    const logContainer = document.getElementById('defect-log');
    
    if (defects.length === 0) {
        logContainer.innerHTML = '<p class="log-empty">No defects detected yet</p>';
        return;
    }
    
    logContainer.innerHTML = '';
    
    defects.forEach(defect => {
        const entry = createLogEntry(defect);
        logContainer.appendChild(entry);
    });
}

function addToLog(detections) {
    const logContainer = document.getElementById('defect-log');
    
    // Remove empty message
    const emptyMsg = logContainer.querySelector('.log-empty');
    if (emptyMsg) {
        emptyMsg.remove();
    }
    
    detections.forEach(defect => {
        const entry = createLogEntry(defect);
        logContainer.insertBefore(entry, logContainer.firstChild);
    });
}

function createLogEntry(defect) {
    const entry = document.createElement('div');
    entry.className = `log-entry log-entry-${defect.defect_type || defect.type}`;
    
    const typeName = (defect.defect_type || defect.type).replace('_', ' ').toUpperCase();
    const confidence = (defect.confidence || 0).toFixed(1);
    const position = defect.fabric_length_m 
        ? `Est. @ ${defect.fabric_length_m.toFixed(2)}m`  // Clearly labeled as estimate
        : `(${defect.x}, ${defect.y})`;
    
    // Build frame/timestamp display
    let frameInfo = '';
    const sourceType = defect.source_type || 'image';
    
    if (sourceType === 'video') {
        const frameNum = defect.frame_number || 0;
        const timestamp = defect.timestamp_display || '00:00';
        frameInfo = ` — Frame ${frameNum} (${timestamp})`;
    } else if (sourceType === 'image' && defect.frame_number > 1) {
        frameInfo = ` — Image ${defect.frame_number}`;
    }
    // For single images or live stream, don't show frame info
    
    // Create jump button for video entries
    let jumpButton = '';
    if (sourceType === 'video' && defect.timestamp_seconds != null) {
        jumpButton = `
            <button class="jump-to-frame-btn" data-timestamp="${defect.timestamp_seconds}" 
                    title="Jump to this frame in video">
                ⏩ Jump
            </button>
        `;
    }
    
    // Build diagnostic debug panel (collapsible)
    const hasDiagnostics = defect.classification_reason || 
                          defect.diagnostic_patch_count !== undefined;
    
    let debugPanel = '';
    if (hasDiagnostics) {
        const reason = defect.classification_reason || 'No classification details available';
        const patchCount = defect.diagnostic_patch_count !== undefined ? defect.diagnostic_patch_count : 'N/A';
        const aspectRatio = defect.diagnostic_aspect_ratio !== undefined ? defect.diagnostic_aspect_ratio.toFixed(3) : 'N/A';
        const circularity = defect.diagnostic_circularity !== undefined ? defect.diagnostic_circularity.toFixed(3) : 'N/A';
        const areaPx = defect.diagnostic_area_px !== undefined ? defect.diagnostic_area_px : 'N/A';
        const brightnessDelta = defect.diagnostic_brightness_delta !== undefined ? defect.diagnostic_brightness_delta.toFixed(3) : 'N/A';
        const edgeDelta = defect.diagnostic_edge_density_delta !== undefined ? defect.diagnostic_edge_density_delta.toFixed(3) : 'N/A';
        const anomalyScore = defect.diagnostic_avg_anomaly_score !== undefined ? defect.diagnostic_avg_anomaly_score.toFixed(3) : 'N/A';
        
        debugPanel = `
            <div class="log-entry-debug-toggle" onclick="toggleDebugPanel(this)">
                🔍 Show Debug Info
            </div>
            <div class="log-entry-debug-panel" style="display: none;">
                <div class="debug-section">
                    <strong>Classification Reason:</strong>
                    <div class="debug-reason">${reason}</div>
                </div>
                <div class="debug-section">
                    <strong>Raw Feature Values:</strong>
                    <table class="debug-table">
                        <tr>
                            <td>Patch Count:</td>
                            <td><code>${patchCount}</code></td>
                        </tr>
                        <tr>
                            <td>Aspect Ratio:</td>
                            <td><code>${aspectRatio}</code> (height/width)</td>
                        </tr>
                        <tr>
                            <td>Circularity:</td>
                            <td><code>${circularity}</code> (0-1, 1=circle)</td>
                        </tr>
                        <tr>
                            <td>Area:</td>
                            <td><code>${areaPx}</code> px²</td>
                        </tr>
                        <tr>
                            <td>Brightness Δ:</td>
                            <td><code>${brightnessDelta}</code> (z-score)</td>
                        </tr>
                        <tr>
                            <td>Edge Density Δ:</td>
                            <td><code>${edgeDelta}</code> (z-score)</td>
                        </tr>
                        <tr>
                            <td>Avg Anomaly Score:</td>
                            <td><code>${anomalyScore}</code></td>
                        </tr>
                    </table>
                </div>
                <div class="debug-hint">
                    💡 Use these values to tune classification thresholds in <code>config.py</code>
                </div>
            </div>
        `;
    }
    
    entry.innerHTML = `
        <div class="log-entry-type">
            ${typeName} · ${confidence}%${frameInfo}
            ${jumpButton}
        </div>
        <div class="log-entry-details">
            Position: ${position} | Size: ${defect.w}x${defect.h}px
        </div>
        ${debugPanel}
    `;
    
    // Add click handler for jump button
    if (sourceType === 'video') {
        const btn = entry.querySelector('.jump-to-frame-btn');
        if (btn) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                jumpToFrame(parseFloat(btn.dataset.timestamp));
            });
        }
    }
    
    return entry;
}

// Toggle debug panel visibility
function toggleDebugPanel(toggleElement) {
    const panel = toggleElement.nextElementSibling;
    if (panel && panel.classList.contains('log-entry-debug-panel')) {
        const isHidden = panel.style.display === 'none';
        panel.style.display = isHidden ? 'block' : 'none';
        toggleElement.textContent = isHidden ? '🔍 Hide Debug Info' : '🔍 Show Debug Info';
    }
}

async function exportLog() {
    try {
        window.open(`${API_BASE}/log/export`, '_blank');
        showStatus('Log exported to CSV', 'success');
    } catch (error) {
        console.error('Export failed:', error);
        showStatus('Export failed', 'error');
    }
}

async function clearLog() {
    if (!confirm('Are you sure you want to clear all logs? This cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/log/`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('defect-log').innerHTML = 
                '<p class="log-empty">No defects detected yet</p>';
            updateResultsSummary([]);
            showStatus('Log cleared', 'success');
        }
    } catch (error) {
        console.error('Clear log failed:', error);
        showStatus('Failed to clear log', 'error');
    }
}

// ================================================================
// Utility Functions
// ================================================================

function showStatus(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);
    
    // You could add a toast notification here
    // For now, we'll just log to console
}

// ================================================================
console.log('Fabric Defect Detection System - Ready');
