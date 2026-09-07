/* Generic D3 line-chart engine — a vanilla-JS/D3 stand-in for the Recharts
 * <LineChart>/<Brush>/<Tooltip>/<Legend> combo the React charts used.
 * Config-driven so ROP / Depth-Time / Multi-Parameter charts share one engine. */
(function () {
  "use strict";

  function downloadCSV(data, filename, columns) {
    if (!data || data.length === 0) return;
    var cols = columns || Object.keys(data[0]);
    var header = cols.join(",");
    var rows = data.map(function (row) {
      return cols
        .map(function (col) {
          var value = row[col];
          if (value === null || value === undefined) return "";
          if (typeof value === "string" && (value.indexOf(",") !== -1 || value.indexOf('"') !== -1)) {
            return '"' + value.replace(/"/g, '""') + '"';
          }
          return value;
        })
        .join(",");
    });
    var csv = [header].concat(rows).join("\n");
    var blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    var link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = filename + ".csv";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function evenTicks(n, count) {
    if (n <= 1) return [0];
    var step = Math.floor((n - 1) / (count - 1)) || 1;
    var out = [];
    for (var i = 0; i < count; i++) {
      out.push(Math.min(i * step, n - 1));
    }
    return out;
  }

  function formatDateTick(raw) {
    var d = new Date(raw);
    if (isNaN(d.getTime())) return String(raw);
    var day = String(d.getDate()).padStart(2, "0");
    var month = String(d.getMonth() + 1).padStart(2, "0");
    var year = String(d.getFullYear()).slice(-2);
    return day + "/" + month + "/" + year;
  }

  function renderLineChart(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var fullData = (config.data || []).filter(function (d) {
      return d[config.xKey] !== null && d[config.xKey] !== undefined;
    });
    if (fullData.length === 0) return;

    var yAxesCfg = config.yAxes || [{ id: "default", color: "var(--color-chart-axis)", orientation: "left" }];
    var leftAxisCount = yAxesCfg.filter(function (a) { return a.orientation !== "right"; }).length;
    var rightAxisCount = yAxesCfg.filter(function (a) { return a.orientation === "right"; }).length;
    var axisGap = 52;
    var margin = {
      top: 24,
      right: 32 + Math.max(1, rightAxisCount) * axisGap,
      bottom: config.brush !== false ? 78 : 50,
      left: 24 + Math.max(1, leftAxisCount) * axisGap,
    };
    var totalHeight = config.height || 460;
    var width = Math.max(container.clientWidth || 800, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;
    var brushHeight = 24;

    container.innerHTML = "";
    var svg = d3
      .select(container)
      .append("svg")
      .attr("width", "100%")
      .attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);

    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    var axisColor = "var(--color-chart-axis)";
    var gridColor = "var(--color-border)";

    var isPointScale = config.xType === "point";
    var xIndex = d3.range(fullData.length);

    function makeXScale(domainSlice) {
      if (isPointScale) {
        return d3.scalePoint().domain(domainSlice).range([0, width]);
      }
      var extent = d3.extent(domainSlice, function (d) {
        return fullData[d][config.xKey];
      });
      return d3.scaleLinear().domain(extent).range([0, width]);
    }

    var xScale = makeXScale(xIndex);

    var yAxes = yAxesCfg;
    var yScales = {};
    yAxes.forEach(function (ax) {
      var seriesForAxis = (config.series || []).filter(function (s) { return (s.yAxisId || "default") === ax.id; });
      var keys = seriesForAxis.map(function (s) { return s.key; });
      // Band keys (bandLoKey/bandHiKey) count toward the axis extent too — a
      // shaded uncertainty band that pokes past the domain the plain line
      // would need gets silently clipped otherwise.
      seriesForAxis.forEach(function (s) {
        if (s.bandLoKey) keys.push(s.bandLoKey);
        if (s.bandHiKey) keys.push(s.bandHiKey);
      });
      var values = [];
      fullData.forEach(function (d) {
        keys.forEach(function (k) {
          if (d[k] !== null && d[k] !== undefined && isFinite(d[k])) values.push(d[k]);
        });
      });
      var extent = values.length ? d3.extent(values) : [0, 1];
      if (extent[0] === extent[1]) { extent[0] -= 1; extent[1] += 1; }
      var range = config.reverseY ? [0, height] : [height, 0];
      yScales[ax.id] = d3.scaleLinear().domain(extent).nice().range(range);
    });

    var gridArea = g.append("g").attr("class", "chart-grid");
    var plotArea = g.append("g").attr("class", "chart-plot");
    var xAxisG = g.append("g").attr("class", "chart-axis-x");
    var leftAxes = [];
    var rightAxes = [];

    yAxes.forEach(function (ax, i) {
      if (ax.orientation === "right") rightAxes.push(ax);
      else leftAxes.push(ax);
    });

    var leftAxisGs = leftAxes.map(function (ax, i) {
      return g.append("g").attr("class", "chart-axis-y").attr("transform", "translate(" + (-i * 46) + ",0)");
    });
    var rightAxisGs = rightAxes.map(function (ax, i) {
      return g.append("g").attr("class", "chart-axis-y").attr("transform", "translate(" + (width + i * 46) + ",0)");
    });

    var lineGen = {};
    var areaGen = {};
    (config.series || []).forEach(function (s) {
      lineGen[s.key] = d3
        .line()
        .defined(function (d) { return d[s.key] !== null && d[s.key] !== undefined && isFinite(d[s.key]); })
        .x(function (d, i) { return isPointScale ? xScale(i) : xScale(d[config.xKey]); })
        .y(function (d) { return yScales[s.yAxisId || "default"](d[s.key]); });

      // Optional shaded uncertainty band (e.g. a prediction interval) — pass
      // bandLoKey/bandHiKey on a series to enable it, no visual change for
      // series that don't set them.
      if (s.bandLoKey && s.bandHiKey) {
        areaGen[s.key] = d3
          .area()
          .defined(function (d) {
            return d[s.bandLoKey] !== null && d[s.bandLoKey] !== undefined && isFinite(d[s.bandLoKey])
              && d[s.bandHiKey] !== null && d[s.bandHiKey] !== undefined && isFinite(d[s.bandHiKey]);
          })
          .x(function (d, i) { return isPointScale ? xScale(i) : xScale(d[config.xKey]); })
          .y0(function (d) { return yScales[s.yAxisId || "default"](d[s.bandLoKey]); })
          .y1(function (d) { return yScales[s.yAxisId || "default"](d[s.bandHiKey]); });
      }
    });

    function render(domainSlice) {
      var visible = domainSlice.map(function (i) { return fullData[i]; });
      xScale = makeXScale(domainSlice);

      gridArea.selectAll("*").remove();
      var yGridScale = yScales[(yAxes[0] || {}).id || "default"];
      gridArea
        .selectAll("line.h")
        .data(yGridScale.ticks(6))
        .join("line")
        .attr("class", "h")
        .attr("x1", 0)
        .attr("x2", width)
        .attr("y1", function (v) { return yGridScale(v); })
        .attr("y2", function (v) { return yGridScale(v); })
        .attr("stroke", gridColor)
        .attr("stroke-dasharray", "3,3");

      xAxisG.selectAll("*").remove();
      xAxisG.attr("transform", "translate(0," + (config.xAxisTop ? 0 : height) + ")");
      var tickIdx = evenTicks(domainSlice.length, 10).map(function (i) { return domainSlice[i]; });
      var xAxisLine = xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
      tickIdx.forEach(function (di) {
        var rawVal = fullData[di][config.xKey];
        var xPos = isPointScale ? xScale(di) : xScale(rawVal);
        if (xPos === undefined) return;
        // "decimal": sub-1 values (e.g. a regularization alpha swept 0.001-100)
        // round to 0 under the default integer formatter — show a couple of
        // significant digits instead. Anything >=1 still reads as a plain number.
        // "raw": xKey is already a display string (e.g. "0-10%" error bands) —
        // show it verbatim instead of coercing through Math.round (-> NaN).
        var label = config.xTickFormat === "date" ? formatDateTick(rawVal)
          : config.xTickFormat === "raw" ? String(rawVal)
          : config.xTickFormat === "decimal" ? (Math.abs(rawVal) > 0 && Math.abs(rawVal) < 1 ? rawVal.toPrecision(2).replace(/0+$/, "").replace(/\.$/, "") : Math.round(rawVal).toLocaleString())
          : Math.round(rawVal).toLocaleString();
        xAxisG
          .append("text")
          .attr("x", xPos)
          .attr("y", config.xAxisTop ? -10 : 18)
          .attr("text-anchor", "middle")
          .attr("fill", axisColor)
          .style("font-size", "11px")
          .text(label);
        xAxisG
          .append("line")
          .attr("x1", xPos).attr("x2", xPos)
          .attr("y1", config.xAxisTop ? 0 : 0).attr("y2", config.xAxisTop ? -5 : 5)
          .attr("stroke", axisColor);
      });

      leftAxisGs.forEach(function (axG, i) {
        var ax = leftAxes[i];
        var sc = yScales[ax.id];
        axG.selectAll("*").remove();
        axG.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", height).attr("stroke", ax.color || axisColor);
        sc.ticks(6).forEach(function (v) {
          axG.append("text").attr("x", -8).attr("y", sc(v)).attr("dy", "0.32em").attr("text-anchor", "end")
            .attr("fill", ax.color || axisColor).style("font-size", "11px").text(formatYTick(v, ax.tickFormat));
        });
      });
      rightAxisGs.forEach(function (axG, i) {
        var ax = rightAxes[i];
        var sc = yScales[ax.id];
        axG.selectAll("*").remove();
        axG.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", height).attr("stroke", ax.color || axisColor);
        sc.ticks(6).forEach(function (v) {
          axG.append("text").attr("x", 8).attr("y", sc(v)).attr("dy", "0.32em").attr("text-anchor", "start")
            .attr("fill", ax.color || axisColor).style("font-size", "11px").text(formatYTick(v, ax.tickFormat));
        });
      });

      plotArea.selectAll("*").remove();
      // Bands first so every series' line renders on top of every band,
      // rather than interleaved band/line/band/line by series order.
      (config.series || []).forEach(function (s) {
        if (!areaGen[s.key]) return;
        plotArea
          .append("path")
          .datum(visible)
          .attr("fill", s.color)
          .attr("fill-opacity", 0.14)
          .attr("stroke", "none")
          .attr("d", areaGen[s.key]);
      });
      (config.series || []).forEach(function (s) {
        plotArea
          .append("path")
          .datum(visible)
          .attr("fill", "none")
          .attr("stroke", s.color)
          .attr("stroke-width", 2)
          .attr("d", lineGen[s.key]);
      });

      // Hover tooltip + crosshair
      var tooltip = container.__tooltip;
      var focusLine = plotArea.append("line").attr("y1", 0).attr("y2", height).attr("stroke", gridColor).style("display", "none");
      var overlay = plotArea
        .append("rect")
        .attr("width", width)
        .attr("height", height)
        .attr("fill", "transparent")
        .on("mousemove", function (event) {
          var mx = d3.pointer(event, this)[0];
          var closest = null;
          var closestDist = Infinity;
          domainSlice.forEach(function (di, idx) {
            var px = isPointScale ? xScale(idx) : xScale(fullData[di][config.xKey]);
            var dist = Math.abs(px - mx);
            if (dist < closestDist) { closestDist = dist; closest = { di: di, idx: idx, px: px }; }
          });
          if (!closest) return;
          focusLine.attr("x1", closest.px).attr("x2", closest.px).style("display", null);
          var d = fullData[closest.di];
          var lines = (config.tooltipFields || config.series || []).map(function (f) {
            var val = d[f.key];
            var text = val === null || val === undefined || !isFinite(val) ? "-" : Number(val).toFixed(2);
            // Show the shaded band's half-width alongside the point estimate
            // (e.g. a prediction interval) when the series defines one —
            // ties the number to the visual band instead of leaving the
            // band self-explanatory only from the shading.
            if (f.bandLoKey && f.bandHiKey && d[f.bandLoKey] !== null && d[f.bandLoKey] !== undefined
              && d[f.bandHiKey] !== null && d[f.bandHiKey] !== undefined && isFinite(d[f.bandLoKey]) && isFinite(d[f.bandHiKey])) {
              text += " (±" + ((d[f.bandHiKey] - d[f.bandLoKey]) / 2).toFixed(2) + ")";
            }
            return '<div style="color:' + (f.color || "var(--color-text)") + ';font-weight:600;">' + f.label + ": " + text + "</div>";
          }).join("");
          var xLabelVal = config.xTickFormat === "date" || config.xTickFormat === "raw" ? d[config.xKey] : Math.round(d[config.xKey]).toLocaleString();
          tooltip.style.display = "block";
          tooltip.innerHTML =
            '<div style="color:var(--color-text-muted);font-size:12px;margin-bottom:4px;">' + (config.xLabel || config.xKey) + ": " + xLabelVal + "</div>" + lines;
          var rect = container.getBoundingClientRect();
          tooltip.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 180) + "px";
          tooltip.style.top = event.clientY - rect.top - 10 + "px";
        })
        .on("mouseleave", function () {
          focusLine.style("display", "none");
          tooltip.style.display = "none";
        });
    }

    // Tooltip element
    var tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    container.style.position = "relative";
    container.appendChild(tooltipEl);
    container.__tooltip = tooltipEl;

    // Legend
    if (config.legend && config.series && config.series.length > 0) {
      var legend = document.createElement("div");
      legend.className = "chart-legend";
      config.series.forEach(function (s) {
        var item = document.createElement("span");
        item.className = "chart-legend-item";
        item.innerHTML = '<span class="chart-legend-swatch" style="background:' + s.color + ';"></span>' + s.label;
        legend.appendChild(item);
      });
      container.insertBefore(legend, container.firstChild);
    }

    render(xIndex);

    // Brush (zoom/pan), functional parity with Recharts <Brush>
    if (config.brush !== false && fullData.length > 3) {
      var brushG = svg
        .append("g")
        .attr("transform", "translate(" + margin.left + "," + (totalHeight - brushHeight - 8) + ")");
      brushG.append("rect").attr("width", width).attr("height", brushHeight).attr("fill", "var(--color-surface-hover)").attr("rx", 3);

      var brush = d3
        .brushX()
        .extent([[0, 0], [width, brushHeight]])
        .on("end", function (event) {
          if (!event.selection) {
            render(xIndex);
            return;
          }
          var scale = d3.scaleLinear().domain([0, width]).range([0, fullData.length - 1]);
          var i0 = Math.max(0, Math.round(scale(event.selection[0])));
          var i1 = Math.min(fullData.length - 1, Math.round(scale(event.selection[1])));
          if (i1 > i0) render(d3.range(i0, i1 + 1));
        });
      brushG.append("g").call(brush);
    }

    // Export button
    if (config.exportButtonId) {
      var btn = document.getElementById(config.exportButtonId);
      if (btn) {
        btn.onclick = function () {
          downloadCSV(fullData, config.csvFilename || "chart_data", config.csvColumns);
        };
      }
    }
  }

  function renderScatterChart(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var points = config.points || [];
    var margin = { top: 20, right: 40, bottom: 56, left: 68 };
    var totalHeight = config.height || 500;
    var width = Math.max(container.clientWidth || 800, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;

    container.innerHTML = "";
    if (points.length === 0) {
      var msg = document.createElement("p");
      msg.style.color = "var(--color-text-muted)";
      msg.style.fontSize = "13px";
      msg.textContent =
        config.xScale === "log" || config.yScale === "log"
          ? "No valid points to plot on a logarithmic scale. Log scale requires values > 0."
          : "No valid points to plot for this selection.";
      container.appendChild(msg);
      return;
    }

    var svg = d3
      .select(container)
      .append("svg")
      .attr("width", "100%")
      .attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");

    var axisColor = "var(--color-chart-axis)";
    var gridColor = "var(--color-border)";

    function buildScale(axis, isLog, logTicks, range) {
      if (isLog && logTicks && logTicks.length) {
        return d3.scaleLog().domain([logTicks[0], logTicks[logTicks.length - 1]]).range(range);
      }
      var values = points.map(function (p) { return p[axis]; });
      if (config.trendLine) values = values.concat(config.trendLine.map(function (p) { return p[axis]; }));
      if (config.refLine) values = values.concat(config.refLine.map(function (p) { return p[axis]; }));
      var extent = d3.extent(values);
      if (extent[0] === extent[1]) { extent[0] -= 1; extent[1] += 1; }
      return d3.scaleLinear().domain(extent).nice().range(range);
    }

    var xScale = buildScale("x", config.xScale === "log", config.xLogTicks, [0, width]);
    var yScale = buildScale("y", config.yScale === "log", config.yLogTicks, [height, 0]);

    var xTicks = config.xScale === "log" ? config.xLogTicks : xScale.ticks(8);
    var yTicks = config.yScale === "log" ? config.yLogTicks : yScale.ticks(8);

    // Grid
    var gridG = g.append("g");
    (yTicks || []).forEach(function (v) {
      gridG.append("line").attr("x1", 0).attr("x2", width).attr("y1", yScale(v)).attr("y2", yScale(v))
        .attr("stroke", gridColor).attr("stroke-dasharray", "3,3");
    });

    // Axes
    var xAxisG = g.append("g").attr("transform", "translate(0," + height + ")");
    xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
    (xTicks || []).forEach(function (v) {
      var px = xScale(v);
      xAxisG.append("line").attr("x1", px).attr("x2", px).attr("y1", 0).attr("y2", 5).attr("stroke", axisColor);
      xAxisG.append("text").attr("x", px).attr("y", 18).attr("text-anchor", "middle")
        .attr("fill", axisColor).style("font-size", "11px").text(formatAxisNumber(v));
    });
    xAxisG.append("text").attr("x", width / 2).attr("y", 44).attr("text-anchor", "middle")
      .attr("fill", axisColor).style("font-size", "12px").text(config.xLabel || "x");

    var yAxisG = g.append("g");
    yAxisG.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", height).attr("stroke", axisColor);
    (yTicks || []).forEach(function (v) {
      var py = yScale(v);
      yAxisG.append("line").attr("x1", -5).attr("x2", 0).attr("y1", py).attr("y2", py).attr("stroke", axisColor);
      yAxisG.append("text").attr("x", -10).attr("y", py).attr("dy", "0.32em").attr("text-anchor", "end")
        .attr("fill", axisColor).style("font-size", "11px").text(formatAxisNumber(v));
    });
    yAxisG
      .append("text")
      .attr("transform", "rotate(-90)")
      .attr("x", -height / 2)
      .attr("y", -50)
      .attr("text-anchor", "middle")
      .attr("fill", axisColor)
      .style("font-size", "12px")
      .text(config.yLabel || "y");

    // Points
    var color = config.color || "#3B82F6";
    g.append("g")
      .selectAll("circle")
      .data(points)
      .join("circle")
      .attr("cx", function (d) { return xScale(d.x); })
      .attr("cy", function (d) { return yScale(d.y); })
      .attr("r", 3)
      .attr("fill", color)
      .attr("fill-opacity", 0.6);

    // Trend line
    if (config.trendLine && config.trendLine.length === 2) {
      var line = d3.line().x(function (d) { return xScale(d.x); }).y(function (d) { return yScale(d.y); });
      g.append("path").datum(config.trendLine).attr("fill", "none").attr("stroke", "#EF4444")
        .attr("stroke-width", 2).attr("d", line);
    }

    // Reference line (e.g. the 45° perfect-model diagonal, or a zero-residual line):
    // dashed, neutral colour, included in the axis domain via buildScale above.
    if (config.refLine && config.refLine.length === 2) {
      var refL = d3.line().x(function (d) { return xScale(d.x); }).y(function (d) { return yScale(d.y); });
      g.append("path").datum(config.refLine).attr("fill", "none").attr("stroke", axisColor)
        .attr("stroke-width", 1.5).attr("stroke-dasharray", "6,4").attr("d", refL);
      if (config.refLineLabel) {
        g.append("text").attr("x", xScale(config.refLine[1].x) - 6).attr("y", yScale(config.refLine[1].y) - 6)
          .attr("text-anchor", "end").attr("fill", axisColor).style("font-size", "11px")
          .text(config.refLineLabel);
      }
    }
  }

  function formatAxisNumber(v) {
    if (Math.abs(v) >= 1000) return d3.format("~s")(v);
    return d3.format("~r")(v);
  }

  // renderLineChart's Y-axis tick label formatter. Defaults to the original
  // integer-rounding behavior (right for ft/depth/pressure-scale series); a
  // yAxes[].tickFormat of "decimal2" fixes 2 decimals (for 0-1-scale metrics
  // like R², where rounding to an integer collapses everything to "0" or "1").
  function formatYTick(v, format) {
    if (format === "decimal2") return v.toFixed(2);
    return Math.round(v).toLocaleString();
  }

  // Multi-well comparison: each well is its own independent {x,y} series
  // (equivalent to Recharts' connectNulls — no shared row grid needed).
  function renderMultiWellChart(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var wells = (config.wells || []).filter(function (w) { return w.points && w.points.length; });
    if (wells.length === 0) return;

    var margin = { top: 24, right: 32, bottom: 78, left: 56 };
    var totalHeight = config.height || 500;
    var width = Math.max(container.clientWidth || 800, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;
    var brushHeight = 24;

    container.innerHTML = "";
    var svg = d3.select(container).append("svg").attr("width", "100%").attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
    var axisColor = "var(--color-chart-axis)";
    var gridColor = "var(--color-border)";

    var allX = wells.reduce(function (acc, w) { return acc.concat(w.points.map(function (p) { return p.x; })); }, []);
    var fullXExtent = d3.extent(allX);

    var gridArea = g.append("g");
    var plotArea = g.append("g");
    var xAxisG = g.append("g").attr("transform", "translate(0," + height + ")");
    var yAxisG = g.append("g");

    function render(xDomain) {
      var xScale = d3.scaleLinear().domain(xDomain).range([0, width]);
      var visibleWells = wells.map(function (w) {
        return { key: w.key, label: w.label, color: w.color, points: w.points.filter(function (p) { return p.x >= xDomain[0] && p.x <= xDomain[1]; }) };
      });
      var allY = visibleWells.reduce(function (acc, w) { return acc.concat(w.points.map(function (p) { return p.y; })); }, []);
      var yExtent = allY.length ? d3.extent(allY) : [0, 1];
      if (yExtent[0] === yExtent[1]) { yExtent[0] -= 1; yExtent[1] += 1; }
      var yScale = d3.scaleLinear().domain(yExtent).nice().range([height, 0]);

      gridArea.selectAll("*").remove();
      yScale.ticks(6).forEach(function (v) {
        gridArea.append("line").attr("x1", 0).attr("x2", width).attr("y1", yScale(v)).attr("y2", yScale(v))
          .attr("stroke", gridColor).attr("stroke-dasharray", "3,3");
      });

      xAxisG.selectAll("*").remove();
      xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
      var step = (xDomain[1] - xDomain[0]) / 9 || 1;
      for (var i = 0; i < 10; i++) {
        var tv = xDomain[0] + step * i;
        var px = xScale(tv);
        xAxisG.append("line").attr("x1", px).attr("x2", px).attr("y1", 0).attr("y2", 5).attr("stroke", axisColor);
        xAxisG.append("text").attr("x", px).attr("y", 18).attr("text-anchor", "middle")
          .attr("fill", axisColor).style("font-size", "11px").text(Math.round(tv).toLocaleString());
      }

      yAxisG.selectAll("*").remove();
      yAxisG.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", height).attr("stroke", axisColor);
      yScale.ticks(6).forEach(function (v) {
        yAxisG.append("text").attr("x", -8).attr("y", yScale(v)).attr("dy", "0.32em").attr("text-anchor", "end")
          .attr("fill", axisColor).style("font-size", "11px").text(Math.round(v).toLocaleString());
      });

      plotArea.selectAll("*").remove();
      var line = d3.line().x(function (d) { return xScale(d.x); }).y(function (d) { return yScale(d.y); });
      visibleWells.forEach(function (w) {
        if (w.points.length < 2) return;
        plotArea.append("path").datum(w.points).attr("fill", "none").attr("stroke", w.color)
          .attr("stroke-width", 2).attr("d", line);
      });

      var tooltip = container.__tooltip;
      var focusLine = plotArea.append("line").attr("y1", 0).attr("y2", height).attr("stroke", gridColor).style("display", "none");
      plotArea.append("rect").attr("width", width).attr("height", height).attr("fill", "transparent")
        .on("mousemove", function (event) {
          var mx = d3.pointer(event, this)[0];
          var xVal = xScale.invert(mx);
          var lines = [];
          visibleWells.forEach(function (w) {
            if (!w.points.length) return;
            var bisect = d3.bisector(function (d) { return d.x; }).left;
            var idx = Math.min(w.points.length - 1, Math.max(0, bisect(w.points, xVal)));
            var pt = w.points[idx];
            lines.push('<div style="color:' + w.color + ';font-weight:600;">' + w.label + ": " + pt.y.toFixed(2) + "</div>");
          });
          focusLine.attr("x1", mx).attr("x2", mx).style("display", null);
          tooltip.style.display = "block";
          tooltip.innerHTML = '<div style="color:var(--color-text-muted);font-size:12px;margin-bottom:4px;">Depth: ' + Math.round(xVal).toLocaleString() + "</div>" + lines.join("");
          var rect = container.getBoundingClientRect();
          tooltip.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 180) + "px";
          tooltip.style.top = event.clientY - rect.top - 10 + "px";
        })
        .on("mouseleave", function () { focusLine.style("display", "none"); tooltip.style.display = "none"; });
    }

    var tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    container.style.position = "relative";
    container.appendChild(tooltipEl);
    container.__tooltip = tooltipEl;

    var legend = document.createElement("div");
    legend.className = "chart-legend";
    wells.forEach(function (w) {
      var item = document.createElement("span");
      item.className = "chart-legend-item";
      item.innerHTML = '<span class="chart-legend-swatch" style="background:' + w.color + ';"></span>' + w.label;
      legend.appendChild(item);
    });
    container.insertBefore(legend, container.firstChild);

    render(fullXExtent);

    if (wells.length && fullXExtent[0] !== fullXExtent[1]) {
      var brushG = svg.append("g").attr("transform", "translate(" + margin.left + "," + (totalHeight - brushHeight - 8) + ")");
      brushG.append("rect").attr("width", width).attr("height", brushHeight).attr("fill", "var(--color-surface-hover)").attr("rx", 3);
      var brush = d3.brushX().extent([[0, 0], [width, brushHeight]]).on("end", function (event) {
        if (!event.selection) { render(fullXExtent); return; }
        var scale = d3.scaleLinear().domain([0, width]).range(fullXExtent);
        render([scale(event.selection[0]), scale(event.selection[1])]);
      });
      brushG.append("g").call(brush);
    }

    if (config.exportButtonId) {
      var btn = document.getElementById(config.exportButtonId);
      if (btn) {
        btn.onclick = function () {
          var rows = [];
          wells.forEach(function (w) {
            w.points.forEach(function (p) { rows.push({ well_name: w.label, depth: p.x, value: p.y }); });
          });
          downloadCSV(rows, config.csvFilename || "multi_well_comparison", ["well_name", "depth", "value"]);
        };
      }
    }
  }

  // Multi-histogram: overlapping (non-stacked) semi-transparent areas, one per well,
  // sharing the same pre-binned x-axis grid computed server-side.
  function renderMultiHistogram(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var bins = config.bins || [];
    var wells = config.wells || [];
    if (bins.length === 0 || wells.length === 0) return;

    var margin = { top: 24, right: 32, bottom: 56, left: 56 };
    var totalHeight = config.height || 500;
    var width = Math.max(container.clientWidth || 800, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;

    container.innerHTML = "";
    var svg = d3.select(container).append("svg").attr("width", "100%").attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
    var axisColor = "var(--color-chart-axis)";
    var gridColor = "var(--color-border)";

    var xExtent = d3.extent(bins, function (b) { return b.bin_center; });
    var xScale = d3.scaleLinear().domain(xExtent).range([0, width]);
    var maxCount = d3.max(bins, function (b) { return d3.max(wells, function (w) { return b.counts[w.key] || 0; }); }) || 1;
    var yScale = d3.scaleLinear().domain([0, maxCount]).nice().range([height, 0]);

    yScale.ticks(6).forEach(function (v) {
      g.append("line").attr("x1", 0).attr("x2", width).attr("y1", yScale(v)).attr("y2", yScale(v))
        .attr("stroke", gridColor).attr("stroke-dasharray", "3,3");
    });

    var xAxisG = g.append("g").attr("transform", "translate(0," + height + ")");
    xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
    (config.ticks || []).forEach(function (tv) {
      var px = xScale(tv);
      xAxisG.append("line").attr("x1", px).attr("x2", px).attr("y1", 0).attr("y2", 5).attr("stroke", axisColor);
      xAxisG.append("text").attr("x", px).attr("y", 18).attr("text-anchor", "middle")
        .attr("fill", axisColor).style("font-size", "11px").text(Math.round(tv).toLocaleString());
    });
    xAxisG.append("text").attr("x", width / 2).attr("y", 44).attr("text-anchor", "middle")
      .attr("fill", axisColor).style("font-size", "12px").text(config.xLabel || "");

    var yAxisG = g.append("g");
    yAxisG.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", height).attr("stroke", axisColor);
    yScale.ticks(6).forEach(function (v) {
      yAxisG.append("text").attr("x", -8).attr("y", yScale(v)).attr("dy", "0.32em").attr("text-anchor", "end")
        .attr("fill", axisColor).style("font-size", "11px").text(v);
    });
    yAxisG.append("text").attr("transform", "rotate(-90)").attr("x", -height / 2).attr("y", -40)
      .attr("text-anchor", "middle").attr("fill", axisColor).style("font-size", "12px").text(config.yLabel || "Frequency");

    var area = d3.area()
      .x(function (b) { return xScale(b.bin_center); })
      .y0(height)
      .y1(function () { return 0; });

    wells.forEach(function (w) {
      var areaGen = d3.area()
        .x(function (b) { return xScale(b.bin_center); })
        .y0(height)
        .y1(function (b) { return yScale(b.counts[w.key] || 0); });
      g.append("path").datum(bins).attr("fill", w.color).attr("fill-opacity", 0.3)
        .attr("stroke", w.color).attr("stroke-width", 2).attr("d", areaGen);
    });

    // Tooltip: nearest bin by x position
    var tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    container.style.position = "relative";
    container.appendChild(tooltipEl);

    var focusLine = g.append("line").attr("y1", 0).attr("y2", height).attr("stroke", gridColor).style("display", "none");
    g.append("rect")
      .attr("width", width)
      .attr("height", height)
      .attr("fill", "transparent")
      .on("mousemove", function (event) {
        var mx = d3.pointer(event, this)[0];
        var xVal = xScale.invert(mx);
        var bisect = d3.bisector(function (b) { return b.bin_center; }).left;
        var idx = Math.min(bins.length - 1, Math.max(0, bisect(bins, xVal)));
        var bin = bins[idx];
        var lines = wells.map(function (w) {
          return '<div style="color:' + w.color + ';font-weight:600;">' + w.label + ": " + (bin.counts[w.key] || 0) + "</div>";
        }).join("");
        focusLine.attr("x1", xScale(bin.bin_center)).attr("x2", xScale(bin.bin_center)).style("display", null);
        tooltipEl.style.display = "block";
        tooltipEl.innerHTML =
          '<div style="color:var(--color-text-muted);font-size:12px;margin-bottom:4px;">' + (config.xLabel || "Value") + ": " + bin.bin_center.toFixed(2) + "</div>" + lines;
        var rect = container.getBoundingClientRect();
        tooltipEl.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 180) + "px";
        tooltipEl.style.top = event.clientY - rect.top - 10 + "px";
      })
      .on("mouseleave", function () {
        focusLine.style("display", "none");
        tooltipEl.style.display = "none";
      });

    var legend = document.createElement("div");
    legend.className = "chart-legend";
    wells.forEach(function (w) {
      var item = document.createElement("span");
      item.className = "chart-legend-item";
      item.innerHTML = '<span class="chart-legend-swatch" style="background:' + w.color + ';"></span>' + w.label;
      legend.appendChild(item);
    });
    container.insertBefore(legend, container.firstChild);

    if (config.exportButtonId) {
      var btn = document.getElementById(config.exportButtonId);
      if (btn) {
        btn.onclick = function () {
          var columns = ["bin_center", "bin_start", "bin_end"].concat(wells.map(function (w) { return w.label + "_count"; }));
          var rows = bins.map(function (b) {
            var row = { bin_center: b.bin_center, bin_start: b.bin_start, bin_end: b.bin_end };
            wells.forEach(function (w) { row[w.label + "_count"] = b.counts[w.key] || 0; });
            return row;
          });
          downloadCSV(rows, config.csvFilename || "multi_histogram_distribution", columns);
        };
      }
    }
  }

  // Plain histogram bars (Outlier Detection wizard Step 2 distribution chart).
  function renderBarChart(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var bins = config.bins || [];
    if (bins.length === 0) return;

    var margin = { top: 20, right: 24, bottom: 56, left: 56 };
    var totalHeight = config.height || 320;
    var width = Math.max(container.clientWidth || 700, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;

    container.innerHTML = "";
    var svg = d3.select(container).append("svg").attr("width", "100%").attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
    var axisColor = "var(--color-chart-axis)";
    var gridColor = "var(--color-border)";
    var color = config.color || "#3B82F6";

    var xExtent = [bins[0].bin_start, bins[bins.length - 1].bin_end];
    var xScale = d3.scaleLinear().domain(xExtent).range([0, width]);
    var maxCount = d3.max(bins, function (b) { return b.count; }) || 1;
    var yScale = d3.scaleLinear().domain([0, maxCount]).nice().range([height, 0]);

    yScale.ticks(5).forEach(function (v) {
      g.append("line").attr("x1", 0).attr("x2", width).attr("y1", yScale(v)).attr("y2", yScale(v))
        .attr("stroke", gridColor).attr("stroke-dasharray", "3,3");
      g.append("text").attr("x", -8).attr("y", yScale(v)).attr("dy", "0.32em").attr("text-anchor", "end")
        .attr("fill", axisColor).style("font-size", "11px").text(v);
    });

    var tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    container.style.position = "relative";
    container.appendChild(tooltipEl);

    g.selectAll("rect.bar").data(bins).join("rect")
      .attr("class", "bar")
      .attr("x", function (b) { return xScale(b.bin_start); })
      .attr("width", function (b) { return Math.max(0, xScale(b.bin_end) - xScale(b.bin_start) - 1); })
      .attr("y", function (b) { return yScale(b.count); })
      .attr("height", function (b) { return height - yScale(b.count); })
      .attr("fill", color)
      .attr("fill-opacity", 0.75)
      .on("mousemove", function (event, b) {
        tooltipEl.style.display = "block";
        tooltipEl.innerHTML =
          '<div style="color:var(--color-text-muted);font-size:12px;">' + b.bin_center.toFixed(2) + "</div>" +
          '<div style="color:' + color + ';font-weight:600;">Count: ' + b.count + "</div>";
        var rect = container.getBoundingClientRect();
        tooltipEl.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 160) + "px";
        tooltipEl.style.top = event.clientY - rect.top - 10 + "px";
      })
      .on("mouseleave", function () { tooltipEl.style.display = "none"; });

    var xAxisG = g.append("g").attr("transform", "translate(0," + height + ")");
    xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
    var tickCount = Math.min(8, bins.length);
    var step = Math.max(1, Math.round(bins.length / tickCount));
    bins.forEach(function (b, i) {
      if (i % step !== 0 && i !== bins.length - 1) return;
      var px = xScale(b.bin_center);
      xAxisG.append("line").attr("x1", px).attr("x2", px).attr("y1", 0).attr("y2", 5).attr("stroke", axisColor);
      xAxisG.append("text").attr("x", px).attr("y", 18).attr("text-anchor", "middle")
        .attr("fill", axisColor).style("font-size", "11px").text(formatAxisNumber(b.bin_center));
    });
    xAxisG.append("text").attr("x", width / 2).attr("y", 44).attr("text-anchor", "middle")
      .attr("fill", axisColor).style("font-size", "12px").text(config.xLabel || "");
  }

  // Box-and-whiskers for a single variable (Outlier Detection wizard Step 2).
  function renderBoxPlot(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var box = config.box;
    if (!box) return;

    var margin = { top: 20, right: 40, bottom: 20, left: 60 };
    var totalHeight = config.height || 220;
    var width = Math.max(container.clientWidth || 700, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;

    container.innerHTML = "";
    var svg = d3.select(container).append("svg").attr("width", "100%").attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
    var axisColor = "var(--color-chart-axis)";
    var color = config.color || "#3B82F6";
    var cy = height / 2;
    var boxHeight = Math.min(48, height * 0.5);

    var domain = [box.min, box.max];
    if (domain[0] === domain[1]) { domain[0] -= 1; domain[1] += 1; }
    var xScale = d3.scaleLinear().domain(domain).nice().range([0, width]);

    xScale.ticks(6).forEach(function (v) {
      g.append("line").attr("x1", xScale(v)).attr("x2", xScale(v)).attr("y1", 0).attr("y2", height)
        .attr("stroke", "var(--color-border)").attr("stroke-dasharray", "3,3");
      g.append("text").attr("x", xScale(v)).attr("y", height + 16).attr("text-anchor", "middle")
        .attr("fill", axisColor).style("font-size", "11px").text(formatAxisNumber(v));
    });

    // Whisker line
    g.append("line").attr("x1", xScale(box.lower_whisker)).attr("x2", xScale(box.upper_whisker))
      .attr("y1", cy).attr("y2", cy).attr("stroke", color).attr("stroke-width", 2);
    [box.lower_whisker, box.upper_whisker].forEach(function (v) {
      g.append("line").attr("x1", xScale(v)).attr("x2", xScale(v))
        .attr("y1", cy - boxHeight / 4).attr("y2", cy + boxHeight / 4)
        .attr("stroke", color).attr("stroke-width", 2);
    });

    // Q1-Q3 box
    g.append("rect")
      .attr("x", xScale(box.q1)).attr("width", Math.max(1, xScale(box.q3) - xScale(box.q1)))
      .attr("y", cy - boxHeight / 2).attr("height", boxHeight)
      .attr("fill", color).attr("fill-opacity", 0.25).attr("stroke", color).attr("stroke-width", 2);

    // Median
    g.append("line").attr("x1", xScale(box.median)).attr("x2", xScale(box.median))
      .attr("y1", cy - boxHeight / 2).attr("y2", cy + boxHeight / 2)
      .attr("stroke", color).attr("stroke-width", 3);

    var labeled = [
      { label: "Min", value: box.min }, { label: "Lower whisker", value: box.lower_whisker },
      { label: "Q1", value: box.q1 }, { label: "Median", value: box.median }, { label: "Q3", value: box.q3 },
      { label: "Upper whisker", value: box.upper_whisker }, { label: "Max", value: box.max },
    ];
    var tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    container.style.position = "relative";
    container.appendChild(tooltipEl);
    g.selectAll("circle").data(labeled).join("circle")
      .attr("cx", function (d) { return xScale(d.value); }).attr("cy", cy).attr("r", 5)
      .attr("fill", "var(--color-surface)").attr("stroke", color).attr("stroke-width", 2)
      .style("cursor", "pointer")
      .on("mousemove", function (event, d) {
        tooltipEl.style.display = "block";
        tooltipEl.innerHTML = '<div style="color:' + color + ';font-weight:600;">' + d.label + ": " + d.value.toFixed(3) + "</div>";
        var rect = container.getBoundingClientRect();
        tooltipEl.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 160) + "px";
        tooltipEl.style.top = event.clientY - rect.top - 30 + "px";
      })
      .on("mouseleave", function () { tooltipEl.style.display = "none"; });
  }

  // Explained-variance bar + cumulative line combo (PCA preview step).
  function renderVarianceChart(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var labels = config.labels || [];
    var ratios = config.ratios || [];
    var cumulative = config.cumulative || [];
    if (labels.length === 0) return;

    var margin = { top: 20, right: 48, bottom: 40, left: 48 };
    var totalHeight = config.height || 320;
    var width = Math.max(container.clientWidth || 700, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;

    container.innerHTML = "";
    var svg = d3.select(container).append("svg").attr("width", "100%").attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
    var axisColor = "var(--color-chart-axis)";

    var xScale = d3.scaleBand().domain(labels).range([0, width]).padding(0.3);
    var yScale = d3.scaleLinear().domain([0, 100]).range([height, 0]);

    yScale.ticks(5).forEach(function (v) {
      g.append("line").attr("x1", 0).attr("x2", width).attr("y1", yScale(v)).attr("y2", yScale(v))
        .attr("stroke", "var(--color-border)").attr("stroke-dasharray", "3,3");
      g.append("text").attr("x", -8).attr("y", yScale(v)).attr("dy", "0.32em").attr("text-anchor", "end")
        .attr("fill", axisColor).style("font-size", "11px").text(v + "%");
    });

    var tooltipEl = document.createElement("div");
    tooltipEl.className = "chart-tooltip";
    container.style.position = "relative";
    container.appendChild(tooltipEl);

    function showTooltip(event, l, i) {
      tooltipEl.style.display = "block";
      tooltipEl.innerHTML =
        '<div style="color:var(--color-text-muted);font-size:12px;">' + l + "</div>" +
        '<div style="color:#3B82F6;font-weight:600;">Variance: ' + ((ratios[i] || 0) * 100).toFixed(1) + "%</div>" +
        '<div style="color:#F59E0B;font-weight:600;">Cumulative: ' + (cumulative[i] || 0).toFixed(1) + "%</div>";
      var rect = container.getBoundingClientRect();
      tooltipEl.style.left = Math.min(event.clientX - rect.left + 14, rect.width - 160) + "px";
      tooltipEl.style.top = event.clientY - rect.top - 10 + "px";
    }

    g.selectAll("rect").data(labels).join("rect")
      .attr("x", function (l) { return xScale(l); }).attr("width", xScale.bandwidth())
      .attr("y", function (l, i) { return yScale((ratios[i] || 0) * 100); })
      .attr("height", function (l, i) { return height - yScale((ratios[i] || 0) * 100); })
      .attr("fill", "#3B82F6").attr("fill-opacity", 0.7)
      .style("cursor", "pointer")
      .on("mousemove", function (event, l) { showTooltip(event, l, labels.indexOf(l)); })
      .on("mouseleave", function () { tooltipEl.style.display = "none"; });

    var lineGen = d3.line()
      .x(function (l, i) { return xScale(l) + xScale.bandwidth() / 2; })
      .y(function (l, i) { return yScale(cumulative[i] || 0); });
    g.append("path").datum(labels).attr("fill", "none").attr("stroke", "#F59E0B").attr("stroke-width", 2).attr("d", lineGen);
    g.selectAll("circle").data(labels).join("circle")
      .attr("cx", function (l, i) { return xScale(l) + xScale.bandwidth() / 2; })
      .attr("cy", function (l, i) { return yScale(cumulative[i] || 0); })
      .attr("r", 4).attr("fill", "#F59E0B")
      .style("cursor", "pointer")
      .on("mousemove", function (event, l) { showTooltip(event, l, labels.indexOf(l)); })
      .on("mouseleave", function () { tooltipEl.style.display = "none"; });

    var xAxisG = g.append("g").attr("transform", "translate(0," + height + ")");
    xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
    labels.forEach(function (l) {
      xAxisG.append("text").attr("x", xScale(l) + xScale.bandwidth() / 2).attr("y", 18).attr("text-anchor", "middle")
        .attr("fill", axisColor).style("font-size", "11px").text(l);
    });

    var legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.innerHTML =
      '<span class="chart-legend-item"><span class="chart-legend-swatch" style="background:#3B82F6;"></span>Variance %</span>' +
      '<span class="chart-legend-item"><span class="chart-legend-swatch" style="background:#F59E0B;"></span>Cumulative %</span>';
    container.insertBefore(legend, container.firstChild);
  }

  // Two-color scatter (inliers vs outliers) for the Outlier Detection preview.
  function renderGroupedScatter(containerId, config) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var groups = config.groups || [];
    var allPoints = groups.reduce(function (acc, gr) { return acc.concat(gr.points); }, []);
    if (allPoints.length === 0) {
      container.innerHTML = '<p style="color:var(--color-text-muted);font-size:13px;">No points to plot.</p>';
      return;
    }

    var margin = { top: 20, right: 32, bottom: 56, left: 60 };
    var totalHeight = config.height || 460;
    var width = Math.max(container.clientWidth || 700, 300) - margin.left - margin.right;
    var height = totalHeight - margin.top - margin.bottom;

    container.innerHTML = "";
    var svg = d3.select(container).append("svg").attr("width", "100%").attr("height", totalHeight)
      .attr("viewBox", "0 0 " + (width + margin.left + margin.right) + " " + totalHeight);
    var g = svg.append("g").attr("transform", "translate(" + margin.left + "," + margin.top + ")");
    var axisColor = "var(--color-chart-axis)";

    var xExtent = d3.extent(allPoints, function (p) { return p.x; });
    var yExtent = d3.extent(allPoints, function (p) { return p.y; });
    if (xExtent[0] === xExtent[1]) { xExtent[0] -= 1; xExtent[1] += 1; }
    if (yExtent[0] === yExtent[1]) { yExtent[0] -= 1; yExtent[1] += 1; }
    var xScale = d3.scaleLinear().domain(xExtent).nice().range([0, width]);
    var yScale = d3.scaleLinear().domain(yExtent).nice().range([height, 0]);

    xScale.ticks(6).forEach(function (v) {
      g.append("line").attr("x1", xScale(v)).attr("x2", xScale(v)).attr("y1", 0).attr("y2", height)
        .attr("stroke", "var(--color-border)").attr("stroke-dasharray", "3,3");
    });

    var xAxisG = g.append("g").attr("transform", "translate(0," + height + ")");
    xAxisG.append("line").attr("x1", 0).attr("x2", width).attr("stroke", axisColor);
    xScale.ticks(6).forEach(function (v) {
      xAxisG.append("text").attr("x", xScale(v)).attr("y", 18).attr("text-anchor", "middle")
        .attr("fill", axisColor).style("font-size", "11px").text(formatAxisNumber(v));
    });
    xAxisG.append("text").attr("x", width / 2).attr("y", 44).attr("text-anchor", "middle")
      .attr("fill", axisColor).style("font-size", "12px").text(config.xLabel || "");

    var yAxisG = g.append("g");
    yAxisG.append("line").attr("x1", 0).attr("x2", 0).attr("y1", 0).attr("y2", height).attr("stroke", axisColor);
    yScale.ticks(6).forEach(function (v) {
      yAxisG.append("text").attr("x", -8).attr("y", yScale(v)).attr("dy", "0.32em").attr("text-anchor", "end")
        .attr("fill", axisColor).style("font-size", "11px").text(formatAxisNumber(v));
    });
    if (config.yLabel) {
      g.append("text").attr("x", -height / 2).attr("y", -44).attr("transform", "rotate(-90)")
        .attr("text-anchor", "middle").attr("fill", axisColor).style("font-size", "12px").text(config.yLabel);
    }

    groups.forEach(function (gr) {
      g.append("g").selectAll("circle").data(gr.points).join("circle")
        .attr("cx", function (p) { return xScale(p.x); }).attr("cy", function (p) { return yScale(p.y); })
        .attr("r", 3).attr("fill", gr.color).attr("fill-opacity", 0.65);
    });

    var legend = document.createElement("div");
    legend.className = "chart-legend";
    groups.forEach(function (gr) {
      var item = document.createElement("span");
      item.className = "chart-legend-item";
      item.innerHTML = '<span class="chart-legend-swatch" style="background:' + gr.color + ';"></span>' + gr.label + " (" + gr.points.length + ")";
      legend.appendChild(item);
    });
    container.insertBefore(legend, container.firstChild);
  }

  // ---------------------------------------------------------------------------
  // Responsive re-render. Each chart sizes itself from container.clientWidth at
  // render time and bakes that into a fixed viewBox. When the available width
  // changes WITHOUT a window resize event — e.g. collapsing the sidebar — the SVG
  // would merely letterbox. A ResizeObserver re-runs the original render at the new
  // width so the chart truly re-lays-out. Debounced, with a width-delta guard so a
  // re-render (which doesn't change the container's own width) can't loop.
  var _respRegistry = {};
  var _respObserver = null;
  var _respTimer = null;

  function _ensureRespObserver() {
    if (_respObserver || typeof ResizeObserver === "undefined") return;
    _respObserver = new ResizeObserver(function (entries) {
      if (_respTimer) clearTimeout(_respTimer);
      var ids = entries.map(function (e) { return e.target.id; });
      _respTimer = setTimeout(function () {
        ids.forEach(function (id) {
          var reg = _respRegistry[id];
          var el = id && document.getElementById(id);
          if (!reg || !el) { if (id) delete _respRegistry[id]; return; }
          var w = el.clientWidth;
          if (w && Math.abs(w - reg.lastWidth) > 2) {
            reg.lastWidth = w;
            try { reg.fn(id, reg.config); } catch (e) { /* keep other charts alive */ }
          }
        });
      }, 130);
    });
  }

  function _responsive(fn) {
    return function (containerId, config) {
      var result = fn(containerId, config);
      var el = document.getElementById(containerId);
      if (el && typeof ResizeObserver !== "undefined") {
        _respRegistry[containerId] = { fn: fn, config: config, lastWidth: el.clientWidth };
        _ensureRespObserver();
        try { _respObserver.observe(el); } catch (e) { /* already observed */ }
      }
      return result;
    };
  }

  window.DrillingCharts = {
    renderLineChart: _responsive(renderLineChart),
    renderScatterChart: _responsive(renderScatterChart),
    renderMultiWellChart: _responsive(renderMultiWellChart),
    renderMultiHistogram: _responsive(renderMultiHistogram),
    renderBarChart: _responsive(renderBarChart),
    renderBoxPlot: _responsive(renderBoxPlot),
    renderVarianceChart: _responsive(renderVarianceChart),
    renderGroupedScatter: _responsive(renderGroupedScatter),
    downloadCSV: downloadCSV,
  };
})();
