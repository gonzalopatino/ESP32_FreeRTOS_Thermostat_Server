// static/api/js/device_detail.js

document.addEventListener("DOMContentLoaded", function () {
  const root = document.getElementById("device-detail-root");
  if (!root) return;

  const serial = root.dataset.deviceSerial;
  const telemetryUrl = root.dataset.telemetryUrl;

  const fromInput = document.getElementById("fromDate");
  const toInput = document.getElementById("toDate");
  const applyBtn = document.getElementById("applyRangeBtn");

  const tempCtx = document.getElementById("tempChart");

  let tempChart = null;

  function createTempChart(ctx) {
    if (!ctx) return null;

    return new Chart(ctx, {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Tin (°C)",
            data: [],
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.2,
          },
          {
            label: "Tout (°C)",
            data: [],
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.2,
          },
          {
            label: "SP (°C)",
            data: [],
            borderWidth: 2,
            pointRadius: 2,
            tension: 0.2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false, // use the 260px from CSS
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            position: "top",
          },
        },
        scales: {
          x: {
            ticks: {
              autoSkip: true,
              maxTicksLimit: 8,
            },
          },
          y: {
            beginAtZero: false,
          },
        },
      },
    });
  }

  tempChart = createTempChart(tempCtx);

  function formatLabel(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) {
      // if parsing fails, just show raw string
      return isoString;
    }
    const pad = (n) => (n < 10 ? "0" + n : "" + n);
    const mm = pad(d.getMonth() + 1);
    const dd = pad(d.getDate());
    const hh = pad(d.getHours());
    const min = pad(d.getMinutes());
    // Example: 11-28 05:31
    return `${mm}-${dd} ${hh}:${min}`;
  }

  async function loadTelemetry(useDefaultRange = false) {
    const params = new URLSearchParams();
    // your TelemetrySnapshot.device_id stores the serial string
    params.append("device_id", serial);

    const fromVal = fromInput.value;
    const toVal = toInput.value;

    if (fromVal && toVal) {
      params.append("start", fromVal);
      params.append("end", toVal);
    } else if (useDefaultRange) {
      // backend treats 'range=24h' as “last 24 hours”
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

    const labels = rows.map((s) => formatLabel(s.server_ts));
    const tin = rows.map((s) => s.temp_inside_c);
    const tout = rows.map((s) => s.temp_outside_c);
    const sp = rows.map((s) => s.setpoint_c);

    if (tempChart) {
      tempChart.data.labels = labels;
      tempChart.data.datasets[0].data = tin;
      tempChart.data.datasets[1].data = tout;
      tempChart.data.datasets[2].data = sp;
      tempChart.update();
    }

    const countSpan = document.getElementById("samplesCount");
    if (countSpan) {
      countSpan.textContent = payload.count ?? rows.length;
    }
  }

  // Initial load: last 24 hours
  loadTelemetry(true);

  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      loadTelemetry(false);
    });
  }
});
