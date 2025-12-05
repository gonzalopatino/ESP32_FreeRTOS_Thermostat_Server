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
  const rtTempCtx = document.getElementById("rtTempChart"); // new realtime chart vanvas

  // Realtime card elements
  const rtCard = document.getElementById("realtime-card");
  const rtTs = document.getElementById("rt-timestamp");
  const rtTin = document.getElementById("rt-tin");
  const rtTout = document.getElementById("rt-tout");
  const rtSp = document.getElementById("rt-sp");
  const rtMode = document.getElementById("rt-mode");
  const rtOut = document.getElementById("rt-out");

  let tempChart = null;
  let rtTempChart = null; //new: realtime chart instance

  // Get theme-aware colors for charts
  function getChartColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
      text: isDark ? '#f1f5f9' : '#0f172a',
      grid: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(0, 0, 0, 0.1)',
      muted: isDark ? '#94a3b8' : '#64748b'
    };
  }

  // Update chart colors when theme changes
  function updateChartColors(chart) {
    if (!chart) return;
    const colors = getChartColors();
    
    // Update scales
    if (chart.options.scales.x) {
      chart.options.scales.x.ticks.color = colors.text;
      chart.options.scales.x.grid.color = colors.grid;
    }
    if (chart.options.scales.y) {
      chart.options.scales.y.ticks.color = colors.text;
      chart.options.scales.y.grid.color = colors.grid;
    }
    
    // Update legend
    if (chart.options.plugins.legend) {
      chart.options.plugins.legend.labels = chart.options.plugins.legend.labels || {};
      chart.options.plugins.legend.labels.color = colors.text;
    }
    
    chart.update('none'); // Update without animation
  }

  function createTempChart(ctx) {
    if (!ctx) return null;
    const colors = getChartColors();

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
            labels: {
              color: colors.text
            }
          },
        },
        scales: {
          x: {
            ticks: {
              autoSkip: true,
              maxTicksLimit: 8,
              color: colors.text
            },
            grid: {
              color: colors.grid
            }
          },
          y: {
            beginAtZero: false,
            ticks: {
              color: colors.text
            },
            grid: {
              color: colors.grid
            }
          },
        },
      },
    });
  }
  //History chart instance
  tempChart = createTempChart(tempCtx);

  //Realtime chart instance
   if (rtTempCtx) {
    rtTempChart = createTempChart(rtTempCtx);
  }

  // Listen for theme changes and update charts
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', function() {
      // Small delay to let the theme change take effect
      setTimeout(() => {
        updateChartColors(tempChart);
        updateChartColors(rtTempChart);
      }, 50);
    });
  }

  function formatServerTimeForChart(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.getTime())) return isoString;

  const pad = (n) => (n < 10 ? "0" + n : "" + n);
  
  const yyyy = d.getFullYear();
  const mm = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const mi = pad(d.getMinutes());
  const ss = pad(d.getSeconds());

  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
}


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

    function toLocalIsoWithOffset(dtLocal) {
    // dtLocal is a string from <input type="datetime-local">, e.g. "2025-11-29T20:10"
    if (!dtLocal) return "";

    // This treats it as local time in the browser timezone
    const d = new Date(dtLocal);
    if (Number.isNaN(d.getTime())) {
        return "";
    }

    const pad = (n) => String(n).padStart(2, "0");

    const year = d.getFullYear();
    const month = pad(d.getMonth() + 1);
    const day = pad(d.getDate());
    const hours = pad(d.getHours());
    const minutes = pad(d.getMinutes());
    const seconds = pad(d.getSeconds());

    // getTimezoneOffset returns minutes *behind* UTC (e.g. 480 for UTC-8)
    const offsetMinutes = d.getTimezoneOffset() * -1;
    const sign = offsetMinutes >= 0 ? "+" : "-";
    const absMinutes = Math.abs(offsetMinutes);
    const offsetHours = pad(Math.floor(absMinutes / 60));
    const offsetMins = pad(absMinutes % 60);

    // Example: "2025-11-29T20:10:00-08:00"
    return (
        `${year}-${month}-${day}` +
        `T${hours}:${minutes}:${seconds}` +
        `${sign}${offsetHours}:${offsetMins}`
    );
  }
  


  async function loadTelemetry(useDefaultRange = false) {
    const params = new URLSearchParams();
    params.append("device_id", serial);

    const fromVal = fromInput.value;
    const toVal = toInput.value;

    if (fromVal && toVal) {

      // Convert browser datetime-local into ISO with timezone offset
      const startIso = toLocalIsoWithOffset(fromVal);
      const endIso = toLocalIsoWithOffset(toVal);
      if(startIso && endIso) {
        params.append("start", startIso);
        params.append("end", endIso);
        } 
        
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


    const labels = data.map((s) => formatServerTimeForChart(s.server_ts));
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


    /**
   * Load realtime chart data from /api/telemetry/recent/.
   * - Filters to samples in the last 24 hours relative to browser time.
   * - Updates rtTempChart if available.
   */
async function loadRealtimeChart() {
  if (!rtTempChart) {
    return;
  }

  const params = new URLSearchParams();
  params.append("device_id", serial);
  params.append("limit", "50"); // still cap to 50 newest at the backend

  const url = `/api/telemetry/recent/?${params.toString()}`;

  let resp;
  try {
    resp = await fetch(url, {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
      },
    });
  } catch (err) {
    console.warn("Failed to fetch realtime chart data:", err);
    return;
  }

  if (!resp.ok) {
    console.warn(
      "Realtime chart telemetry request failed with status",
      resp.status
    );
    return;
  }

  const payload = await resp.json();

  const rows =
    (payload && (payload.results || payload.data)) ||
    (Array.isArray(payload) ? payload : []);

  if (!rows.length) {
    // No data at all for this device
    rtTempChart.data.labels = [];
    rtTempChart.data.datasets.forEach((ds) => (ds.data = []));
    rtTempChart.update();
    return;
  }

  // Backend: newest first (order by -server_ts). Reverse to chronological.
  const chronological = rows.slice().reverse();

  // Compute cutoff for the last 24 hours relative to the browser time
  const now = new Date();
  const cutoffMs = now.getTime() - 24 * 60 * 60 * 1000;

  // Keep only points from the last 24 hours
  const data = chronological.filter((s) => {
    const ts = s.server_ts ? new Date(s.server_ts) : null;
    if (!ts || isNaN(ts.getTime())) {
      return false;
    }
    return ts.getTime() >= cutoffMs;
  });

  // If nothing is within the last 24h, show an empty chart, not old data
  if (!data.length) {
    rtTempChart.data.labels = [];
    rtTempChart.data.datasets.forEach((ds) => (ds.data = []));
    rtTempChart.update();
    return;
  }

  const labels = data.map((s) => formatServerTimeForChart(s.server_ts));
  const tin = data.map((s) => s.temp_inside_c);
  const tout = data.map((s) => s.temp_outside_c);
  const sp = data.map((s) => s.setpoint_c);

  rtTempChart.data.labels = labels;
  rtTempChart.data.datasets[0].data = tin;
  rtTempChart.data.datasets[1].data = tout;
  rtTempChart.data.datasets[2].data = sp;
  rtTempChart.update();
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
          : d.toLocaleString(); //Broswer localtime
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

  // ---------- NEW: localize table timestamps to browser timezone ----------

  function formatLocalDateTime(d) {
    if (!(d instanceof Date) || Number.isNaN(d.getTime())) {
      return "";
    }
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function localizeTableTimes() {
    const cells = document.querySelectorAll(".js-localtime");
    cells.forEach((cell) => {
      const iso = cell.dataset.iso;
      if (!iso) {
        return;
      }
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) {
        return; // leave whatever was rendered
      }
      cell.textContent = formatLocalDateTime(d);
    });
  }

  // -----------------------------------------------------------------------

  // Initial loads
  console.log("Device detail script: running initial loads");
  loadTelemetry(true);
  loadRealtime();
  loadRealtimeChart();    // new realtime chart
  localizeTableTimes(); // convert table times to broswer-local

  // Realtime poll every 5 seconds
  setInterval(loadRealtime, 15000);
  setInterval(loadRealtimeChart, 15000); // realtime chart every 15 s

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

  // CSV export - keep it in sync with the date range pickers
  const exportForm = document.getElementById("exportCsvForm");
  if (exportForm) {
    exportForm.addEventListener("submit", function (e) {
      

      // Hidden inputs in the form that will be sent as query parameters
      const csvStartInput = document.getElementById("csvStart");
      const csvEndInput = document.getElementById("csvEnd");
      const csvTzInput = document.getElementById("csvTz");

      const fromVal = fromInput.value;
      const toVal = toInput.value;

      // Same behavior as chart:
      // - Empty: backend uses last 24h
      // - Both set: explicit range in browser local time with offset
      csvStartInput.value = fromVal ? toLocalIsoWithOffset(fromVal) : "";
      csvEndInput.value = toVal ? toLocalIsoWithOffset(toVal) : "";

      // NEW: put browser timezone name into tz param, e.g. "America/Vancouver"
      if (csvTzInput) {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        csvTzInput.value = tz || "";
      }

    });
  }


});
