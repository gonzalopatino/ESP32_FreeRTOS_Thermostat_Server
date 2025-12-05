// static/api/js/device_detail.js
// Modern Chart.js implementation with industry-standard features

document.addEventListener("DOMContentLoaded", function () {
  const root = document.getElementById("device-detail-root");
  if (!root) return;

  const serial = root.dataset.deviceSerial;
  const telemetryUrl = root.dataset.telemetryUrl;

  const fromInput = document.getElementById("fromDate");
  const toInput = document.getElementById("toDate");
  const applyBtn = document.getElementById("applyRangeBtn");

  const tempCtx = document.getElementById("tempChart");
  const rtTempCtx = document.getElementById("rtTempChart");

  // Realtime card elements
  const rtCard = document.getElementById("realtime-card");
  const rtTs = document.getElementById("rt-timestamp");
  const rtTin = document.getElementById("rt-tin");
  const rtTout = document.getElementById("rt-tout");
  const rtSp = document.getElementById("rt-sp");
  const rtMode = document.getElementById("rt-mode");
  const rtOut = document.getElementById("rt-out");

  let tempChart = null;
  let rtTempChart = null;
  
  // Store offline indices for tooltip access
  let tempChartOfflineIndices = new Set();
  let rtChartOfflineIndices = new Set();

  // =========================================================================
  // OFFLINE DETECTION CONFIGURATION
  // =========================================================================
  // Device is considered offline if no data received for this many seconds
  const OFFLINE_THRESHOLD_SECONDS = 120; // 2 minutes - adjust based on your sample rate
  
  // Colors for offline segments
  const offlineColors = {
    line: 'rgb(239, 68, 68)',       // Red
    fill: 'rgba(239, 68, 68, 0.15)',
    point: 'rgb(239, 68, 68)',
  };

  // =========================================================================
  // MODERN COLOR PALETTE
  // =========================================================================
  const chartPalette = {
    inside: {
      line: 'rgb(59, 130, 246)',      // Blue
      fill: 'rgba(59, 130, 246, 0.12)',
      point: 'rgb(59, 130, 246)',
    },
    outside: {
      line: 'rgb(16, 185, 129)',      // Emerald/Green  
      fill: 'rgba(16, 185, 129, 0.08)',
      point: 'rgb(16, 185, 129)',
    },
    setpoint: {
      line: 'rgb(249, 115, 22)',      // Orange
      fill: 'rgba(249, 115, 22, 0.05)',
      point: 'rgb(249, 115, 22)',
    }
  };

  // =========================================================================
  // THEME-AWARE COLORS
  // =========================================================================
  function getChartColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    return {
      text: isDark ? '#e2e8f0' : '#1e293b',
      textMuted: isDark ? '#94a3b8' : '#64748b',
      grid: isDark ? 'rgba(148, 163, 184, 0.1)' : 'rgba(15, 23, 42, 0.06)',
      border: isDark ? 'rgba(148, 163, 184, 0.2)' : 'rgba(15, 23, 42, 0.1)',
      tooltipBg: isDark ? 'rgba(30, 41, 59, 0.96)' : 'rgba(255, 255, 255, 0.96)',
      tooltipBorder: isDark ? 'rgba(71, 85, 105, 0.5)' : 'rgba(203, 213, 225, 0.8)',
      crosshair: isDark ? 'rgba(148, 163, 184, 0.4)' : 'rgba(100, 116, 139, 0.3)',
    };
  }

  // =========================================================================
  // CUSTOM CROSSHAIR PLUGIN
  // =========================================================================
  const crosshairPlugin = {
    id: 'crosshair',
    afterDraw: (chart) => {
      const tooltip = chart.tooltip;
      if (tooltip && tooltip._active && tooltip._active.length) {
        const activePoint = tooltip._active[0];
        const ctx = chart.ctx;
        const x = activePoint.element.x;
        const topY = chart.scales.y.top;
        const bottomY = chart.scales.y.bottom;
        const colors = getChartColors();

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(x, topY);
        ctx.lineTo(x, bottomY);
        ctx.lineWidth = 1;
        ctx.strokeStyle = colors.crosshair;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.restore();
      }
    }
  };

  // Register the crosshair plugin
  Chart.register(crosshairPlugin);

  // =========================================================================
  // TOOLTIP CONFIGURATION
  // =========================================================================
  function createTooltipConfig(getOfflineIndices = null) {
    const colors = getChartColors();
    
    return {
      enabled: true,
      mode: 'index',
      intersect: false,
      backgroundColor: colors.tooltipBg,
      titleColor: colors.text,
      bodyColor: colors.text,
      borderColor: colors.tooltipBorder,
      borderWidth: 1,
      cornerRadius: 10,
      padding: 14,
      displayColors: true,
      titleFont: {
        size: 13,
        weight: '600',
        family: "'Inter', 'Segoe UI', system-ui, sans-serif"
      },
      bodyFont: {
        size: 12,
        family: "'Inter', 'Segoe UI', system-ui, sans-serif"
      },
      bodySpacing: 8,
      boxPadding: 6,
      usePointStyle: true,
      callbacks: {
        title: function(tooltipItems) {
          if (!tooltipItems.length) return '';
          const label = tooltipItems[0].label;
          const date = new Date(label);
          if (isNaN(date.getTime())) return label;
          return date.toLocaleString(undefined, {
            weekday: 'short',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
          });
        },
        afterTitle: function(tooltipItems) {
          if (!tooltipItems.length || !getOfflineIndices) return '';
          const offlineIndices = getOfflineIndices();
          const idx = tooltipItems[0].dataIndex;
          // Check if this point is at the start or end of an offline gap
          if (offlineIndices.has(idx) || offlineIndices.has(idx - 1)) {
            return '⚠️ Device was offline';
          }
          return '';
        },
        label: function(context) {
          const label = context.dataset.label || '';
          const value = context.parsed.y;
          if (value === null || value === undefined) return null;
          return ` ${label}: ${value.toFixed(1)}°C`;
        },
        labelPointStyle: function() {
          return { pointStyle: 'circle', rotation: 0 };
        }
      }
    };
  }

  // =========================================================================
  // MODERN CHART FACTORY
  // =========================================================================
  function createTempChart(ctx, options = {}) {
    if (!ctx) return null;
    
    const colors = getChartColors();
    const isRealtime = options.realtime || false;
    
    // Get the appropriate offline indices getter based on chart type
    const getOfflineIndices = isRealtime 
      ? () => rtChartOfflineIndices 
      : () => tempChartOfflineIndices;

    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Inside Temp',
            data: [],
            borderColor: chartPalette.inside.line,
            backgroundColor: chartPalette.inside.fill,
            pointBackgroundColor: chartPalette.inside.point,
            pointBorderColor: 'transparent',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: chartPalette.inside.line,
            pointHoverBorderWidth: 3,
            borderWidth: 2.5,
            pointRadius: isRealtime ? 0 : 2,
            pointHoverRadius: 6,
            tension: 0.4,
            fill: true,
            order: 3,
            segment: {}, // Will be populated with offline styling
          },
          {
            label: 'Outside Temp',
            data: [],
            borderColor: chartPalette.outside.line,
            backgroundColor: chartPalette.outside.fill,
            pointBackgroundColor: chartPalette.outside.point,
            pointBorderColor: 'transparent',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: chartPalette.outside.line,
            pointHoverBorderWidth: 3,
            borderWidth: 2.5,
            pointRadius: isRealtime ? 0 : 2,
            pointHoverRadius: 6,
            tension: 0.4,
            fill: true,
            order: 2,
            segment: {}, // Will be populated with offline styling
          },
          {
            label: 'Setpoint',
            data: [],
            borderColor: chartPalette.setpoint.line,
            backgroundColor: 'transparent',
            pointBackgroundColor: chartPalette.setpoint.point,
            pointBorderColor: 'transparent',
            pointHoverBackgroundColor: '#fff',
            pointHoverBorderColor: chartPalette.setpoint.line,
            pointHoverBorderWidth: 3,
            borderWidth: 2,
            borderDash: [8, 4],
            pointRadius: 0,
            pointHoverRadius: 5,
            tension: 0,
            fill: false,
            order: 1,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        
        // Smooth animations
        animation: {
          duration: 800,
          easing: 'easeOutQuart',
        },
        transitions: {
          active: {
            animation: {
              duration: 200
            }
          }
        },
        
        // Interaction settings
        interaction: {
          mode: 'index',
          intersect: false,
          axis: 'x',
        },
        
        // Hover effects
        hover: {
          mode: 'index',
          intersect: false,
        },

        // Layout padding
        layout: {
          padding: {
            top: 8,
            right: 16,
            bottom: 4,
            left: 8,
          }
        },

        // Plugins configuration
        plugins: {
          legend: {
            display: true,
            position: 'top',
            align: 'end',
            labels: {
              color: colors.text,
              usePointStyle: true,
              pointStyle: 'circle',
              padding: 20,
              font: {
                size: 12,
                weight: '500',
                family: "'Inter', 'Segoe UI', system-ui, sans-serif"
              },
              boxWidth: 8,
              boxHeight: 8,
            }
          },
          tooltip: createTooltipConfig(getOfflineIndices),
        },

        // Scales configuration
        scales: {
          x: {
            type: 'category',
            display: true,
            grid: {
              display: true,
              color: colors.grid,
              drawBorder: false,
              lineWidth: 1,
            },
            border: {
              display: false,
            },
            ticks: {
              color: colors.textMuted,
              font: {
                size: 11,
                family: "'Inter', 'Segoe UI', system-ui, sans-serif"
              },
              maxRotation: 45,
              minRotation: 0,
              autoSkip: true,
              maxTicksLimit: isRealtime ? 6 : 10,
              padding: 8,
              callback: function(value, index, ticks) {
                const label = this.getLabelForValue(value);
                if (!label) return '';
                const date = new Date(label);
                if (isNaN(date.getTime())) return label;
                
                if (isRealtime) {
                  return date.toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit'
                  });
                }
                return date.toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit'
                });
              }
            },
          },
          y: {
            display: true,
            beginAtZero: false,
            grid: {
              display: true,
              color: colors.grid,
              drawBorder: false,
              lineWidth: 1,
            },
            border: {
              display: false,
            },
            ticks: {
              color: colors.textMuted,
              font: {
                size: 11,
                weight: '500',
                family: "'Inter', 'Segoe UI', system-ui, sans-serif"
              },
              padding: 12,
              callback: function(value) {
                return value.toFixed(1) + '°';
              }
            },
            title: {
              display: true,
              text: 'Temperature (°C)',
              color: colors.textMuted,
              font: {
                size: 11,
                weight: '500',
                family: "'Inter', 'Segoe UI', system-ui, sans-serif"
              },
              padding: { bottom: 8 }
            }
          },
        },

        // Element defaults
        elements: {
          line: {
            capBezierPoints: true,
          },
          point: {
            hitRadius: 10,
          }
        }
      }
    });
  }

  // Create chart instances
  tempChart = createTempChart(tempCtx, { realtime: false });
  if (rtTempCtx) {
    rtTempChart = createTempChart(rtTempCtx, { realtime: true });
  }

  // =========================================================================
  // THEME CHANGE HANDLER
  // =========================================================================
  function updateChartTheme(chart) {
    if (!chart) return;
    const colors = getChartColors();

    // Update scales
    chart.options.scales.x.ticks.color = colors.textMuted;
    chart.options.scales.x.grid.color = colors.grid;
    chart.options.scales.y.ticks.color = colors.textMuted;
    chart.options.scales.y.grid.color = colors.grid;
    chart.options.scales.y.title.color = colors.textMuted;

    // Update legend
    chart.options.plugins.legend.labels.color = colors.text;

    // Update tooltip
    chart.options.plugins.tooltip.backgroundColor = colors.tooltipBg;
    chart.options.plugins.tooltip.titleColor = colors.text;
    chart.options.plugins.tooltip.bodyColor = colors.text;
    chart.options.plugins.tooltip.borderColor = colors.tooltipBorder;

    chart.update('none');
  }

  // Listen for theme changes
  const themeToggle = document.getElementById('themeToggle');
  if (themeToggle) {
    themeToggle.addEventListener('click', function() {
      setTimeout(() => {
        updateChartTheme(tempChart);
        updateChartTheme(rtTempChart);
      }, 50);
    });
  }

  // Observe data-theme attribute changes
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.attributeName === 'data-theme') {
        updateChartTheme(tempChart);
        updateChartTheme(rtTempChart);
      }
    });
  });
  observer.observe(document.documentElement, { attributes: true });

  // =========================================================================
  // UTILITY FUNCTIONS
  // =========================================================================
  
  function formatServerTimeForChart(isoString) {
    if (!isoString) return "";
    const d = new Date(isoString);
    if (Number.isNaN(d.getTime())) return isoString;
    return d.toISOString();
  }

  function toLocalIsoWithOffset(dtLocal) {
    if (!dtLocal) return "";
    const d = new Date(dtLocal);
    if (Number.isNaN(d.getTime())) return "";

    const pad = (n) => String(n).padStart(2, "0");
    const year = d.getFullYear();
    const month = pad(d.getMonth() + 1);
    const day = pad(d.getDate());
    const hours = pad(d.getHours());
    const minutes = pad(d.getMinutes());
    const seconds = pad(d.getSeconds());

    const offsetMinutes = d.getTimezoneOffset() * -1;
    const sign = offsetMinutes >= 0 ? "+" : "-";
    const absMinutes = Math.abs(offsetMinutes);
    const offsetHours = pad(Math.floor(absMinutes / 60));
    const offsetMins = pad(absMinutes % 60);

    return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}${sign}${offsetHours}:${offsetMins}`;
  }

  // =========================================================================
  // OFFLINE DETECTION - Detect gaps in telemetry data
  // =========================================================================
  
  /**
   * Analyzes timestamps and returns a Set of indices where offline gaps occur.
   * A gap is detected when the time between consecutive samples exceeds the threshold.
   * @param {string[]} labels - Array of ISO timestamp strings
   * @returns {Set<number>} - Set of indices that START an offline period
   */
  function detectOfflineSegments(labels) {
    const offlineIndices = new Set();
    
    if (labels.length < 2) {
      console.log('detectOfflineSegments: Not enough labels (<2)');
      return offlineIndices;
    }
    
    console.log(`detectOfflineSegments: Analyzing ${labels.length} timestamps, threshold=${OFFLINE_THRESHOLD_SECONDS}s`);
    console.log(`First timestamp: ${labels[0]}, Last: ${labels[labels.length-1]}`);
    
    for (let i = 1; i < labels.length; i++) {
      const prevTime = new Date(labels[i - 1]).getTime();
      const currTime = new Date(labels[i]).getTime();
      
      if (isNaN(prevTime) || isNaN(currTime)) {
        console.warn(`Invalid timestamp at index ${i}: prev="${labels[i-1]}", curr="${labels[i]}"`);
        continue;
      }
      
      const gapSeconds = (currTime - prevTime) / 1000;
      
      // If gap exceeds threshold, mark this segment as offline
      if (gapSeconds > OFFLINE_THRESHOLD_SECONDS) {
        offlineIndices.add(i - 1); // The segment FROM index i-1 TO i is offline
        console.log(`Offline gap detected: ${gapSeconds.toFixed(0)}s between index ${i-1} and ${i}`);
        console.log(`  From: ${labels[i-1]} To: ${labels[i]}`);
      }
    }
    
    console.log(`detectOfflineSegments: Found ${offlineIndices.size} offline period(s)`);
    return offlineIndices;
  }

  /**
   * Creates a segment style function for Chart.js that colors offline segments red
   * @param {Set<number>} offlineIndices - Set of indices where offline periods start
   * @param {string} normalColor - Normal line color
   * @returns {function} - Segment style function for Chart.js
   */
  function createSegmentStyle(offlineIndices, normalColor) {
    // Capture the Set by value at the time of function creation
    const indices = new Set(offlineIndices);
    console.log(`createSegmentStyle called with ${indices.size} offline indices`);
    
    return function(ctx) {
      // ctx.p0DataIndex is the index of the starting point of the segment
      const idx = ctx.p0DataIndex;
      if (indices.has(idx)) {
        return offlineColors.line;
      }
      return undefined; // Use default color
    };
  }

  /**
   * Creates segment background color function
   */
  function createSegmentBgStyle(offlineIndices, normalColor) {
    // Capture the Set by value at the time of function creation
    const indices = new Set(offlineIndices);
    console.log(`createSegmentBgStyle called with ${indices.size} offline indices`);
    
    return function(ctx) {
      const idx = ctx.p0DataIndex;
      if (indices.has(idx)) {
        return offlineColors.fill;
      }
      return undefined; // Use default
    };
  }

  /**
   * Creates point background color array based on offline status
   * @param {string[]} labels - Array of ISO timestamp strings
   * @param {Set<number>} offlineIndices - Set of indices where offline periods start
   * @param {string} normalColor - Normal point color
   * @returns {string[]} - Array of colors for each point
   */
  function createPointColors(labels, offlineIndices, normalColor) {
    const colors = [];
    for (let i = 0; i < labels.length; i++) {
      // Point is "offline" if it's at the end of an offline gap
      // or at the start of an offline gap
      if (offlineIndices.has(i) || offlineIndices.has(i - 1)) {
        colors.push(offlineColors.point);
      } else {
        colors.push(normalColor);
      }
    }
    return colors;
  }

  // =========================================================================
  // DATA LOADING - HISTORY CHART
  // =========================================================================
  async function loadTelemetry(useDefaultRange = false) {
    const params = new URLSearchParams();
    params.append("device_id", serial);

    const fromVal = fromInput.value;
    const toVal = toInput.value;

    if (fromVal && toVal) {
      const startIso = toLocalIsoWithOffset(fromVal);
      const endIso = toLocalIsoWithOffset(toVal);
      if (startIso && endIso) {
        params.append("start", startIso);
        params.append("end", endIso);
      }
    } else if (useDefaultRange) {
      params.append("range", "24h");
    }

    const url = params.toString().length > 0
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

    // Sort oldest → newest
    const data = rows.slice().sort((a, b) => {
      const ta = a.server_ts || a.device_ts || "";
      const tb = b.server_ts || b.device_ts || "";
      return ta.localeCompare(tb);
    });

    const labels = data.map((s) => formatServerTimeForChart(s.server_ts));
    const tin = data.map((s) => s.temp_inside_c);
    const tout = data.map((s) => s.temp_outside_c);
    const sp = data.map((s) => s.setpoint_c);

    // Detect offline segments and store for tooltip access
    tempChartOfflineIndices = detectOfflineSegments(labels);
    
    if (tempChart) {
      tempChart.data.labels = labels;
      tempChart.data.datasets[0].data = tin;
      tempChart.data.datasets[1].data = tout;
      tempChart.data.datasets[2].data = sp;
      
      // Apply segment styling for offline detection
      tempChart.data.datasets[0].segment = {
        borderColor: createSegmentStyle(tempChartOfflineIndices, chartPalette.inside.line),
        backgroundColor: createSegmentBgStyle(tempChartOfflineIndices, chartPalette.inside.fill),
      };
      tempChart.data.datasets[0].pointBackgroundColor = createPointColors(labels, tempChartOfflineIndices, chartPalette.inside.point);
      
      tempChart.data.datasets[1].segment = {
        borderColor: createSegmentStyle(tempChartOfflineIndices, chartPalette.outside.line),
        backgroundColor: createSegmentBgStyle(tempChartOfflineIndices, chartPalette.outside.fill),
      };
      tempChart.data.datasets[1].pointBackgroundColor = createPointColors(labels, tempChartOfflineIndices, chartPalette.outside.point);
      
      // Setpoint doesn't need offline coloring as it's a configuration, not a measurement
      
      tempChart.update('default');
      
      // Update offline indicator badge and legend hint
      const historyOfflineIndicator = document.getElementById('historyOfflineIndicator');
      const historyLegendHint = document.getElementById('historyChartLegendHint');
      
      if (tempChartOfflineIndices.size > 0) {
        if (historyOfflineIndicator) {
          historyOfflineIndicator.classList.remove('d-none');
          historyOfflineIndicator.innerHTML = `<i class="bi bi-wifi-off me-1"></i>${tempChartOfflineIndices.size} offline period${tempChartOfflineIndices.size > 1 ? 's' : ''}`;
        }
        if (historyLegendHint) {
          historyLegendHint.classList.remove('d-none');
        }
        console.log(`History chart: Detected ${tempChartOfflineIndices.size} offline period(s)`);
      } else {
        if (historyOfflineIndicator) historyOfflineIndicator.classList.add('d-none');
        if (historyLegendHint) historyLegendHint.classList.add('d-none');
      }
    }

    const countSpan = document.getElementById("samplesCount");
    if (countSpan) {
      countSpan.textContent = payload.count ?? data.length;
    }
  }

  // =========================================================================
  // DATA LOADING - REALTIME CHART
  // =========================================================================
  async function loadRealtimeChart() {
    if (!rtTempChart) return;

    const params = new URLSearchParams();
    params.append("device_id", serial);
    params.append("limit", "100");

    const url = `/api/telemetry/recent/?${params.toString()}`;

    let resp;
    try {
      resp = await fetch(url, {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
    } catch (err) {
      console.warn("Failed to fetch realtime chart data:", err);
      return;
    }

    if (!resp.ok) {
      console.warn("Realtime chart request failed with status", resp.status);
      return;
    }

    const payload = await resp.json();
    const rows = (payload && (payload.results || payload.data)) || 
                 (Array.isArray(payload) ? payload : []);

    if (!rows.length) {
      rtTempChart.data.labels = [];
      rtTempChart.data.datasets.forEach((ds) => (ds.data = []));
      rtTempChart.update('none');
      return;
    }

    // Backend: newest first → reverse to chronological
    const chronological = rows.slice().reverse();

    // Filter to last 24 hours
    const now = new Date();
    const cutoffMs = now.getTime() - 24 * 60 * 60 * 1000;

    const data = chronological.filter((s) => {
      const ts = s.server_ts ? new Date(s.server_ts) : null;
      if (!ts || isNaN(ts.getTime())) return false;
      return ts.getTime() >= cutoffMs;
    });

    if (!data.length) {
      rtTempChart.data.labels = [];
      rtTempChart.data.datasets.forEach((ds) => (ds.data = []));
      rtChartOfflineIndices = new Set();
      rtTempChart.update('none');
      return;
    }

    const labels = data.map((s) => formatServerTimeForChart(s.server_ts));
    const tin = data.map((s) => s.temp_inside_c);
    const tout = data.map((s) => s.temp_outside_c);
    const sp = data.map((s) => s.setpoint_c);

    // Detect offline segments and store for tooltip access
    rtChartOfflineIndices = detectOfflineSegments(labels);

    rtTempChart.data.labels = labels;
    rtTempChart.data.datasets[0].data = tin;
    rtTempChart.data.datasets[1].data = tout;
    rtTempChart.data.datasets[2].data = sp;
    
    // Apply segment styling for offline detection
    rtTempChart.data.datasets[0].segment = {
      borderColor: createSegmentStyle(rtChartOfflineIndices, chartPalette.inside.line),
      backgroundColor: createSegmentBgStyle(rtChartOfflineIndices, chartPalette.inside.fill),
    };
    rtTempChart.data.datasets[0].pointBackgroundColor = createPointColors(labels, rtChartOfflineIndices, chartPalette.inside.point);
    
    rtTempChart.data.datasets[1].segment = {
      borderColor: createSegmentStyle(rtChartOfflineIndices, chartPalette.outside.line),
      backgroundColor: createSegmentBgStyle(rtChartOfflineIndices, chartPalette.outside.fill),
    };
    rtTempChart.data.datasets[1].pointBackgroundColor = createPointColors(labels, rtChartOfflineIndices, chartPalette.outside.point);
    
    rtTempChart.update('default');
    
    // Update offline indicator badge and legend hint
    const rtOfflineIndicator = document.getElementById('rtOfflineIndicator');
    const rtLegendHint = document.getElementById('rtChartLegendHint');
    
    if (rtChartOfflineIndices.size > 0) {
      if (rtOfflineIndicator) {
        rtOfflineIndicator.classList.remove('d-none');
        rtOfflineIndicator.innerHTML = `<i class="bi bi-wifi-off me-1"></i>${rtChartOfflineIndices.size} offline period${rtChartOfflineIndices.size > 1 ? 's' : ''}`;
      }
      if (rtLegendHint) {
        rtLegendHint.classList.remove('d-none');
      }
      console.log(`Realtime chart: Detected ${rtChartOfflineIndices.size} offline period(s)`);
    } else {
      if (rtOfflineIndicator) rtOfflineIndicator.classList.add('d-none');
      if (rtLegendHint) rtLegendHint.classList.add('d-none');
    }
  }

  // =========================================================================
  // REALTIME CARD UPDATE
  // =========================================================================
  async function loadRealtime() {
    if (!rtCard) return;

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
    if (!rows.length) return;

    const s = rows[0];
    const ts = s.server_ts || s.device_ts || "";

    if (rtTs) {
      if (ts) {
        const d = new Date(ts);
        const tsText = Number.isNaN(d.getTime()) ? ts : d.toLocaleString();
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

  // =========================================================================
  // TABLE TIMESTAMP LOCALIZATION
  // =========================================================================
  function formatLocalDateTime(d) {
    if (!(d instanceof Date) || Number.isNaN(d.getTime())) return "";
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
      if (!iso) return;
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return;
      cell.textContent = formatLocalDateTime(d);
    });
  }

  // =========================================================================
  // INITIALIZATION
  // =========================================================================
  console.log("Device detail script: running initial loads");
  loadTelemetry(true);
  loadRealtime();
  loadRealtimeChart();
  localizeTableTimes();

  // Polling intervals
  setInterval(loadRealtime, 15000);
  setInterval(loadRealtimeChart, 15000);

  // Apply button handler
  if (applyBtn) {
    applyBtn.addEventListener("click", function () {
      const fromVal = fromInput.value;
      const toVal = toInput.value;

      if (!fromVal && !toVal) {
        loadTelemetry(true);
        return;
      }

      if (!fromVal || !toVal) {
        alert("Please set both From and To, or leave both empty to show the last 24 hours.");
        return;
      }

      loadTelemetry(false);
    });
  }

  // CSV export handler
  const exportForm = document.getElementById("exportCsvForm");
  if (exportForm) {
    exportForm.addEventListener("submit", function (e) {
      const csvStartInput = document.getElementById("csvStart");
      const csvEndInput = document.getElementById("csvEnd");
      const csvTzInput = document.getElementById("csvTz");

      const fromVal = fromInput.value;
      const toVal = toInput.value;

      csvStartInput.value = fromVal ? toLocalIsoWithOffset(fromVal) : "";
      csvEndInput.value = toVal ? toLocalIsoWithOffset(toVal) : "";

      if (csvTzInput) {
        const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        csvTzInput.value = tz || "";
      }
    });
  }
});
