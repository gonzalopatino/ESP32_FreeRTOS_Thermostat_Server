// static/api/js/device_detail.js

document.addEventListener("DOMContentLoaded", function () {
  const root = document.getElementById("device-detail-root");
  if (!root) return;

  const serial = root.dataset.deviceSerial;
  const telemetryUrl = root.dataset.telemetryUrl;

  const fromInput = document.getElementById("fromDate");
  const toInput = document.getElementById("toDate");
  const applyBtn = document.getElementById("applyRangeBtn");

  const indoorCtx = document.getElementById("indoorChart");
  const outdoorCtx = document.getElementById("outdoorChart");

  let indoorChart = null;
  let outdoorChart = null;

  function createChart(ctx, label) {
    if (!ctx) return null;

    return new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: label,
            data: [],
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false, // use CSS height
        scales: {
          x: {
            ticks: { autoSkip: true, maxTicksLimit: 8 },
          },
          y: {
            beginAtZero: false,
          },
        },
      },
    });
  }

  indoorChart = createChart(indoorCtx, "Tin (°C)");
  outdoorChart = createChart(outdoorCtx, "Tout (°C)");

  async function loadTelemetry(useDefaultRange = false) {
    const params = new URLSearchParams();
    // Your TelemetrySnapshot.device_id stores the serial string
    params.append("device_id", serial);

    const fromVal = fromInput.value;
    const toVal = toInput.value;

    if (fromVal && toVal) {
      // Match view's parameter names
      params.append("start", fromVal);
      params.append("end", toVal);
    } else if (useDefaultRange) {
      // When no dates set, ask backend for last 24h
      params.append("range", "24h");
    }

    const resp = await fetch(`${telemetryUrl}?${params.toString()}`, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });

    if (!resp.ok) {
      console.error("Failed to load telemetry", resp.status);
      return;
    }

    const payload = await resp.json();
    const rows = payload.results || payload.data || [];

    const labels = rows.map((s) => s.server_ts);
    const indoorData = rows.map((s) => s.temp_inside_c);
    const outdoorData = rows.map((s) => s.temp_outside_c);

    if (indoorChart) {
      indoorChart.data.labels = labels;
      indoorChart.data.datasets[0].data = indoorData;
      indoorChart.update();
    }

    if (outdoorChart) {
      outdoorChart.data.labels = labels;
      outdoorChart.data.datasets[0].data = outdoorData;
      outdoorChart.update();
    }

    const countSpan = document.getElementById("samplesCount");
    if (countSpan) {
      // try count from backend, fall back to rows length
      countSpan.textContent = payload.count ?? rows.length;
    }
  }

  // Initial load: last 24 hours
  loadTelemetry(true);

  // Apply button for custom range
  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      loadTelemetry(false);
    });
  }
});
