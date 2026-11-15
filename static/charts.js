// Shared Chart.js helpers: every chart in the project uses these colours,
// so the charts always match the theme. (Red is never used here: it is only for losses.)
const COLORS = {
  accent: "#10b981",   // emerald
  navy: "#0f172a",
  slate: "#64748b",
  loss: "#ef4444",
};
const PALETTE = ["#10b981", "#0f172a", "#34d399", "#64748b",
                 "#059669", "#6ee7b7", "#334155", "#a7f3d0"];

Chart.defaults.font.family = "Inter, sans-serif";
Chart.defaults.color = "#64748b";
Chart.defaults.maintainAspectRatio = false;   // charts fill their .chart-box height

// Format a number as ₹ with Indian grouping (for tooltips and axes)
function rupees(n) {
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

// Doughnut / pie chart: labels = ["Food","Rent"], values = [5000, 12000]
function drawCircle(canvasId, type, labels, values) {
  return new Chart(document.getElementById(canvasId), {
    type: type,                       // "doughnut" or "pie"
    data: { labels: labels,
            datasets: [{ data: values, backgroundColor: PALETTE, borderWidth: 2, borderColor: "#fff" }] },
    options: {
      plugins: {
        legend: { position: "bottom" },
        tooltip: { callbacks: { label: (c) => ` ${c.label}: ${rupees(c.parsed)}` } },
      },
    },
  });
}

// Bar chart: datasets = [{label:"Income", data:[..], color:"#10b981"}, ...]
function drawBar(canvasId, labels, datasets) {
  return new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: { labels: labels,
            datasets: datasets.map(d => ({ label: d.label, data: d.data,
                                           backgroundColor: d.color, borderRadius: 6 })) },
    options: {
      plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${rupees(c.parsed.y)}` } } },
      scales: { y: { ticks: { callback: (v) => rupees(v) } } },
    },
  });
}

// Line chart: same dataset format as drawBar
function drawLine(canvasId, labels, datasets) {
  return new Chart(document.getElementById(canvasId), {
    type: "line",
    data: { labels: labels,
            datasets: datasets.map(d => ({ label: d.label, data: d.data, borderColor: d.color,
                                           backgroundColor: d.color + "22", fill: d.fill || false,
                                           tension: 0.3, pointRadius: 2 })) },
    options: {
      plugins: { tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${rupees(c.parsed.y)}` } } },
      scales: { y: { ticks: { callback: (v) => rupees(v) } } },
    },
  });
}