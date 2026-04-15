/**
 * OP3 Power Monitor — Dashboard Client
 * Connects to WebSocket server and updates all UI elements in real-time.
 *
 * Joint mapping from OP3.robot config:
 *   ID  1: r_sho_pitch    ID  2: l_sho_pitch
 *   ID  3: r_sho_roll     ID  4: l_sho_roll
 *   ID  5: r_el           ID  6: l_el
 *   ID  7: r_hip_yaw      ID  8: l_hip_yaw
 *   ID  9: r_hip_roll     ID 10: l_hip_roll
 *   ID 11: r_hip_pitch    ID 12: l_hip_pitch
 *   ID 13: r_knee         ID 14: l_knee
 *   ID 15: r_ank_pitch    ID 16: l_ank_pitch
 *   ID 17: r_ank_roll     ID 18: l_ank_roll
 *   ID 19: head_pan       ID 20: head_tilt
 *   ID200: open-cr (sensor)
 */

// ============================================================
// Constants & Joint Configuration — mirrors OP3.robot exactly
// ============================================================
const WS_URL = `ws://${window.location.hostname}:9090`;
const HISTORY_LENGTH = 60;
const VOLTAGE_OK = 11.5;
const VOLTAGE_LOW = 11.0;

// Brighter colors for chart/gauge labels (no gray!)
const COLOR_LABEL = '#768390';
const COLOR_GRID = 'rgba(48, 54, 61, 0.5)';

/**
 * The authoritative joint list, matching OP3.robot config order & IDs.
 * Each joint has: id, name, and group (for filtering).
 */
const JOINTS = [
    { id:  1, name: 'r_sho_pitch', group: 'r_arm' },
    { id:  2, name: 'l_sho_pitch', group: 'l_arm' },
    { id:  3, name: 'r_sho_roll',  group: 'r_arm' },
    { id:  4, name: 'l_sho_roll',  group: 'l_arm' },
    { id:  5, name: 'r_el',        group: 'r_arm' },
    { id:  6, name: 'l_el',        group: 'l_arm' },
    { id:  7, name: 'r_hip_yaw',   group: 'r_leg' },
    { id:  8, name: 'l_hip_yaw',   group: 'l_leg' },
    { id:  9, name: 'r_hip_roll',  group: 'r_leg' },
    { id: 10, name: 'l_hip_roll',  group: 'l_leg' },
    { id: 11, name: 'r_hip_pitch', group: 'r_leg' },
    { id: 12, name: 'l_hip_pitch', group: 'l_leg' },
    { id: 13, name: 'r_knee',      group: 'r_leg' },
    { id: 14, name: 'l_knee',      group: 'l_leg' },
    { id: 15, name: 'r_ank_pitch', group: 'r_leg' },
    { id: 16, name: 'l_ank_pitch', group: 'l_leg' },
    { id: 17, name: 'r_ank_roll',  group: 'r_leg' },
    { id: 18, name: 'l_ank_roll',  group: 'l_leg' },
    { id: 19, name: 'head_pan',    group: 'head' },
    { id: 20, name: 'head_tilt',   group: 'head' },
];

const JOINT_NAMES = JOINTS.map(j => j.name);

// ============================================================
// State
// ============================================================
let ws = null;
let voltageHistory = [];
let reconnectTimer = null;
let startTime = Date.now();
let currentFilter = 'all';
let latestJoints = {};
let selectedJoint = null;   // currently clicked/selected joint name

// ============================================================
// DOM references
// ============================================================
const $ = id => document.getElementById(id);
const batteryCanvas = $('battery-gauge');
const batteryCtx = batteryCanvas.getContext('2d');
const chartCanvas = $('voltage-chart');
const chartCtx = chartCanvas.getContext('2d');

// ============================================================
// WebSocket Connection
// ============================================================

function connect() {
    if (ws && ws.readyState <= WebSocket.OPEN) return;

    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        setConnectionStatus('ws-status', true, 'WebSocket');
        console.log('[Dashboard] WebSocket connected');
        if (reconnectTimer) {
            clearInterval(reconnectTimer);
            reconnectTimer = null;
        }
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
        setConnectionStatus('ws-status', false, 'Disconnected');
        console.log('[Dashboard] WebSocket disconnected');
        scheduleReconnect();
    };

    ws.onerror = () => {
        ws.close();
    };
}

function scheduleReconnect() {
    if (!reconnectTimer) {
        reconnectTimer = setInterval(() => {
            console.log('[Dashboard] Reconnecting...');
            connect();
        }, 3000);
    }
}

function setConnectionStatus(eleId, connected, label) {
    const badge = $(eleId);
    const dot = badge.querySelector('.status-dot');
    const text = badge.querySelector('.status-text');
    dot.className = `status-dot ${connected ? 'connected' : 'disconnected'}`;
    text.textContent = label;
}

// ============================================================
// Uptime Counter
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
    const joints = data.joints || {};
    const totals = data.totals || {};
    const voltSummary = data.voltage_summary || {};

    latestJoints = joints;

    // Manager status
    setConnectionStatus('mgr-status', data.manager_connected,
        data.manager_connected ? 'op3_manager ✓' : 'op3_manager ✗');

    // Battery
    updateBattery(battery.voltage_V, battery.status);

    // Voltage history for chart
    voltageHistory.push(battery.voltage_V || null);
    if (voltageHistory.length > HISTORY_LENGTH) voltageHistory.shift();
    drawChart();

    // Joint table
    updateJointTable(joints);

    // Robot body SVG
    updateRobotMap(joints);

    // Summary cards
    const totalPower = totals.estimated_total_power_W;
    // total_effort_abs is in raw ticks. Map to roughly N.m string
    const totalEffortRaw = totals.total_effort_abs;
    const totalEffortNm = totalEffortRaw != null ? (totalEffortRaw / 1193.0 * 4.1).toFixed(2) : '--';

    $('total-power').textContent = totalPower != null ? totalPower.toFixed(2) : '--';
    $('total-effort').textContent = totalEffortNm;
    $('avg-voltage').textContent = voltSummary.avg_joint_input_V != null ? voltSummary.avg_joint_input_V.toFixed(2) : '--';
    $('min-voltage').textContent = voltSummary.min_joint_input_V != null ? voltSummary.min_joint_input_V.toFixed(2) : '--';

    // Conclusion
    updateConclusion(battery, joints, totals, voltSummary);
}

// ============================================================
// Battery Gauge (bigger: 260x260)
// ============================================================

function updateBattery(voltage, status) {
    const vElem = $('battery-voltage');
    const sElem = $('battery-status');

    vElem.textContent = voltage != null ? voltage.toFixed(2) : '--';
    sElem.textContent = status || 'UNKNOWN';

    let color, statusClass;
    if (status === 'OK') {
        color = getComputedStyle(document.documentElement).getPropertyValue('--accent-ok').trim();
        statusClass = '';
    } else if (status === 'LOW') {
        color = getComputedStyle(document.documentElement).getPropertyValue('--accent-low').trim();
        statusClass = 'low';
    } else if (status === 'CRITICAL') {
        color = getComputedStyle(document.documentElement).getPropertyValue('--accent-critical').trim();
        statusClass = 'critical';
    } else {
        color = COLOR_LABEL;
        statusClass = '';
    }

    vElem.style.color = color;
    sElem.className = `battery-status ${statusClass}`;

    drawBatteryGauge(voltage, color);
}

function drawBatteryGauge(voltage, color) {
    const w = batteryCanvas.width;
    const h = batteryCanvas.height;
    const cx = w / 2;
    const cy = h / 2;
    const r = 105;          // bigger radius
    const lineWidth = 14;   // thicker ring

    batteryCtx.clearRect(0, 0, w, h);

    // Background arc
    const startAngle = 0.75 * Math.PI;
    const endAngle = 2.25 * Math.PI;

    batteryCtx.beginPath();
    batteryCtx.arc(cx, cy, r, startAngle, endAngle);
    batteryCtx.strokeStyle = 'rgba(48, 54, 61, 0.6)';
    batteryCtx.lineWidth = lineWidth;
    batteryCtx.lineCap = 'round';
    batteryCtx.stroke();

    // Value arc
    if (voltage != null) {
        const ratio = Math.max(0, Math.min(1, (voltage - 9.0) / 4.0));
        const valueAngle = startAngle + ratio * (endAngle - startAngle);

        batteryCtx.beginPath();
        batteryCtx.arc(cx, cy, r, startAngle, valueAngle);
        batteryCtx.strokeStyle = color;
        batteryCtx.lineWidth = lineWidth;
        batteryCtx.lineCap = 'round';
        batteryCtx.shadowColor = color;
        batteryCtx.shadowBlur = 18;
        batteryCtx.stroke();
        batteryCtx.shadowBlur = 0;
    }

    // Tick marks — brighter color
    batteryCtx.fillStyle = COLOR_LABEL;
    batteryCtx.font = '12px Inter, sans-serif';
    batteryCtx.textAlign = 'center';
    const ticks = [9, 10, 11, 12, 13];
    for (const v of ticks) {
        const ratio = (v - 9) / 4;
        const angle = startAngle + ratio * (endAngle - startAngle);
        const tx = cx + (r + 20) * Math.cos(angle);
        const ty = cy + (r + 20) * Math.sin(angle);
        batteryCtx.fillText(v + '', tx, ty + 4);
    }
}

// ============================================================
// Voltage Chart (taller)
// ============================================================

function drawChart() {
    const canvas = chartCanvas;
    const ctx = chartCtx;

    const rect = canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.scale(dpr, dpr);
    const w = rect.width;
    const h = rect.height;

    const pad = { top: 18, right: 18, bottom: 28, left: 46 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;

    ctx.clearRect(0, 0, w, h);

    const vals = voltageHistory.filter(v => v != null);
    let yMin = vals.length ? Math.min(...vals) - 0.3 : 10.0;
    let yMax = vals.length ? Math.max(...vals) + 0.3 : 13.0;
    yMin = Math.floor(yMin * 2) / 2;
    yMax = Math.ceil(yMax * 2) / 2;
    if (yMax - yMin < 1) { yMin -= 0.5; yMax += 0.5; }

    // Grid
    ctx.strokeStyle = COLOR_GRID;
    ctx.lineWidth = 1;
    ctx.fillStyle = COLOR_LABEL;
    ctx.font = '12px JetBrains Mono, monospace';
    ctx.textAlign = 'right';

    const ySteps = 5;
    for (let i = 0; i <= ySteps; i++) {
        const y = pad.top + (plotH / ySteps) * i;
        const val = yMax - ((yMax - yMin) / ySteps) * i;
        ctx.beginPath();
        ctx.moveTo(pad.left, y);
        ctx.lineTo(pad.left + plotW, y);
        ctx.stroke();
        ctx.fillText(val.toFixed(1), pad.left - 6, y + 4);
    }

    // Threshold lines
    const drawThreshold = (v, color, label) => {
        if (v >= yMin && v <= yMax) {
            const y = pad.top + plotH * (1 - (v - yMin) / (yMax - yMin));
            ctx.save();
            ctx.setLineDash([4, 4]);
            ctx.strokeStyle = color;
            ctx.globalAlpha = 0.5;
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(pad.left + plotW, y);
            ctx.stroke();
            ctx.restore();
            ctx.fillStyle = color;
            ctx.globalAlpha = 0.7;
            ctx.fillText(label, pad.left + plotW, y - 4);
            ctx.globalAlpha = 1.0;
        }
    };
    drawThreshold(VOLTAGE_OK, '#00ff88', 'OK');
    drawThreshold(VOLTAGE_LOW, '#ffaa00', 'LOW');

    // X axis labels
    ctx.fillStyle = COLOR_LABEL;
    ctx.textAlign = 'center';
    ctx.font = '11px JetBrains Mono, monospace';
    for (let i = 0; i <= 6; i++) {
        const x = pad.left + (plotW / 6) * i;
        const sec = -60 + (60 / 6) * i;
        ctx.fillText(sec + 's', x, h - 6);
    }

    // Data line
    if (vals.length < 2) return;

    ctx.beginPath();
    let started = false;
    for (let i = 0; i < voltageHistory.length; i++) {
        const v = voltageHistory[i];
        if (v == null) { started = false; continue; }
        const x = pad.left + (i / (HISTORY_LENGTH - 1)) * plotW;
        const y = pad.top + plotH * (1 - (v - yMin) / (yMax - yMin));
        if (!started) { ctx.moveTo(x, y); started = true; }
        else ctx.lineTo(x, y);
    }

    ctx.strokeStyle = '#00ff88';
    ctx.lineWidth = 2.5;
    ctx.shadowColor = '#00ff88';
    ctx.shadowBlur = 8;
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Fill under curve
    const lastIdx = voltageHistory.length - 1;
    const lastX = pad.left + (lastIdx / (HISTORY_LENGTH - 1)) * plotW;
    ctx.lineTo(lastX, pad.top + plotH);
    let firstIdx = voltageHistory.findIndex(v => v != null);
    const firstX = pad.left + (firstIdx / (HISTORY_LENGTH - 1)) * plotW;
    ctx.lineTo(firstX, pad.top + plotH);
    ctx.closePath();
    const gradient = ctx.createLinearGradient(0, pad.top, 0, pad.top + plotH);
    gradient.addColorStop(0, 'rgba(0, 255, 136, 0.15)');
    gradient.addColorStop(1, 'rgba(0, 255, 136, 0.0)');
    ctx.fillStyle = gradient;
    ctx.fill();
}

// ============================================================
// Joint Table — IDs from OP3.robot
// ============================================================

function updateJointTable(joints) {
    const tbody = $('joint-tbody');

    // Build rows if empty
    if (tbody.children.length === 0) {
        for (const j of JOINTS) {
            const tr = document.createElement('tr');
            tr.id = `row-${j.name}`;
            tr.dataset.group = j.group;
            tr.innerHTML = `
                <td class="cell-id">${j.id}</td>
                <td>${j.name}</td>
                <td class="cell-vin">--</td>
                <td class="cell-pos">--</td>
                <td class="cell-effort">--</td>
                <td class="cell-current">--</td>
                <td class="cell-power">--</td>
            `;
            // Hover: highlight
            tr.addEventListener('mouseenter', () => highlightJoint(j.name, true));
            tr.addEventListener('mouseleave', () => highlightJoint(j.name, false));
            // Click: select (toggle)
            tr.addEventListener('click', () => selectJoint(j.name));
            tbody.appendChild(tr);
        }
    }

    // Update values
    for (const j of JOINTS) {
        const jd = joints[j.name];
        const tr = $(`row-${j.name}`);
        if (!tr || !jd) continue;

        const cells = tr.querySelectorAll('td');
        const vin = jd.input_voltage_V;
        const pos = jd.position_rad != null ? (jd.position_rad * 180 / Math.PI).toFixed(1) : '--';
        
        let effStr = '--';
        if (jd.effort_raw != null) {
            // Converts raw current ticks (-1193 to 1193) to approx Torque in N.m
            // based on XM430-W350 nominal stall torque (4.1 N.m @ 12.0V)
            const effNm = (jd.effort_raw / 1193.0) * 4.1;
            effStr = effNm.toFixed(3);
        }
        
        const cur = jd.current_A != null ? jd.current_A.toFixed(4) : 'N/A';
        const pow = jd.estimated_power_W != null ? jd.estimated_power_W.toFixed(3) : 'N/A';

        cells[2].textContent = vin != null ? vin.toFixed(2) : 'N/A';
        cells[2].className = vin != null ? voltageClass(vin) : 'cell-na';
        cells[3].textContent = pos;
        cells[4].textContent = effStr;
        cells[5].textContent = cur;
        cells[5].className = cur === 'N/A' ? 'cell-na' : '';
        cells[6].textContent = pow;
        cells[6].className = pow === 'N/A' ? 'cell-na' : '';
    }
}

function voltageClass(v) {
    if (v >= VOLTAGE_OK) return 'cell-ok';
    if (v >= VOLTAGE_LOW) return 'cell-low';
    return 'cell-critical';
}

// ============================================================
// Joint Table Filter
// ============================================================

function setupFilters() {
    const filterDiv = $('table-filter');
    if (!filterDiv) return;
    filterDiv.addEventListener('click', (e) => {
        if (!e.target.classList.contains('filter-btn')) return;
        const group = e.target.dataset.group;
        currentFilter = group;

        // Update button state
        filterDiv.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');

        // Update row visibility
        const rows = $('joint-tbody').querySelectorAll('tr');
        rows.forEach(row => {
            if (group === 'all' || row.dataset.group === group) {
                row.dataset.hidden = 'false';
            } else {
                row.dataset.hidden = 'true';
            }
        });
    });
}

// ============================================================
// Click-Select Logic — purple accent
// ============================================================

function selectJoint(name) {
    // Toggle: if already selected, deselect
    if (selectedJoint === name) {
        selectedJoint = null;
    } else {
        selectedJoint = name;
    }

    // Update table rows
    $('joint-tbody').querySelectorAll('tr').forEach(row => {
        row.classList.remove('selected');
    });
    if (selectedJoint) {
        const row = $(`row-${selectedJoint}`);
        if (row) row.classList.add('selected');
    }

    // Update SVG dots
    document.querySelectorAll('.joint-dot').forEach(dot => {
        dot.classList.remove('selected');
    });
    if (selectedJoint) {
        const dot = document.querySelector(`.joint-dot[data-joint="${selectedJoint}"]`);
        if (dot) dot.classList.add('selected');
    }
}

// ============================================================
// Robot SVG Map — Interactive
// ============================================================

function updateRobotMap(joints) {
    for (const j of JOINTS) {
        const dot = document.querySelector(`.joint-dot[data-joint="${j.name}"]`);
        if (!dot) continue;

        const jd = joints[j.name];
        let base;
        if (!jd || jd.input_voltage_V == null) {
            base = 'joint-dot unknown';
        } else {
            const v = jd.input_voltage_V;
            if (v >= VOLTAGE_OK) base = 'joint-dot ok';
            else if (v >= VOLTAGE_LOW) base = 'joint-dot low';
            else base = 'joint-dot critical';
        }
        // Preserve selected class
        if (selectedJoint === j.name) base += ' selected';
        dot.className.baseVal = base;
    }
}

function setupRobotTooltips() {
    const tooltip = $('robot-tooltip');
    const ttName = $('tt-name');
    const ttVin = $('tt-vin');
    const ttPos = $('tt-pos');

    document.querySelectorAll('.joint-dot').forEach(dot => {
        const jName = dot.dataset.joint;

        dot.addEventListener('mouseenter', () => {
            const jd = latestJoints[jName];
            const j = JOINTS.find(x => x.name === jName);
            ttName.textContent = `${jName} (ID ${j ? j.id : '?'})`;

            if (jd) {
                const vin = jd.input_voltage_V != null ? jd.input_voltage_V.toFixed(2) + ' V' : 'N/A';
                const pos = jd.position_rad != null ? (jd.position_rad * 180 / Math.PI).toFixed(1) + '°' : '--';
                ttVin.textContent = vin;
                ttPos.textContent = pos;
            } else {
                ttVin.textContent = 'N/A';
                ttPos.textContent = '--';
            }

            tooltip.style.display = 'flex';
            highlightJoint(jName, true);
        });

        dot.addEventListener('mouseleave', () => {
            tooltip.style.display = 'none';
            highlightJoint(jName, false);
        });

        // Click on SVG dot → select
        dot.addEventListener('click', () => {
            selectJoint(jName);
        });
    });
}

function highlightJoint(name, on) {
    // Table row hover glow (blue)
    const row = $(`row-${name}`);
    if (row) {
        if (on) row.classList.add('highlight');
        else row.classList.remove('highlight');
    }

    // SVG dot — enlarge on hover from table
    const dot = document.querySelector(`.joint-dot[data-joint="${name}"]`);
    if (dot) {
        if (on) {
            dot.setAttribute('r', '10');
            dot.style.strokeWidth = '2';
        } else {
            // Reset to original size
            const orig = ['r_sho_pitch','l_sho_pitch','r_hip_yaw','l_hip_yaw','r_knee','l_knee'].includes(name) ? 7 : 6;
            dot.setAttribute('r', orig);
            dot.style.strokeWidth = '1';
        }
    }
}

// ============================================================
// Conclusion Panel — auto-generated narrative
// ============================================================

function updateConclusion(battery, joints, totals, voltSummary) {
    const icon = $('conclusion-icon');
    const title = $('conclusion-title');
    const text = $('conclusion-text');
    const ts = $('conclusion-ts');

    const bVolt = battery.voltage_V;
    const bStatus = battery.status;
    const totalPower = totals.estimated_total_power_W;

    // Count joints with voltage issues
    let lowJoints = [];
    let critJoints = [];
    let totalJointsWithData = 0;

    for (const j of JOINTS) {
        const jd = joints[j.name];
        if (!jd || jd.input_voltage_V == null) continue;
        totalJointsWithData++;
        const v = jd.input_voltage_V;
        if (v < VOLTAGE_LOW) critJoints.push({ name: j.name, v });
        else if (v < VOLTAGE_OK) lowJoints.push({ name: j.name, v });
    }

    let statusLevel, iconEmoji, titleText, bodyParts = [];

    if (bStatus === 'CRITICAL' || critJoints.length > 0) {
        statusLevel = 'critical';
        iconEmoji = '🔴';
        titleText = 'KRITIS — Perlu Tindakan Segera';
    } else if (bStatus === 'LOW' || lowJoints.length > 0) {
        statusLevel = 'low';
        iconEmoji = '⚠️';
        titleText = 'PERHATIAN — Tegangan Menurun';
    } else if (bStatus === 'OK') {
        statusLevel = 'ok';
        iconEmoji = '✅';
        titleText = 'SISTEM NORMAL';
    } else {
        statusLevel = '';
        iconEmoji = '⚡';
        titleText = 'Menunggu Data Baterai...';
    }

    // Build narrative
    if (bVolt != null) {
        bodyParts.push(`Baterai <strong>${bVolt.toFixed(2)}V</strong> (${bStatus}).`);
    }

    if (totalJointsWithData > 0) {
        bodyParts.push(`<strong>${totalJointsWithData}</strong> joint terpantau.`);

        if (critJoints.length > 0) {
            const names = critJoints.map(j => `<strong>${j.name}</strong> (${j.v.toFixed(2)}V)`).join(', ');
            bodyParts.push(`🔴 ${critJoints.length} joint KRITIS: ${names}.`);
        }
        if (lowJoints.length > 0) {
            const names = lowJoints.map(j => `<strong>${j.name}</strong> (${j.v.toFixed(2)}V)`).join(', ');
            bodyParts.push(`⚠️ ${lowJoints.length} joint LOW: ${names}.`);
        }
        if (critJoints.length === 0 && lowJoints.length === 0 && bStatus === 'OK') {
            bodyParts.push('Semua joint beroperasi normal.');
        }
    }

    if (totalPower != null) {
        bodyParts.push(`Total daya: <strong>${totalPower.toFixed(2)}W</strong>.`);
    }

    if (voltSummary.avg_joint_input_V != null) {
        bodyParts.push(`Rata-rata Vin joint: <strong>${voltSummary.avg_joint_input_V.toFixed(2)}V</strong>.`);
    }

    icon.textContent = iconEmoji;
    title.textContent = titleText;
    title.className = `conclusion-title ${statusLevel}`;
    text.innerHTML = bodyParts.join(' ') || 'Menunggu data...';

    // Timestamp
    const now = new Date();
    ts.textContent = `Update: ${now.toLocaleTimeString('id-ID')}`;
}

// ============================================================
// Init
// ============================================================

window.addEventListener('load', () => {
    drawBatteryGauge(null, COLOR_LABEL);
    drawChart();
    setupFilters();
    setupRobotTooltips();
    connect();

    // Uptime ticker
    setInterval(updateUptime, 1000);
});

window.addEventListener('resize', () => {
    drawChart();
});
