// Frontend Core JavaScript Logic
document.addEventListener("DOMContentLoaded", () => {
    // Constants & State
    const API_HOST = window.location.host;
    const WS_URL = `ws://${API_HOST}/api/ws/events`;
    
    let ws = null;
    let soundEnabled = true;
    let occupancyChart = null;
    let distributionChart = null;
    
    // KPI references
    const kpiOccupancy = document.getElementById("kpi-occupancy");
    const kpiTotalCustomers = document.getElementById("kpi-total-customers");
    const kpiDwell = document.getElementById("kpi-dwell");
    const kpiAlerts = document.getElementById("kpi-alerts");
    
    // Pipeline control references
    const dotStatus = document.getElementById("pipeline-status-dot");
    const textStatus = document.getElementById("pipeline-status-text");
    const btnStop = document.getElementById("btn-stop-pipeline");
    const btnStart = document.getElementById("btn-start-pipeline");
    
    // History buffers for chart (max 30 data points)
    const occupancyLabels = [];
    const occupancyData = [];
    
    // ================== TAB NAVIGATION ==================
    const navItems = document.querySelectorAll(".nav-item");
    const tabContents = document.querySelectorAll(".tab-content");
    
    navItems.forEach(item => {
        item.addEventListener("click", (e) => {
            e.preventDefault();
            const tabId = item.getAttribute("data-tab");
            
            navItems.forEach(n => n.classList.remove("active"));
            item.classList.add("active");
            
            tabContents.forEach(content => {
                content.style.display = "none";
            });
            document.getElementById(`tab-${tabId}`).style.display = "block";
            
            // Trigger specific actions based on tab
            if (tabId === "heatmap") {
                loadHeatmapData();
            } else if (tabId === "anomalies") {
                loadAnomalies();
            } else if (tabId === "overview") {
                loadInitialData();
            }
            
            // Update page header titles
            updateHeaderTitles(tabId);
        });
    });
    
    function updateHeaderTitles(tabId) {
        const title = document.getElementById("page-title");
        const subtitle = document.getElementById("page-subtitle");
        
        switch (tabId) {
            case "overview":
                title.innerText = "Live Store Overview";
                subtitle.innerText = "Real-time occupancy tracking and behavior profiling";
                break;
            case "cameras":
                title.innerText = "CCTV Surveillance Grid";
                subtitle.innerText = "Live edge streams processed with YOLOv8 tracking";
                break;
            case "anomalies":
                title.innerText = "Threat & Anomaly Command Center";
                subtitle.innerText = "Security breaches, fall alerts, and cash desk loitering logs";
                break;
            case "heatmap":
                title.innerText = "Spatial Heatmap Insights";
                subtitle.innerText = "Aggregated visual density analysis of customer dwell patterns";
                break;
        }
    }

    // ================== LIVE CLOCK ==================
    function startClock() {
        const liveClock = document.getElementById("live-clock");
        setInterval(() => {
            const now = new Date();
            liveClock.innerText = now.toTimeString().split(" ")[0];
        }, 1000);
    }
    startClock();

    // ================== CHARTS INITIALIZATION ==================
    function initCharts() {
        // 1. Line Chart: Occupancy history
        const ctxLine = document.getElementById("occupancyChart").getContext("2d");
        
        // Fill initial mock history (last 10 points)
        for (let i = 9; i >= 0; i--) {
            const time = new Date(Date.now() - i * 30000);
            occupancyLabels.push(time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
            occupancyData.push(0);
        }
        
        occupancyChart = new Chart(ctxLine, {
            type: "line",
            data: {
                labels: occupancyLabels,
                datasets: [{
                    label: "Store Occupancy",
                    data: occupancyData,
                    borderColor: "#00f2fe",
                    borderWidth: 3,
                    pointBackgroundColor: "#00f2fe",
                    pointHoverRadius: 6,
                    backgroundColor: "rgba(0, 242, 254, 0.05)",
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { color: "rgba(255,255,255,0.03)" },
                        ticks: { color: "#8a92a6", maxTicksLimit: 6 }
                    },
                    y: {
                        grid: { color: "rgba(255,255,255,0.03)" },
                        ticks: { color: "#8a92a6", stepSize: 1 },
                        beginAtZero: true
                    }
                }
            }
        });
        
        // 2. Donut Chart: Zone distribution
        const ctxDonut = document.getElementById("trafficDistributionChart").getContext("2d");
        distributionChart = new Chart(ctxDonut, {
            type: "doughnut",
            data: {
                labels: ["Aisle 1 (Cosmetics)", "Aisle 2 (Skincare)", "Cashier 1 Queue", "Cashier 2 Queue"],
                datasets: [{
                    data: [0, 0, 0, 0],
                    backgroundColor: [
                        "rgba(155, 81, 224, 0.75)",
                        "rgba(79, 172, 254, 0.75)",
                        "rgba(255, 149, 0, 0.75)",
                        "rgba(0, 242, 254, 0.75)"
                    ],
                    borderColor: "rgba(10, 11, 16, 0.9)",
                    borderWidth: 2,
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "bottom",
                        labels: {
                            color: "#8a92a6",
                            font: { family: "Outfit", size: 11 },
                            padding: 12
                        }
                    }
                },
                cutout: "70%"
            }
        });
    }
    initCharts();

    // ================== WEBSOCKET TELEMETRY STREAM ==================
    function connectWebSocket() {
        console.log("Connecting to WebSocket event stream:", WS_URL);
        ws = new WebSocket(WS_URL);
        
        ws.onopen = () => {
            console.log("WebSocket connection established successfully.");
            dotStatus.className = "status-indicator online";
            textStatus.innerText = "Pipeline: Connected";
        };
        
        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            const type = msg.event_type;
            const data = msg.data;
            
            // 1. Add raw event to logs list
            appendEventToTable(msg);
            
            // 2. Update real-time stats
            updateLiveStats(type, data);
        };
        
        ws.onclose = () => {
            console.warn("WebSocket closed. Reconnecting in 5 seconds...");
            dotStatus.className = "status-indicator offline";
            textStatus.innerText = "Pipeline: Reconnecting";
            setTimeout(connectWebSocket, 5000);
        };
    }
    connectWebSocket();

    // ================== TELEMETRY LOG DISPLAY ==================
    const eventLogRows = document.getElementById("event-log-rows");
    
    function appendEventToTable(eventObj) {
        const emptyRow = document.getElementById("empty-event-row");
        if (emptyRow) emptyRow.remove();
        
        const timestamp = new Date(eventObj.timestamp).toLocaleTimeString();
        const type = eventObj.event_type;
        const data = eventObj.data;
        
        let details = "";
        let camera = data.camera_id || "N/A";
        let zone = data.zone || data.to_zone || "general";
        
        if (type === "entry") {
            details = `Customer #${data.track_id} entered store floor.`;
        } else if (type === "exit") {
            details = `Customer #${data.track_id} left store. Store dwell: ${data.duration_seconds}s.`;
        } else if (type === "queue_entry") {
            details = `Customer #${data.track_id} joined checkout queue.`;
        } else if (type === "queue_exit") {
            details = `Customer #${data.track_id} left checkout. Queue time: ${data.payload?.wait_seconds || 0}s.`;
        } else if (type === "shelf_interaction") {
            details = `Customer #${data.track_id} standing near shelves.`;
        } else if (type === "anomaly") {
            details = `<strong style="color: #ff3b30">${data.description}</strong>`;
            camera = data.camera_id;
            zone = data.zone || "Alert Zone";
            
            // Render popup toast notification
            showToastAlert(data);
        } else if (type === "anomaly_resolved") {
            // Remove resolve visual or reload
            loadAnomalies();
            return;
        } else {
            details = JSON.stringify(data);
        }
        
        const newRow = document.createElement("tr");
        newRow.className = type === "anomaly" ? "anomaly-row animate-pulse" : "";
        newRow.innerHTML = `
            <td>${timestamp}</td>
            <td><strong>${camera}</strong></td>
            <td><span class="event-badge ${type}">${type.replace("_", " ")}</span></td>
            <td><code>${zone.replace("_", " ").toUpperCase()}</code></td>
            <td>${details}</td>
        `;
        
        eventLogRows.insertBefore(newRow, eventLogRows.firstChild);
        
        // Truncate list to max 30 items
        if (eventLogRows.children.length > 30) {
            eventLogRows.removeChild(eventLogRows.lastChild);
        }
    }

    // ================== REAL-TIME STATS PROPAGATION ==================
    function updateLiveStats(type, data) {
        // Update occupancy KPI
        if (data.store_occupancy !== undefined) {
            kpiOccupancy.innerText = data.store_occupancy;
            updateOccupancyChart(data.store_occupancy);
        }
        
        // Triggered on entry
        if (type === "entry") {
            kpiTotalCustomers.innerText = parseInt(kpiTotalCustomers.innerText || 0) + 1;
        }
        
        // Triggered on exit
        if (type === "exit" && data.duration_seconds) {
            const currentTotal = parseInt(kpiTotalCustomers.innerText || 0);
            // Rough rolling update for visualization
            kpiDwell.innerText = `${Math.round(data.duration_seconds)}s`;
        }
        
        // Triggered on anomaly
        if (type === "anomaly") {
            const currentAlerts = parseInt(kpiAlerts.innerText || 0) + 1;
            kpiAlerts.innerText = currentAlerts;
            document.getElementById("sidebar-alert-badge").innerText = currentAlerts;
            
            const alertCard = document.getElementById("kpi-alerts-card");
            alertCard.classList.add("alerting");
            document.getElementById("kpi-alerts-trend").innerHTML = `<i class="fa-solid fa-bell"></i> Critical Alert Active`;
            
            // Play chime sound
            playAlertSound();
            
            // Reload anomalies if active tab
            const activeTab = document.querySelector(".nav-item.active").getAttribute("data-tab");
            if (activeTab === "anomalies") {
                loadAnomalies();
            }
        }
        
        // Dynamically extract active zone occupancy count from DOM for Donut chart
        if (type === "entry" || type === "exit" || type === "zone_transition" || type === "queue_entry" || type === "queue_exit") {
            fetchInitialDistribution();
        }
    }
    
    function updateOccupancyChart(currentVal) {
        if (!occupancyChart) return;
        const now = new Date();
        const timeLabel = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        
        occupancyLabels.push(timeLabel);
        occupancyData.push(currentVal);
        
        if (occupancyLabels.length > 30) {
            occupancyLabels.shift();
            occupancyData.shift();
        }
        
        occupancyChart.update();
    }
    
    async function fetchInitialDistribution() {
        try {
            const res = await fetch("/api/metrics");
            const data = await res.json();
            
            // Update queue KPI representation
            const queue1 = data.queue_lengths["CAM 4"] || 0;
            const queue2 = data.queue_lengths["CAM 5"] || 0;
            
            // Update distribution donut: Aisle 1, Aisle 2, Queue 1, Queue 2
            // We fetch camera occupancy mock values
            if (distributionChart) {
                // Random/computed values for aisles based on total store occupancy
                const total = data.current_occupancy;
                const qSum = queue1 + queue2;
                const remain = Math.max(0, total - qSum);
                const aisle1 = Math.round(remain * 0.6);
                const aisle2 = Math.max(0, remain - aisle1);
                
                distributionChart.data.datasets[0].data = [aisle1, aisle2, queue1, queue2];
                distributionChart.update();
            }
        } catch (e) {
            console.error("Error fetching distribution metrics:", e);
        }
    }

    // ================== REST DATA INGESTION ==================
    async function loadInitialData() {
        document.getElementById("event-spinner").style.display = "inline-block";
        try {
            // 1. Fetch metrics
            const resMetrics = await fetch("/api/metrics");
            const metrics = await resMetrics.json();
            
            kpiOccupancy.innerText = metrics.current_occupancy;
            kpiTotalCustomers.innerText = metrics.total_customers;
            kpiDwell.innerText = `${metrics.avg_dwell_seconds}s`;
            kpiAlerts.innerText = metrics.active_anomalies;
            document.getElementById("sidebar-alert-badge").innerText = metrics.active_anomalies;
            
            const alertCard = document.getElementById("kpi-alerts-card");
            if (metrics.active_anomalies > 0) {
                alertCard.classList.add("alerting");
                document.getElementById("kpi-alerts-trend").innerHTML = `<i class="fa-solid fa-bell"></i> Alerts Active`;
            } else {
                alertCard.classList.remove("alerting");
                document.getElementById("kpi-alerts-trend").innerText = "No active alerts";
            }
            
            // 2. Fetch recent events
            const resEvents = await fetch("/api/events?limit=15");
            const events = await resEvents.json();
            
            eventLogRows.innerHTML = "";
            if (events.length === 0) {
                eventLogRows.innerHTML = `<tr id="empty-event-row"><td colspan="5" class="text-center text-muted">Awaiting incoming telemetry streams...</td></tr>`;
            } else {
                events.forEach(e => {
                    // Normalize DB rows to match WebSocket structures
                    appendEventToTable({
                        timestamp: e.timestamp,
                        event_type: e.event_type,
                        data: {
                            camera_id: e.camera_id,
                            track_id: e.track_id,
                            zone: e.zone,
                            description: e.event_type === "anomaly" ? JSON.parse(e.payload).description : "",
                            duration_seconds: e.event_type === "exit" ? JSON.parse(e.payload).duration_seconds : 0,
                            payload: JSON.parse(e.payload)
                        }
                    });
                });
            }
            
            fetchInitialDistribution();
        } catch (e) {
            console.error("Error loading initial data:", e);
        } finally {
            document.getElementById("event-spinner").style.display = "none";
        }
    }
    loadInitialData();

    // ================== ANOMALY MANAGEMENT ==================
    async function loadAnomalies() {
        try {
            const res = await fetch("/api/anomalies?limit=30");
            const list = await res.json();
            
            const rows = document.getElementById("anomalies-log-rows");
            rows.innerHTML = "";
            
            let activeCount = 0;
            
            if (list.length === 0) {
                rows.innerHTML = `<tr id="empty-anomaly-row"><td colspan="7" class="text-center text-muted">No anomalies detected. Store operations running smoothly.</td></tr>`;
            } else {
                list.forEach(a => {
                    const is_active = a.status === "active";
                    if (is_active) activeCount++;
                    
                    const time = new Date(a.timestamp).toLocaleString();
                    const actionBtn = is_active 
                        ? `<button class="btn btn-sm btn-primary btn-resolve" data-id="${a.anomaly_id}"><i class="fa-solid fa-check"></i> Resolve</button>`
                        : `<span style="color: var(--accent-green)"><i class="fa-solid fa-circle-check"></i> Cleared</span>`;
                        
                    const statusBadge = is_active
                        ? `<span class="event-badge anomaly">Active</span>`
                        : `<span class="event-badge entry">Resolved</span>`;
                        
                    const tr = document.createElement("tr");
                    tr.innerHTML = `
                        <td>${time}</td>
                        <td><strong>${a.camera_id}</strong></td>
                        <td><code>${a.track_id !== null ? 'Track #' + a.track_id : 'System'}</code></td>
                        <td><span style="font-weight:700; color: #ff453a">${a.anomaly_type.replace("_", " ").toUpperCase()}</span></td>
                        <td>${a.description}</td>
                        <td>${statusBadge}</td>
                        <td>${actionBtn}</td>
                    `;
                    rows.appendChild(tr);
                });
            }
            
            document.getElementById("alerts-count-badge").innerText = `${activeCount} Active Alerts`;
            kpiAlerts.innerText = activeCount;
            document.getElementById("sidebar-alert-badge").innerText = activeCount;
            
            const alertCard = document.getElementById("kpi-alerts-card");
            if (activeCount > 0) {
                alertCard.classList.add("alerting");
                document.getElementById("kpi-alerts-trend").innerHTML = `<i class="fa-solid fa-bell"></i> Alerts Active`;
            } else {
                alertCard.classList.remove("alerting");
                document.getElementById("kpi-alerts-trend").innerText = "No active alerts";
            }
            
            // Add click listeners to resolve buttons
            document.querySelectorAll(".btn-resolve").forEach(btn => {
                btn.addEventListener("click", async () => {
                    const id = btn.getAttribute("data-id");
                    await resolveAnomaly(id);
                });
            });
        } catch (e) {
            console.error("Error loading anomalies list:", e);
        }
    }
    
    async function resolveAnomaly(anomalyId) {
        try {
            const res = await fetch(`/api/anomalies/${anomalyId}/resolve`, { method: "POST" });
            if (res.ok) {
                loadAnomalies();
            }
        } catch (e) {
            console.error("Error resolving anomaly:", e);
        }
    }

    // ================== TOAST ALERTS & CHIME ==================
    const notificationArea = document.getElementById("notification-area");
    
    function showToastAlert(data) {
        const toast = document.createElement("div");
        toast.className = "toast";
        toast.innerHTML = `
            <div class="toast-icon"><i class="fa-solid fa-circle-exclamation"></i></div>
            <div class="toast-content">
                <div class="toast-title">${data.anomaly_type.replace("_", " ").toUpperCase()}</div>
                <div class="toast-desc">${data.description}</div>
                <div class="toast-time">Camera: ${data.camera_id} | Live Alert</div>
            </div>
        `;
        notificationArea.appendChild(toast);
        
        // Remove toast after 6 seconds
        setTimeout(() => {
            toast.style.animation = "slide-in 0.3s ease-out reverse";
            setTimeout(() => toast.remove(), 300);
        }, 6000);
    }
    
    const audio = document.getElementById("alert-chime");
    function playAlertSound() {
        if (soundEnabled && audio) {
            audio.currentTime = 0;
            audio.play().catch(e => console.log("Audio playback blocked by browser policies. Need interaction."));
        }
    }
    
    // Toggle Sound Button
    const btnSound = document.getElementById("btn-sound-toggle");
    const soundIcon = document.getElementById("sound-icon");
    btnSound.addEventListener("click", () => {
        soundEnabled = !soundEnabled;
        if (soundEnabled) {
            soundIcon.className = "fa-solid fa-volume-high";
            btnSound.querySelector("span").innerText = "Alert Chime: ON";
        } else {
            soundIcon.className = "fa-solid fa-volume-xmark";
            btnSound.querySelector("span").innerText = "Alert Chime: OFF";
        }
    });

    // ================== HEATMAP CANVAS RENDER ==================
    const heatmapSelect = document.getElementById("heatmap-cam-select");
    const btnRefreshHeatmap = document.getElementById("btn-refresh-heatmap");
    const heatmapCanvas = document.getElementById("heatmapCanvas");
    const ctxHeat = heatmapCanvas.getContext("2d");
    
    heatmapSelect.addEventListener("change", () => loadHeatmapData());
    btnRefreshHeatmap.addEventListener("click", () => loadHeatmapData());
    
    async function loadHeatmapData() {
        const camId = heatmapSelect.value;
        ctxHeat.clearRect(0, 0, heatmapCanvas.width, heatmapCanvas.height);
        
        // Draw loading text
        ctxHeat.fillStyle = "#8a92a6";
        ctxHeat.font = "16px Inter";
        ctxHeat.textAlign = "center";
        ctxHeat.fillText(`Loading track coordinates for ${camId}...`, heatmapCanvas.width / 2, heatmapCanvas.height / 2);
        
        try {
            const res = await fetch(`/api/heatmap/${camId}`);
            const data = await res.json();
            const points = data.points;
            
            // Clear loading
            ctxHeat.clearRect(0, 0, heatmapCanvas.width, heatmapCanvas.height);
            
            document.getElementById("heatmap-total-points").innerText = points.length;
            
            if (points.length === 0) {
                ctxHeat.fillText("No track history available for this camera. Run the pipeline first.", heatmapCanvas.width / 2, heatmapCanvas.height / 2);
                document.getElementById("heatmap-hot-spot").innerText = "None";
                document.getElementById("heatmap-congestion").innerText = "None (No data)";
                return;
            }
            
            // Render heatmap density cloud
            // Draw background grid representation
            ctxHeat.strokeStyle = "rgba(255, 255, 255, 0.02)";
            ctxHeat.lineWidth = 1;
            const gridSize = 40;
            for (let x = 0; x < heatmapCanvas.width; x += gridSize) {
                ctxHeat.beginPath();
                ctxHeat.moveTo(x, 0);
                ctxHeat.lineTo(x, heatmapCanvas.height);
                ctxHeat.stroke();
            }
            for (let y = 0; y < heatmapCanvas.height; y += gridSize) {
                ctxHeat.beginPath();
                ctxHeat.moveTo(0, y);
                ctxHeat.lineTo(heatmapCanvas.width, y);
                ctxHeat.stroke();
            }
            
            // Draw track points as glowing spots
            // To construct density, we draw soft radial gradients for each point
            points.forEach(pt => {
                // Scale normalized coordinate: 0.0 - 1.0 to canvas coordinates
                const cx = pt.x * heatmapCanvas.width;
                const cy = pt.y * heatmapCanvas.height;
                
                const rad = 25;
                const grad = ctxHeat.createRadialGradient(cx, cy, 2, cx, cy, rad);
                
                // Color mapping: red for shelves/checkout queues, green/blue for corridors
                let colorGlow = "rgba(0, 242, 254, 0.08)"; // Cyan
                if (pt.zone && (pt.zone.includes("shelves") || pt.zone.includes("queue") || pt.zone.includes("desk"))) {
                    colorGlow = "rgba(255, 59, 48, 0.08)"; // Red/Hot
                }
                
                grad.addColorStop(0, colorGlow);
                grad.addColorStop(1, "rgba(0, 0, 0, 0)");
                
                ctxHeat.fillStyle = grad;
                ctxHeat.beginPath();
                ctxHeat.arc(cx, cy, rad, 0, Math.PI * 2);
                ctxHeat.fill();
            });
            
            // Calculate hot spots based on zone labels
            const zoneCounts = {};
            points.forEach(pt => {
                if (pt.zone) {
                    zoneCounts[pt.zone] = (zoneCounts[pt.zone] || 0) + 1;
                }
            });
            
            let hotSpot = "General Pathway";
            let maxCount = 0;
            for (const [zone, count] of Object.entries(zoneCounts)) {
                if (count > maxCount && zone !== "general") {
                    maxCount = count;
                    hotSpot = zone.replace("_", " ").title();
                }
            }
            
            document.getElementById("heatmap-hot-spot").innerText = hotSpot;
            
            // Congestion index based on points length
            let congestion = "Low";
            if (points.length > 2500) congestion = "High Congestion";
            else if (points.length > 800) congestion = "Moderate Congestion";
            document.getElementById("heatmap-congestion").innerText = congestion;
            
        } catch (e) {
            console.error("Error loading heatmap points:", e);
            ctxHeat.fillText("Error loading data from server.", heatmapCanvas.width / 2, heatmapCanvas.height / 2);
        }
    }
    
    // Helper to capitalize words
    String.prototype.title = function() {
        return this.split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
    };

    // ================== PIPELINE LIFECYCLE CONTROLS ==================
    btnStop.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/pipeline/stop", { method: "POST" });
            if (res.ok) {
                dotStatus.className = "status-indicator offline";
                textStatus.innerText = "Pipeline: Offline";
                btnStop.style.display = "none";
                btnStart.style.display = "inline-block";
            }
        } catch (e) {
            console.error("Error stopping pipeline:", e);
        }
    });
    
    btnStart.addEventListener("click", async () => {
        try {
            const res = await fetch("/api/pipeline/start", { method: "POST" });
            if (res.ok) {
                dotStatus.className = "status-indicator online";
                textStatus.innerText = "Pipeline: Connected";
                btnStart.style.display = "none";
                btnStop.style.display = "inline-block";
            }
        } catch (e) {
            console.error("Error starting pipeline:", e);
        }
    });
});
