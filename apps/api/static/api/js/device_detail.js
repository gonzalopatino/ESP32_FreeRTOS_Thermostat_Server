(function () {
  const canvas = document.getElementById("telemetryChart");
  if (!canvas) {
    return;
  }

  const deviceSerial = canvas.dataset.deviceSerial;
  if (!deviceSerial) {
    console.error("No device serial found on telemetryChart element.");
    return;
  }

  const apiUrl = `/api/telemetry/recent/?device_id=${encodeURIComponent(
    deviceSerial
  )}&limit=50`;

  const ctx = canvas.getContext("2d");

  const chartConfig = {
    type: "line",
    data: {
      labels: [],
      datasets: [
        {
          label: "Tin (°C)",
          data: [],
          tension: 0.2
        },
        {
          label: "Setpoint (°C)",
          data: [],
          tension: 0.2
        }
      ]
    },
    options: {
      responsive: false,
      scales: {
        x: {
          title: {
            display: true,
            text: "Time"
          }
        },
        y: {
          title: {
            display: true,
            text: "Temperature (°C)"
          }
        }
      }
    }
  };

  const telemetryChart = new Chart(ctx, chartConfig);

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
        const tin = [];
        const setpoint = [];

        const tbody = document.getElementById("telemetry-table-body");
        if (!tbody) {
          return;
        }
        tbody.innerHTML = "";

        data.forEach((item) => {
          const ts = item.server_ts || "";
          labels.push(ts);
          tin.push(item.temp_inside_c);
          setpoint.push(item.setpoint_c);

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

        telemetryChart.data.labels = labels;
        telemetryChart.data.datasets[0].data = tin;
        telemetryChart.data.datasets[1].data = setpoint;
        telemetryChart.update();
      })
      .catch((error) => {
        console.error("Error fetching telemetry:", error);
      });
  }

  // Initial load
  updateTelemetry();
  // Poll every 5 seconds
  setInterval(updateTelemetry, 5000);
})();
