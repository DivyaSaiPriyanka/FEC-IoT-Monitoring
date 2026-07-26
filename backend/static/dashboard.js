const REFRESH_MS = 5000;
const charts = {};

const SENSOR_META = {
  temperature: { icon: "🌡", label: "Temperature" },
  humidity: { icon: "💧", label: "Humidity" },
  motion: { icon: "◉", label: "Motion" },
  air_quality: { icon: "AQ", label: "Air Quality" },
  light: { icon: "☀", label: "Light" }
};

function fmtTime(iso) {
  return iso ? new Date(iso).toLocaleTimeString() : "–";
}

function fmtValue(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "–";
  return Number(value).toFixed(2).replace(/\.00$/, "");
}

function metaFor(type) {
  return SENSOR_META[type] || {
    icon: "IoT",
    label: type.replace(/_/g, " ").replace(/\b\w/g, c => c.toUpperCase())
  };
}

function sensorTemplate(type) {
  const meta = metaFor(type);
  const el = document.createElement("article");
  el.className = "sensor-card";
  el.id = `sensor-${type}`;
  el.innerHTML = `
    <div class="sensor-card-head">
      <div class="sensor-name-wrap">
        <div class="sensor-icon">${meta.icon}</div>
        <div>
          <div class="sensor-title">${meta.label}</div>
          <div class="sensor-node" id="node-${type}">No node</div>
        </div>
      </div>
      <div class="sensor-badge" id="badge-${type}">Normal</div>
    </div>
    <div class="sensor-reading">
      <div class="sensor-value" id="value-${type}">–</div>
      <div class="sensor-unit" id="unit-${type}"></div>
    </div>
    <div class="chart-wrap"><canvas id="chart-${type}"></canvas></div>
    <div class="sensor-stats">
      <div class="stat-box"><div class="stat-label">Minimum</div><div class="stat-value" id="min-${type}">–</div></div>
      <div class="stat-box"><div class="stat-label">Maximum</div><div class="stat-value" id="max-${type}">–</div></div>
      <div class="stat-box"><div class="stat-label">Samples</div><div class="stat-value" id="samples-${type}">–</div></div>
    </div>
    <div class="sensor-updated" id="updated-${type}">No recent data</div>
  `;
  return el;
}

function ensureChart(type) {
  if (charts[type]) return charts[type];
  const context = document.getElementById(`chart-${type}`).getContext("2d");
  charts[type] = new Chart(context, {
    type: "line",
    data: { labels: [], datasets: [{ data: [], borderColor: "#0878e8", backgroundColor: "rgba(8,120,232,.12)", fill: true, borderWidth: 2.2, pointRadius: 0, tension: .35 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: true } },
      scales: { x: { display: false }, y: { display: false } }
    }
  });
  return charts[type];
}

function setConnection(ok) {
  ["conn-dot", "sidebar-status-dot"].forEach(id => document.getElementById(id)?.classList.toggle("live", ok));
  document.getElementById("conn-text").textContent = ok ? "Live" : "Offline";
  document.getElementById("sidebar-status-text").textContent = ok ? "Operational" : "Unavailable";
  document.getElementById("backend-health").textContent = ok ? "Healthy" : "Unavailable";
}

function renderNodes(nodes) {
  const list = document.getElementById("node-list");
  document.getElementById("metric-nodes").textContent = nodes.length;
  document.getElementById("node-count-badge").textContent = `${nodes.length} connected`;
  if (!nodes.length) {
    list.innerHTML = '<div class="empty-inline">No fog nodes connected</div>';
    return;
  }
  list.innerHTML = nodes.map(node => `
    <div class="node-row">
      <div><div class="node-name">${node}</div><div class="node-meta">Receiving sensor telemetry</div></div>
      <div class="node-status">Connected</div>
    </div>
  `).join("");
}

function renderAlerts(entries) {
  const alerts = entries.filter(entry => (entry.total_anomalies || 0) > 0);
  const list = document.getElementById("alert-list");
  document.getElementById("alert-count-badge").textContent = `${alerts.length} alerts`;
  if (!alerts.length) {
    list.innerHTML = '<div class="empty-inline">No active alerts</div>';
    return;
  }
  list.innerHTML = alerts.map(entry => `
    <div class="alert-row">
      <div><div class="alert-title">${metaFor(entry.sensor_type).label}</div><div class="alert-meta">Anomalous readings detected</div></div>
      <div class="alert-count">${entry.total_anomalies}</div>
    </div>
  `).join("");
}

async function refreshTimeseries(type) {
  const response = await fetch(`/api/timeseries/${type}?limit=30`);
  const rows = await response.json();
  const chart = ensureChart(type);
  chart.data.labels = rows.map(row => fmtTime(row.received_at));
  chart.data.datasets[0].data = rows.map(row => row.mean);
  chart.update();
}

async function refreshDashboard() {
  try {
    const [summaryResponse, nodesResponse] = await Promise.all([fetch("/api/summary"), fetch("/api/nodes")]);
    if (!summaryResponse.ok || !nodesResponse.ok) throw new Error("Backend unavailable");
    const summary = await summaryResponse.json();
    const nodesData = await nodesResponse.json();
    const entries = summary.sensor_types || [];

    setConnection(true);
    document.getElementById("last-refresh").textContent = new Date().toLocaleTimeString();
    document.getElementById("queue-length").textContent = summary.queue_length ?? 0;
    document.getElementById("metric-sensors").textContent = entries.length;
    document.getElementById("metric-batches").textContent = entries.reduce((sum, item) => sum + (item.total_batches || 0), 0);
    document.getElementById("metric-anomalies").textContent = entries.reduce((sum, item) => sum + (item.total_anomalies || 0), 0);

    renderNodes(nodesData.fog_nodes || []);
    renderAlerts(entries);

    const grid = document.getElementById("sensor-grid");
    if (!entries.length) {
      grid.innerHTML = '<div class="empty-state">Waiting for live sensor data…</div>';
      return;
    }
    if (grid.querySelector(".empty-state")) grid.innerHTML = "";

    for (const entry of entries) {
      const type = entry.sensor_type;
      if (!document.getElementById(`sensor-${type}`)) grid.appendChild(sensorTemplate(type));
      const latest = entry.latest;
      const anomalies = entry.total_anomalies || 0;
      const badge = document.getElementById(`badge-${type}`);
      badge.textContent = anomalies > 0 ? `${anomalies} anomalies` : "Normal";
      badge.classList.toggle("alert", anomalies > 0);
      document.getElementById(`value-${type}`).textContent = fmtValue(latest?.mean);
      document.getElementById(`unit-${type}`).textContent = latest?.unit || "";
      document.getElementById(`node-${type}`).textContent = latest?.fog_node_id || "No node";
      document.getElementById(`min-${type}`).textContent = fmtValue(latest?.min);
      document.getElementById(`max-${type}`).textContent = fmtValue(latest?.max);
      document.getElementById(`samples-${type}`).textContent = latest?.sample_count ?? "–";
      document.getElementById(`updated-${type}`).textContent = `Updated ${fmtTime(latest?.received_at)}`;
      refreshTimeseries(type).catch(console.error);
    }
  } catch (error) {
    console.error(error);
    setConnection(false);
  }
}

document.getElementById("manual-refresh").addEventListener("click", refreshDashboard);
refreshDashboard();
setInterval(refreshDashboard, REFRESH_MS);
