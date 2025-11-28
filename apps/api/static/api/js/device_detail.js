(function () {
  // -------------- Metric configuration --------------

  // Each metric config describes:
  // - which canvas to bind to
  // - how to label the Y axis
  // - which fields from telemetry to plot
  const METRIC_CONFIGS = {
    temperature: {
      canvasId: "metric-temperature",
      yLabel: "Temperature (°C)",
      datasets: [
        { label: "Tin (°C)", field: "temp_inside_c" },
        { label: "Setpoint (°C)", field: "setpoint_c" },
        { label: "Tout (°C)", field: "temp_outside_c" }
      ]
    }
    // Later you can add:
    // humidity: {
    //   canvasId: "metric-humidity",
    //   yLabel: "Humidity (%)",
    //   datasets: [
    //     { label: "Humidity (%)", field: "humidity_percent" }
    //   ]
    // }
  };

  // -------------- Find device serial --------------

  // Find the first existing metric canvas and read its device serial.
  // All metrics for this page share the same device.
  let deviceSerial = null;
  for (const metricName in METRIC_CONFIGS) {
    if (!Object.prototype.hasOwnProperty.call(METRIC_CONFIGS, metricName)) continue;
    const cfg = METRIC_CONFIGS[metricName];
    const canvas = document.getElementById(cfg.canvasId);
    if (canvas && canvas.dataset.deviceSerial) {
      deviceSerial = canvas.dataset.deviceSerial;
      break;
    }
  }

  if (!deviceSerial) {
    // No metric canvas on this page, nothing to do.
    return;
  }

  const apiUrl = `/api/telemetry/recent/?device_id=${encodeURIComponent(
    deviceSerial
  )}&limit=50`;

  // -------------- Initialize charts --------------

  // Full timestamps for tooltip titles
  let telemetryTimestamps = [];
  // Keep charts keyed by metric name
  const charts = {};

  function createChartForMetric(metricName, cfg) {
    const canvas = document.getElementById(cfg.canvasId);
    if (!canvas) {
      return null;
    }

    const ctx = canvas.getContext("2d");

    const chartConfig = {
      type: "line",
      data: {
        labels: [],
        datasets: cfg.datasets.map((ds) => ({
          label: ds.label,
          data: [],
          tension: 0.2
        }))
      },
      options: {
        responsive: false,
        plugins: {
          tooltip: {
            callbacks: {
              // Tooltip title: full server_ts with date
              title: function (items) {
                if (!items.length) {
                  return "";
                }
                const idx = items[0].dataIndex;
                return telemetryTimestamps[idx] || "";
              }
            }
          }
        },
        scales: {
          x: {
            title: {
              display: true,
              text: "Time"
            },
            ticks: {
              maxTicksLimit: 6
            }
          },
          y: {
            title: {
              display: true,
              text: cfg.yLabel
            }
          }
        }
      }
    };

    return new Chart(ctx, chartConfig);
  }

  function initCharts() {
    for (const metricName in METRIC_CONFIGS) {
      if (!Object.prototype.hasOwnProperty.call(METRIC_CONFIGS, metricName)) continue;
      const cfg = METRIC_CONFIGS[metricName];
      const chart = createChartForMetric(metricName, cfg);
      if (chart) {
        charts[metricName] = chart;
      }
    }
  }

  // -------------- Telemetry fetch + update --------------

  function updateTelemetry() {
    fetch(apiUrl)
      .then((response) => {
        if (!response.ok) {
          throw new Error("Network response was not ok");
        }
        return response.json();
      })
      .then((payload) => {
        // payload is { count, device_id, data: [...] }
        const data = payload.data || [];

        // sort by server_ts ascending for chart readability
        data.sort((a, b) => (a.server_ts > b.server_ts ? 1 : -1));

        const labels = [];
        telemetryTimestamps = [];

        const tbody = document.getElementById("telemetry-table-body");
        if (!tbody) {
          return;
        }
        tbody.innerHTML = "";

        data.forEach((item) => {
          const iso = item.server_ts;
          let label = "";
          if (iso) {
            const d = new Date(iso);
            // Axis label: "HH:MM" 24h, no seconds
            label = d.toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
              hour12: false
            });
          }
          labels.push(label);
          telemetryTimestamps.push(item.server_ts || "");

          // Rebuild table row
          const row = document.createElement("tr");

          function cell(text) {
            const td = document.createElement("td");
            td.textContent = text;
            return td;
          }

          row.appendChild(cell(item.server_ts || ""));
          row.appendChild(cell(item.device_ts || "-"));
          row.appendChild(cell(item.mode || ""));
          row.appendChild(cell(item.temp_inside_c));
          row.appendChild(
            cell(
              item.temp_outside_c !== null && item.temp_outside_c !== undefined
                ? item.temp_outside_c
                : "-"
            )
          );
          row.appendChild(cell(item.setpoint_c));
          row.appendChild(
            cell(
              item.hysteresis_c !== null && item.hysteresis_c !== undefined
                ? item.hysteresis_c
                : "-"
            )
          );
          row.appendChild(
            cell(
              item.humidity_percent !== null &&
              item.humidity_percent !== undefined
                ? item.humidity_percent
                : "-"
            )
          );
          row.appendChild(cell(item.output || "-"));

          tbody.appendChild(row);
        });

        // Update all metric charts based on the same telemetry
        for (const metricName in METRIC_CONFIGS) {
          if (!Object.prototype.hasOwnProperty.call(METRIC_CONFIGS, metricName)) continue;
          const cfg = METRIC_CONFIGS[metricName];
          const chart = charts[metricName];
          if (!chart) {
            continue;
          }

          // Prepare one array per dataset
          const datasetValues = cfg.datasets.map(() => []);

          data.forEach((item) => {
            cfg.datasets.forEach((ds, idx) => {
              const value = item[ds.field];
              datasetValues[idx].push(value);
            });
          });

          chart.data.labels = labels;
          cfg.datasets.forEach((ds, idx) => {
            chart.data.datasets[idx].data = datasetValues[idx];
          });
          chart.update();
        }
      })
      .catch((error) => {
        console.error("Error fetching telemetry:", error);
      });
  }

  // -------------- Init + poll --------------

  initCharts();
  updateTelemetry();
  setInterval(updateTelemetry, 5000);
})();
