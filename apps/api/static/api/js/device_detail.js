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

  // Realtime card elements
  const rtCard = document.getElementById("realtime-card");
  const rtTs = document.getElementById("rt-timestamp");
  const rtTin = document.getElementById("rt-tin");
  const rtTout = document.getElementById("rt-tout");
  const rtSp = document.getElementById("rt-sp");
  const rtMode = document.getElementById("rt-mode");
  const rtOut = document.getElementById("rt-out");

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
        maintainAspectRatio: false,
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
      return isoString;
    }
    const pad = (n) => (n < 10 ? "0" + n : "" + n);
    const mm = pad(d.getMonth() + 1);
    const dd = pad(d.getDate());
    const hh = pad(d.getHours());
    const min = pad(d.getMinutes());
    return `${mm}-${dd} ${hh}:${min}`;
  }

  async function loadTelemetry(useDefaultRange = false) {
    const params = new URLSearchParams();
    params.append("device_id", serial);

    const fromVal = fromInput.value;
    const toVal = toInput.value;

    if (fromVal && toVal) {
      params.append("start", fromVal);
      params.append("end", toVal);
    } else if (useDefaultRange) {
      params.append("range", "24h");
    }

    const url =
      params.toString().length > 0
        ? `${telemetryUrl}?${params.toString()}`
        : telemetryUrl;

    let resp;

    try {
      resp = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
    } catch (err) {
      console.error("Failed to fetch telemetry:", err);
      return;
    }

    if (!resp.ok) {
      console.error("Telemetry request failed with status", resp.status);
      return;
    }

    const payload = await resp.json();
    const rows = payload.results || payload.data || [];

   // Sort telemetry by timestamp: oldest → newest
    const data = rows.slice().sort((a, b) => {
      const ta = (a.server_ts || a.device_ts || "");
      const tb = (b.server_ts || b.device_ts || "");
      // ISO 8601 strings sort correctly lexicographically
      return ta.localeCompare(tb);
    });

    console.log(
      "Telemetry order (server_ts, sorted):",
      data.map((s) => s.server_ts || s.device_ts)
    );


    const labels = data.map((s) => formatLabel(s.server_ts));
    const tin = data.map((s) => s.temp_inside_c);
    const tout = data.map((s) => s.temp_outside_c);
    const sp = data.map((s) => s.setpoint_c);

    console.log("Chart labels:", labels);

    if (tempChart) {
      tempChart.data.labels = labels;
      tempChart.data.datasets[0].data = tin;
      tempChart.data.datasets[1].data = tout;
      tempChart.data.datasets[2].data = sp;
      tempChart.update();
    }

    const countSpan = document.getElementById("samplesCount");
    if (countSpan) {
      countSpan.textContent = payload.count ?? data.length;
    }
  }

  // Realtime telemetry (latest sample every 5 seconds)
  async function loadRealtime() {
    if (!rtCard) {
      return;
    }

    const params = new URLSearchParams();
    params.append("device_id", serial);
    params.append("latest", "1");

    const url = `${telemetryUrl}?${params.toString()}`;

    let resp;
    try {
      resp = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
    } catch (err) {
      console.warn("Failed to fetch realtime telemetry:", err);
      return;
    }

    if (!resp.ok) {
      console.warn("Realtime telemetry request failed with status", resp.status);
      return;
    }

    const payload = await resp.json();
    const rows = payload.results || payload.data || [];
    if (!rows.length) {
      // No data yet, just leave card as-is
      return;
    }

    const s = rows[0];

    const ts = s.server_ts || s.device_ts || "";
    if (rtTs) {
      if (ts) {
        const d = new Date(ts);
        const tsText = Number.isNaN(d.getTime())
          ? ts
          : d.toLocaleString() + " UTC";
        rtTs.textContent = "Last update: " + tsText;
      } else {
        rtTs.textContent = "Last update: --";
      }
    }

    if (rtTin) rtTin.textContent = s.temp_inside_c ?? "--";
    if (rtTout) rtTout.textContent = s.temp_outside_c ?? "--";
    if (rtSp) rtSp.textContent = s.setpoint_c ?? "--";
    if (rtMode) rtMode.textContent = s.mode ?? "--";
    if (rtOut) rtOut.textContent = s.output ?? "--";
  }

  // Initial loads
  loadTelemetry(true);
 

  loadRealtime();

  // Realtime poll every 5 seconds
  setInterval(loadRealtime, 5000);

  // Apply button behavior
  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      const fromVal = fromInput.value;
      const toVal = toInput.value;

      // Case 1: both empty, treat as default 24h
      if (!fromVal && !toVal) {
        loadTelemetry(true);
        return;
      }

      // Case 2: only one set, block and nag
      if (!fromVal || !toVal) {
        alert(
          "Please set both From and To, or leave both empty to show the last 24 hours."
        );
        return;
      }

      // Case 3: both set, use explicit range
      loadTelemetry(false);
    });
  }
});
