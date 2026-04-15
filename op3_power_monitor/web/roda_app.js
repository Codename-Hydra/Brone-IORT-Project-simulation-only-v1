/**
 * BRone Roda Monitor — Dashboard Client
 * Connects to WebSocket on port 9091 and updates all UI elements.
 *
 * Wheel mapping:
 *   FL = Front Left    FR = Front Right
 *   RL = Rear Left     RR = Rear Right
 */

const WS_URL = `ws://${window.location.hostname}:9091`;
const HISTORY_LENGTH = 60;

const COLOR_LABEL = '#768390';
const COLOR_GRID = 'rgba(48, 54, 61, 0.5)';

// ============================================================
// State
// ============================================================
let ws = null;
let reconnectTimer = null;
let startTime = Date.now();
let powerHistory = [];

const $ = id => document.getElementById(id);

const batteryCanvas = $('battery-gauge');
const batteryCtx = batteryCanvas.getContext('2d');
const chartCanvas = $('power-chart');
const chartCtx = chartCanvas.getContext('2d');
const motionCanvas = $('motion-canvas');
const motionCtx = motionCanvas.getContext('2d');

// ============================================================
// WebSocket
// ============================================================

function connect() {
    if (ws && ws.readyState <= WebSocket.OPEN) return;
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        setStatus('ws-status', true, 'WebSocket');
        if (reconnectTimer) { clearInterval(reconnectTimer); reconnectTimer = null; }
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            updateDashboard(data);
        } catch (e) {
            console.warn('Invalid JSON:', e);
        }
    };

    ws.onclose = () => {
        setStatus('ws-status', false, 'Disconnected');
        scheduleReconnect();
    };

    ws.onerror = () => ws.close();
}

function scheduleReconnect() {
    if (!reconnectTimer) {
        reconnectTimer = setInterval(() => connect(), 3000);
    }
}

function setStatus(id, connected, label) {
    const badge = $(id);
    const dot = badge.querySelector('.status-dot');
    const text = badge.querySelector('.status-text');
    dot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
    text.textContent = label;
}

// ============================================================
// Uptime
// ============================================================

function updateUptime() {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    const h = String(Math.floor(elapsed / 3600)).padStart(2, '0');
    const m = String(Math.floor((elapsed % 3600) / 60)).padStart(2, '0');
    const s = String(elapsed % 60).padStart(2, '0');
    const el = $('uptime-badge');
    if (el) el.querySelector('.uptime-text').textContent = `${h}:${m}:${s}`;
}

// ============================================================
// Main Update
// ============================================================

function updateDashboard(data) {
    const battery = data.battery || {};
    const wheels = data.wheels || {};
    const motion = data.motion || {};
    const system = data.system || {};
    const totals = data.totals || {};

    // Battery
    updateBattery(battery);

    // Ping
    updatePing(system);

    // Power history
    powerHistory.push(totals.total_power_W || 0);
    if (powerHistory.length > HISTORY_LENGTH) powerHistory.shift();
    drawChart();

    // Wheels
    updateWheels(wheels);

    // Motion
    updateMotion(motion);

    // Summary cards
    $('total-power').textContent = totals.total_power_W != null ? totals.total_power_W.toFixed(2) : '--';
    $('total-current').textContent = totals.total_current_A != null ? totals.total_current_A.toFixed(2) : '--';
    $('avg-rpm').textContent = totals.avg_rpm != null ? totals.avg_rpm.toFixed(0) : '--';
    $('soc-card').textContent = battery.soc_pct != null ? battery.soc_pct.toFixed(1) : '--';

    // Conclusion
    updateConclusion(battery, totals, system);
}

// ============================================================
// Battery Gauge (6S LiPo: 18V – 25.2V)
// ============================================================

function updateBattery(battery) {
    const v = battery.voltage_V;
    const status = battery.status;

    $('battery-voltage').textContent = v != null ? v.toFixed(1) : '--';
    $('battery-status').textContent = status || 'UNKNOWN';
    $('battery-soc').textContent = battery.soc_pct != null ? battery.soc_pct.toFixed(1) + '%' : '--%';
    $('cell-voltage').textContent = battery.cell_voltage_V != null ? battery.cell_voltage_V.toFixed(2) + ' V' : '-- V';
    $('runtime').textContent = battery.runtime_hours != null
        ? (battery.runtime_hours > 99 ? '99+ h' : battery.runtime_hours.toFixed(1) + ' h')
        : '-- h';

    let color, statusClass;
    if (status === 'OK') {
        color = '#00ff88'; statusClass = '';
    } else if (status === 'LOW') {
        color = '#ffaa00'; statusClass = 'low';
    } else if (status === 'CRITICAL') {
        color = '#ff4444'; statusClass = 'critical';
    } else {
        color = COLOR_LABEL; statusClass = '';
    }

    $('battery-voltage').style.color = color;
    $('battery-status').className = `battery-status ${statusClass}`;
    drawBatteryGauge(v, color);
}

function drawBatteryGauge(voltage, color) {
    const w = batteryCanvas.width, h = batteryCanvas.height;
    const cx = w / 2, cy = h / 2, r = 105, lw = 14;

    batteryCtx.clearRect(0, 0, w, h);

    const startAngle = 0.75 * Math.PI;
    const endAngle = 2.25 * Math.PI;

    // Background arc
    batteryCtx.beginPath();
    batteryCtx.arc(cx, cy, r, startAngle, endAngle);
    batteryCtx.strokeStyle = 'rgba(48, 54, 61, 0.6)';
    batteryCtx.lineWidth = lw;
    batteryCtx.lineCap = 'round';
    batteryCtx.stroke();

    // Value arc (18V – 25.2V range)
    if (voltage != null) {
        const ratio = Math.max(0, Math.min(1, (voltage - 18.0) / 7.2));
        const valueAngle = startAngle + ratio * (endAngle - startAngle);
        batteryCtx.beginPath();
        batteryCtx.arc(cx, cy, r, startAngle, valueAngle);
        batteryCtx.strokeStyle = color;
        batteryCtx.lineWidth = lw;
        batteryCtx.lineCap = 'round';
        batteryCtx.shadowColor = color;
        batteryCtx.shadowBlur = 18;
        batteryCtx.stroke();
        batteryCtx.shadowBlur = 0;
    }

    // Tick labels
    batteryCtx.fillStyle = COLOR_LABEL;
    batteryCtx.font = '11px Inter, sans-serif';
    batteryCtx.textAlign = 'center';
    const ticks = [18, 20, 22, 24, 25];
    for (const v of ticks) {
        const ratio = (v - 18) / 7.2;
        const angle = startAngle + ratio * (endAngle - startAngle);
        const tx = cx + (r + 20) * Math.cos(angle);
        const ty = cy + (r + 20) * Math.sin(angle);
        batteryCtx.fillText(v + '', tx, ty + 4);
    }
}

// ============================================================
// Ping Status
// ============================================================

function updatePing(system) {
    const ping = system.ping_ms;
    const badge = $('ping-status');
    const dot = badge.querySelector('.status-dot');
    const text = badge.querySelector('.status-text');

    if (ping != null) {
        text.textContent = `Ping: ${ping > 900 ? 'TIMEOUT' : ping.toFixed(0) + 'ms'}`;
        if (ping < 50) {
            dot.className = 'status-dot connected';
        } else if (ping < 100) {
            dot.className = 'status-dot warning';
        } else {
            dot.className = 'status-dot disconnected';
        }
    }
}

// ============================================================
// Wheel Cards
// ============================================================

function updateWheels(wheels) {
    const mapping = { 'wheel_FL': 'wheel-FL', 'wheel_FR': 'wheel-FR', 'wheel_RL': 'wheel-RL', 'wheel_RR': 'wheel-RR' };

    for (const [key, elemId] of Object.entries(mapping)) {
        const w = wheels[key];
        const card = $(elemId);
        if (!card || !w) continue;

        const vals = card.querySelectorAll('.wc-val');
        vals.forEach(el => {
            const f = el.dataset.field;
            if (f === 'torque') el.textContent = w.torque_Nm != null ? w.torque_Nm.toFixed(3) + ' N·m' : '-- N·m';
            if (f === 'rpm') el.textContent = w.rpm != null ? w.rpm.toFixed(0) : '--';
            if (f === 'current') el.textContent = w.current_A != null ? w.current_A.toFixed(3) + ' A' : '-- A';
            if (f === 'power') el.textContent = w.power_W != null ? w.power_W.toFixed(2) + ' W' : '-- W';
        });
    }
}

// ============================================================
// Motion Vector Canvas
// ============================================================

function updateMotion(motion) {
    $('motion-vx').textContent = motion.vx != null ? motion.vx.toFixed(3) : '0.000';
    $('motion-vy').textContent = motion.vy != null ? motion.vy.toFixed(3) : '0.000';
    $('motion-omega').textContent = motion.omega != null ? motion.omega.toFixed(3) : '0.000';

    drawMotionVector(motion.vx || 0, motion.vy || 0, motion.omega || 0);
}

function drawMotionVector(vx, vy, omega) {
    const c = motionCanvas;
    const ctx = motionCtx;
    const w = c.width, h = c.height;
    const cx = w / 2, cy = h / 2;

    ctx.clearRect(0, 0, w, h);

    // Grid
    ctx.strokeStyle = COLOR_GRID;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cx, 10); ctx.lineTo(cx, h - 10);
    ctx.moveTo(10, cy); ctx.lineTo(w - 10, cy);
    ctx.stroke();

    // Circle boundary
    const R = 90;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 2 * Math.PI);
    ctx.strokeStyle = 'rgba(88, 166, 255, 0.15)';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Robot body (center square)
    ctx.fillStyle = 'rgba(88, 166, 255, 0.08)';
    ctx.strokeStyle = 'rgba(88, 166, 255, 0.3)';
    ctx.lineWidth = 1.5;
    ctx.fillRect(cx - 20, cy - 20, 40, 40);
    ctx.strokeRect(cx - 20, cy - 20, 40, 40);

    // Velocity arrow
    const scale = R / 0.5;  // max speed = 0.5 m/s
    // Sesuai konvensi ESP/Controller kita: vx = maju/mundur, vy = kanan/kiri
    // Sesuai konvensi layar (canvas): X+ = kanan, Y- = atas
    // Maka: sumbu Y layar (ay) digerakkan oleh vx (maju = UP = y negatif)
    //       sumbu X layar (ax) digerakkan oleh vy (kanan = RIGHT = x positif)
    const ax = vy * scale;
    const ay = -vx * scale;
    const mag = Math.sqrt(ax * ax + ay * ay);

    if (mag > 2) {
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + ax, cy + ay);
        ctx.strokeStyle = '#00ff88';
        ctx.lineWidth = 3;
        ctx.shadowColor = '#00ff88';
        ctx.shadowBlur = 8;
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Arrowhead
        const angle = Math.atan2(ay, ax);
        const aSize = 10;
        ctx.beginPath();
        ctx.moveTo(cx + ax, cy + ay);
        ctx.lineTo(cx + ax - aSize * Math.cos(angle - 0.4), cy + ay - aSize * Math.sin(angle - 0.4));
        ctx.moveTo(cx + ax, cy + ay);
        ctx.lineTo(cx + ax - aSize * Math.cos(angle + 0.4), cy + ay - aSize * Math.sin(angle + 0.4));
        ctx.strokeStyle = '#00ff88';
        ctx.lineWidth = 2;
        ctx.stroke();
    }

    // Rotation indicator (arc)
    if (Math.abs(omega) > 0.01) {
        const rotAngle = omega * 1.5;
        ctx.beginPath();
        if (omega > 0) {
            ctx.arc(cx, cy, 35, -Math.PI / 2, -Math.PI / 2 + rotAngle);
        } else {
            ctx.arc(cx, cy, 35, -Math.PI / 2 + rotAngle, -Math.PI / 2);
        }
        ctx.strokeStyle = '#bc8cff';
        ctx.lineWidth = 3;
        ctx.shadowColor = '#bc8cff';
        ctx.shadowBlur = 6;
        ctx.stroke();
        ctx.shadowBlur = 0;
    }

    // Labels
    ctx.fillStyle = COLOR_LABEL;
    ctx.font = '10px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Y+', cx, 12);
    ctx.fillText('Y−', cx, h - 4);
    ctx.textAlign = 'left';
    ctx.fillText('X+', w - 22, cy - 4);
    ctx.textAlign = 'right';
    ctx.fillText('X−', 22, cy - 4);
}

// ============================================================
// Power Chart
// ============================================================

function drawChart() {
    const canvas = chartCanvas;
    const ctx = chartCtx;
    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const w = rect.width, h = rect.height;

    const pad = { top: 18, right: 18, bottom: 28, left: 52 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;

    ctx.clearRect(0, 0, w, h);

    const vals = powerHistory.filter(v => v != null);
    let yMax = vals.length ? Math.max(...vals) + 5 : 50;
    yMax = Math.ceil(yMax / 10) * 10;
    const yMin = 0;

    // Grid
    ctx.strokeStyle = COLOR_GRID;
    ctx.lineWidth = 1;
    ctx.fillStyle = COLOR_LABEL;
    ctx.font = '11px JetBrains Mono, monospace';
    ctx.textAlign = 'right';

    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
        const y = pad.top + (plotH / ySteps) * i;
        const val = yMax - ((yMax - yMin) / ySteps) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + plotW, y);
        ctx.stroke();
        ctx.fillText(val.toFixed(0) + 'W', pad.left - 6, y + 4);
    }

    // X labels
    ctx.textAlign = 'center';
    for (let i = 0; i <= 6; i++) {
        const x = pad.left + (plotW / 6) * i;
        const sec = -60 + (60 / 6) * i;
        ctx.fillText(sec + 's', x, h - 6);
    }

    if (vals.length < 2) return;

    // Line
    ctx.beginPath();
    let started = false;
    for (let i = 0; i < powerHistory.length; i++) {
        const v = powerHistory[i];
        if (v == null) { started = false; continue; }
        const x = pad.left + (i / (HISTORY_LENGTH - 1)) * plotW;
        const y = pad.top + plotH * (1 - (v - yMin) / (yMax - yMin));
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = '#bc8cff';
    ctx.lineWidth = 2.5;
    ctx.shadowColor = '#bc8cff';
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Fill
    const lastIdx = powerHistory.length - 1;
    ctx.lineTo(pad.left + (lastIdx / (HISTORY_LENGTH - 1)) * plotW, pad.top + plotH);
    const firstIdx = powerHistory.findIndex(v => v != null);
    ctx.lineTo(pad.left + (firstIdx / (HISTORY_LENGTH - 1)) * plotW, pad.top + plotH);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    gradient.addColorStop(0, 'rgba(188, 140, 255, 0.15)');
    gradient.addColorStop(1, 'rgba(188, 140, 255, 0.0)');
    ctx.fillStyle = gradient;
    ctx.fill();
}

// ============================================================
// Conclusion
// ============================================================

function updateConclusion(battery, totals, system) {
    const icon = $('conclusion-icon');
    const title = $('conclusion-title');
    const text = $('conclusion-text');
    const ts = $('conclusion-ts');

    const soc = battery.soc_pct;
    const status = battery.status;
    const power = totals.total_power_W;
    const ping = system.ping_ms;

    let level, emoji, titleText, bodyParts = [];

    if (status === 'CRITICAL' || (ping && ping > 500)) {
        level = 'critical'; emoji = '🔴'; titleText = 'KRITIS — Perlu Tindakan Segera';
    } else if (status === 'LOW' || (ping && ping > 100)) {
        level = 'low'; emoji = '⚠️'; titleText = 'PERHATIAN — Perlu Monitoring';
    } else if (status === 'OK') {
        level = 'ok'; emoji = '✅'; titleText = 'SISTEM NORMAL';
    } else {
        level = ''; emoji = '🛞'; titleText = 'Menunggu Data...';
    }

    if (battery.voltage_V != null) {
        bodyParts.push(`Baterai <strong>${battery.voltage_V.toFixed(1)}V</strong> (${status}, SOC: ${soc != null ? soc.toFixed(1) : '--'}%).`);
    }
    if (power != null) {
        bodyParts.push(`Total daya: <strong>${power.toFixed(1)}W</strong>.`);
    }
    if (battery.runtime_hours != null && battery.runtime_hours < 99) {
        bodyParts.push(`Estimasi sisa waktu: <strong>${battery.runtime_hours.toFixed(1)} jam</strong>.`);
    }
    if (ping != null) {
        const pingStatus = ping > 100 ? '⚠️ TINGGI' : ping > 900 ? '🔴 TIMEOUT' : '✅ OK';
        bodyParts.push(`Ping: <strong>${ping > 900 ? 'TIMEOUT' : ping.toFixed(0) + 'ms'}</strong> (${pingStatus}).`);
    }

    icon.textContent = emoji;
    title.textContent = titleText;
    title.className = `conclusion-title ${level}`;
    text.innerHTML = bodyParts.join(' ') || 'Menunggu data...';
    ts.textContent = `Update: ${new Date().toLocaleTimeString('id-ID')}`;
}

// ============================================================
// Init
// ============================================================

window.addEventListener('load', () => {
    drawBatteryGauge(null, COLOR_LABEL);
    drawChart();
    drawMotionVector(0, 0, 0);
    connect();
    setInterval(updateUptime, 1000);
});

window.addEventListener('resize', drawChart);
