/**
 * Desktop Viewer for Live Stream
 * 
 * Manages the Live Stream tab UI:
 * - Session creation/management
 * - Display phone URL and QR code
 * - WebSocket connection to receive live updates
 * - Status monitoring
 */

(function() {
    'use strict';

    // State
    let activeSession = null;
    let viewerWs = null;
    let reconnectAttempts = 0;
    let reconnectTimer = null;

    // Elements (will be initialized when tab is active)
    let elements = {};

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    function init() {
        console.log('[LiveViewer] Initializing');

        // Set up tab visibility listener
        const liveTab = document.querySelector('[data-tab="live"]');
        if (liveTab) {
            liveTab.addEventListener('click', () => {
                setTimeout(onTabVisible, 100);
            });
        }

        // Check if live tab is initially active
        const liveTabPanel = document.getElementById('live-tab');
        if (liveTabPanel && liveTabPanel.classList.contains('active')) {
            onTabVisible();
        }

        // Listen for tab switches
        document.addEventListener('click', (e) => {
            const tabButton = e.target.closest('.tab-button');
            if (tabButton) {
                const tab = tabButton.dataset.tab;
                if (tab === 'live') {
                    setTimeout(onTabVisible, 100);
                } else {
                    onTabHidden();
                }
            }
        });
    }

    function onTabVisible() {
        console.log('[LiveViewer] Tab visible');
        
        // Get/refresh elements
        elements.connectCard = document.getElementById('live-connect-card');
        elements.statusChip = document.getElementById('live-status-chip');
        elements.phoneUrl = document.getElementById('live-phone-url');
        elements.qrCode = document.getElementById('live-qr-code');
        elements.copyBtn = document.getElementById('live-copy-btn');
        elements.startBtn = document.getElementById('live-start-btn');
        elements.endBtn = document.getElementById('live-end-btn');
        elements.statsContainer = document.getElementById('live-stats');
        elements.frameCount = document.getElementById('live-stat-frames');
        elements.defectCount = document.getElementById('live-stat-defects');
        elements.estLength = document.getElementById('live-stat-length');
        elements.mode = document.getElementById('live-stat-mode');

        // Set up event listeners
        if (elements.startBtn) {
            elements.startBtn.onclick = startSession;
        }
        if (elements.endBtn) {
            elements.endBtn.onclick = endSession;
        }
        if (elements.copyBtn) {
            elements.copyBtn.onclick = copyPhoneUrl;
        }

        // Check for existing session
        checkSession();
    }

    function onTabHidden() {
        console.log('[LiveViewer] Tab hidden');
        
        // Disconnect WebSocket but keep session active
        if (viewerWs) {
            viewerWs.close();
            viewerWs = null;
        }
        
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
    }

    async function checkSession() {
        try {
            const response = await fetch('/live/info');
            const data = await response.json();

            if (data.has_session) {
                // Session exists
                activeSession = data;
                updateUI(data);
                
                // Connect viewer WebSocket
                connectViewer();
            } else {
                // No session
                showStartButton();
            }
        } catch (err) {
            console.error('[LiveViewer] Check session error:', err);
            showError('Failed to check session status');
        }
    }

    async function startSession() {
        elements.startBtn.disabled = true;
        elements.startBtn.textContent = 'Creating Session...';

        try {
            const response = await fetch('/live/session/start', {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Failed to start session');
            }

            // Wait a moment then check status
            await new Promise(resolve => setTimeout(resolve, 500));
            await checkSession();

        } catch (err) {
            console.error('[LiveViewer] Start session error:', err);
            showError(err.message);
            elements.startBtn.disabled = false;
            elements.startBtn.textContent = 'Start Live Stream';
        }
    }

    async function endSession() {
        if (!confirm('End the live stream session?')) {
            return;
        }

        elements.endBtn.disabled = true;

        try {
            await fetch('/live/session/stop', {
                method: 'POST'
            });

            // Disconnect viewer
            if (viewerWs) {
                viewerWs.close();
                viewerWs = null;
            }

            activeSession = null;
            showStartButton();

            // Reload defect log to show new entries
            if (typeof loadLog === 'function') {
                loadLog();
            }

        } catch (err) {
            console.error('[LiveViewer] End session error:', err);
            showError('Failed to end session');
            elements.endBtn.disabled = false;
        }
    }

    function updateUI(data) {
        // Update status chip
        const statusMap = {
            'waiting': { text: 'Waiting for Phone', color: '#fbbf24' },
            'connected': { text: 'Phone Connected', color: '#10b981' },
            'disconnected': { text: 'Disconnected', color: '#ef4444' }
        };

        const status = statusMap[data.status] || statusMap['waiting'];
        elements.statusChip.textContent = status.text;
        elements.statusChip.style.backgroundColor = status.color;

        // Show/hide connect card
        if (data.phone_url) {
            elements.connectCard.style.display = 'block';
            
            // Update URL
            elements.phoneUrl.value = data.phone_url;
            elements.copyBtn.disabled = false;

            // Update QR code
            if (data.qr_code_data) {
                elements.qrCode.src = 'data:image/png;base64,' + data.qr_code_data;
                elements.qrCode.style.display = 'block';
            } else {
                elements.qrCode.style.display = 'none';
            }
        } else {
            // No LAN IP detected
            elements.connectCard.innerHTML = `
                <div style="text-align: center; padding: 40px; color: #ef4444;">
                    <h3>⚠️ No Network Connection</h3>
                    <p>Connect the laptop to Wi-Fi first.</p>
                    <p style="margin-top: 15px; font-size: 14px; color: #666;">
                        Options:<br>
                        • Connect to your Wi-Fi network<br>
                        • Use your phone's hotspot<br>
                        • Then restart the server
                    </p>
                </div>
            `;
        }

        // Show stats and end button
        elements.statsContainer.style.display = 'flex';
        elements.startBtn.style.display = 'none';
        elements.endBtn.style.display = 'inline-block';
        elements.endBtn.disabled = false;
    }

    function showStartButton() {
        if (elements.connectCard) {
            elements.connectCard.style.display = 'none';
        }
        if (elements.statsContainer) {
            elements.statsContainer.style.display = 'none';
        }
        if (elements.startBtn) {
            elements.startBtn.style.display = 'inline-block';
            elements.startBtn.disabled = false;
            elements.startBtn.textContent = 'Start Live Stream';
        }
        if (elements.endBtn) {
            elements.endBtn.style.display = 'none';
        }
        if (elements.statusChip) {
            elements.statusChip.textContent = 'No Active Session';
            elements.statusChip.style.backgroundColor = '#6b7280';
        }
    }

    function connectViewer() {
        if (viewerWs && viewerWs.readyState === WebSocket.OPEN) {
            return; // Already connected
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/live/ws/viewer`;

        console.log('[LiveViewer] Connecting to:', wsUrl);

        viewerWs = new WebSocket(wsUrl);

        viewerWs.onopen = () => {
            console.log('[LiveViewer] Connected');
            reconnectAttempts = 0;
        };

        viewerWs.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleViewerMessage(data);
            } catch (err) {
                console.error('[LiveViewer] Parse error:', err);
            }
        };

        viewerWs.onerror = (err) => {
            console.error('[LiveViewer] WebSocket error:', err);
        };

        viewerWs.onclose = () => {
            console.log('[LiveViewer] Disconnected');
            viewerWs = null;

            // Try to reconnect if tab is still visible and session is active
            if (activeSession && document.getElementById('live-tab').classList.contains('active')) {
                reconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
                console.log(`[LiveViewer] Reconnecting in ${delay}ms...`);
                
                reconnectTimer = setTimeout(() => {
                    connectViewer();
                }, delay);
            }
        };

        // Send ping every 10 seconds
        const pingInterval = setInterval(() => {
            if (viewerWs && viewerWs.readyState === WebSocket.OPEN) {
                viewerWs.send(JSON.stringify({ type: 'ping' }));
            } else {
                clearInterval(pingInterval);
            }
        }, 10000);
    }

    function handleViewerMessage(data) {
        switch (data.type) {
            case 'status':
            case 'pong':
                // Update stats
                if (elements.frameCount) {
                    elements.frameCount.textContent = data.frame_count || 0;
                }
                if (elements.defectCount) {
                    elements.defectCount.textContent = data.defects_logged || 0;
                }

                // Update status
                if (data.phone_connected && elements.statusChip) {
                    elements.statusChip.textContent = 'Phone Connected • Analyzing';
                    elements.statusChip.style.backgroundColor = '#10b981';
                }
                break;

            case 'frame':
                // Update real-time stats
                if (elements.frameCount) {
                    elements.frameCount.textContent = data.frame_number || 0;
                }
                if (elements.estLength) {
                    elements.estLength.textContent = (data.est_length_m || 0).toFixed(2) + ' m';
                }

                // Reload defect log periodically (every 10 frames)
                if (data.frame_number % 10 === 0) {
                    if (typeof loadLog === 'function') {
                        loadLog();
                    }
                }
                break;

            case 'ended':
                showError('Session ended: ' + data.message);
                checkSession();
                break;
        }
    }

    function copyPhoneUrl() {
        if (!elements.phoneUrl) return;

        elements.phoneUrl.select();
        elements.phoneUrl.setSelectionRange(0, 99999);

        try {
            document.execCommand('copy');
            
            // Visual feedback
            const originalText = elements.copyBtn.textContent;
            elements.copyBtn.textContent = '✓ Copied';
            setTimeout(() => {
                elements.copyBtn.textContent = originalText;
            }, 2000);
        } catch (err) {
            showError('Failed to copy URL');
        }
    }

    function showError(message) {
        console.error('[LiveViewer]', message);
        // Could show a toast notification here
        alert(message);
    }

    console.log('[LiveViewer] Script loaded');
})();
