/* Self-contained D3 renderers for the operational dashboard. Reads a payload
   (window.__OPS_DASHBOARD__) produced by app/ops/services/analytics.py and
   draws: depth-vs-days (plan vs actual), cumulative cost vs budget, time
   distribution donut, NPT-by-category bar, and the vertical-section trajectory.
   Kept apart from charts.js (the frozen Dashboard engine) so it owns its own
   multi-source series without bending that engine's row-based API. */
(function () {
  "use strict";
  var AXIS = "var(--color-chart-axis)";
  var GRID = "var(--color-border)";
  var MUTED = "var(--color-text-muted)";
  var TEXT = "var(--color-text)";

  function clear(id) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = "";
    return el;
  }

  function svgIn(el, w, h) {
    return d3.select(el).append("svg")
      .attr("width", "100%").attr("height", h)
      .attr("viewBox", "0 0 " + w + " " + h)
      .attr("preserveAspectRatio", "xMidYMid meet");
  }

  function tooltip(container) {
    var t = document.createElement("div");
    t.className = "chart-tooltip";
    t.style.display = "none";
    container.style.position = "relative";
    container.appendChild(t);
    return t;
  }

  function nearestByX(points, xv) {
    var best = null, bd = Infinity;
    for (var i = 0; i < points.length; i++) {
      var p = points[i];
      if (p.x == null || p.y == null || !isFinite(p.x)) continue;
      var dd = Math.abs(p.x - xv);
      if (dd < bd) { bd = dd; best = p; }
    }
    return best;
  }

  // Crosshair + tooltip over a line chart: tracks the X axis and shows every
  // series value at the hovered position.
  function addLineFocus(el, g, x, y, series, iw, ih, opts) {
    var tip = tooltip(el);
    var yfmt = opts.yFormat || fmt;
    var focus = g.append("g").style("display", "none").style("pointer-events", "none");
    var vline = focus.append("line").attr("y1", 0).attr("y2", ih).attr("stroke", MUTED).attr("stroke-dasharray", "3,3");
    var dots = series.map(function (s) {
      return focus.append("circle").attr("r", 4).attr("fill", s.color).attr("stroke", "var(--color-bg)").attr("stroke-width", 1.5);
    });
    g.append("rect").attr("width", iw).attr("height", ih).attr("fill", "transparent")
      .style("pointer-events", "all").style("cursor", "crosshair")
      .on("mouseenter", function () { focus.style("display", null); tip.style.display = "block"; })
      .on("mouseleave", function () { focus.style("display", "none"); tip.style.display = "none"; })
      .on("mousemove", function (event) {
        var xv = x.invert(d3.pointer(event, g.node())[0]);
        var ref = null, rows = [];
        series.forEach(function (s, i) {
          var pnt = nearestByX(s.points, xv);
          if (!pnt) { dots[i].style("display", "none"); return; }
          dots[i].style("display", null).attr("cx", x(pnt.x)).attr("cy", y(pnt.y));
          rows.push({ s: s, v: pnt.y });
          if (ref === null) ref = pnt;
        });
        if (ref === null) return;
        vline.attr("x1", x(ref.x)).attr("x2", x(ref.x));
        var html = '<div style="font-weight:600;margin-bottom:3px;">' + (opts.xLabel || "X") + ": " + fmt(ref.x) + "</div>";
        rows.forEach(function (r) {
          html += '<div style="display:flex;align-items:center;gap:6px;"><span style="width:9px;height:9px;border-radius:2px;background:' +
            r.s.color + ';display:inline-block;"></span>' + r.s.name + ": " + yfmt(r.v) + "</div>";
        });
        tip.innerHTML = html;
        var rc = el.getBoundingClientRect();
        var lx = event.clientX - rc.left + 14, ty = event.clientY - rc.top + 14;
        if (lx + 176 > rc.width) lx = Math.max(4, event.clientX - rc.left - 182);
        tip.style.left = lx + "px"; tip.style.top = ty + "px";
      });
  }

  // Multi-series line chart. series: [{name,color,dashed,points:[{x,y}]}]
  function lineChart(id, opts) {
    var el = clear(id);
    if (!el) return;
    var series = (opts.series || []).filter(function (s) { return s.points && s.points.length; });
    if (!series.length) { el.innerHTML = '<p class="text-sm" style="color:' + MUTED + '">No data.</p>'; return; }
    var W = 640, H = opts.height || 320, m = { t: 16, r: 18, b: 44, l: 60 };
    var iw = W - m.l - m.r, ih = H - m.t - m.b;
    var svg = svgIn(el, W, H);
    var g = svg.append("g").attr("transform", "translate(" + m.l + "," + m.t + ")");
    var allX = [], allY = [];
    series.forEach(function (s) { s.points.forEach(function (p) { if (p.x != null) allX.push(p.x); if (p.y != null) allY.push(p.y); }); });
    var x = d3.scaleLinear().domain(d3.extent(allX)).nice().range([0, iw]);
    var yDomain = d3.extent(allY); if (yDomain[0] === yDomain[1]) yDomain = [0, yDomain[1] || 1];
    var y = d3.scaleLinear().domain(opts.padY ? [Math.min(0, yDomain[0]), yDomain[1] * 1.05] : yDomain).nice().range(opts.reverseY ? [0, ih] : [ih, 0]);

    var yfmt = opts.yFormat || fmt;
    y.ticks(6).forEach(function (v) {
      g.append("line").attr("x1", 0).attr("x2", iw).attr("y1", y(v)).attr("y2", y(v)).attr("stroke", GRID).attr("stroke-dasharray", "3,3");
      g.append("text").attr("x", -8).attr("y", y(v)).attr("dy", "0.32em").attr("text-anchor", "end").attr("fill", AXIS).style("font-size", "11px").text(yfmt(v));
    });
    var xa = g.append("g").attr("transform", "translate(0," + ih + ")");
    xa.append("line").attr("x1", 0).attr("x2", iw).attr("stroke", AXIS);
    x.ticks(8).forEach(function (v) {
      xa.append("line").attr("x1", x(v)).attr("x2", x(v)).attr("y2", 5).attr("stroke", AXIS);
      xa.append("text").attr("x", x(v)).attr("y", 18).attr("text-anchor", "middle").attr("fill", AXIS).style("font-size", "11px").text(fmt(v));
    });
    g.append("text").attr("x", iw / 2).attr("y", ih + 40).attr("text-anchor", "middle").attr("fill", MUTED).style("font-size", "12px").text(opts.xLabel || "");
    g.append("text").attr("transform", "rotate(-90)").attr("x", -ih / 2).attr("y", -46).attr("text-anchor", "middle").attr("fill", MUTED).style("font-size", "12px").text(opts.yLabel || "");

    var line = d3.line().defined(function (p) { return p.y != null && isFinite(p.y); }).x(function (p) { return x(p.x); }).y(function (p) { return y(p.y); });
    series.forEach(function (s) {
      g.append("path").datum(s.points).attr("fill", "none").attr("stroke", s.color).attr("stroke-width", 2)
        .attr("stroke-dasharray", s.dashed ? "6,4" : null).attr("d", line);
      if (!s.dashed) {
        g.selectAll(null).data(s.points.filter(function (p) { return p.y != null; })).join("circle")
          .attr("cx", function (p) { return x(p.x); }).attr("cy", function (p) { return y(p.y); }).attr("r", 2.5).attr("fill", s.color);
      }
    });
    addLineFocus(el, g, x, y, series, iw, ih, opts);
    legend(el, series.map(function (s) { return { label: s.name, color: s.color, dashed: s.dashed }; }));
  }

  // Vertical section: horizontal displacement (x) vs TVD (y, down positive)
  function trajChart(id, planPts, actualPts, du) {
    var el = clear(id);
    if (!el) return;
    du = du || "ft";
    var series = [];
    if (planPts && planPts.length) series.push({ name: "Planned", color: "#8B5CF6", dashed: true, points: planPts.map(function (p) { return { x: p.vs, y: p.tvd }; }) });
    if (actualPts && actualPts.length) series.push({ name: "Actual", color: "#10B981", points: actualPts.map(function (p) { return { x: p.vs, y: p.tvd }; }) });
    lineChart(id, { series: series, xLabel: "Vertical Section / Horizontal displacement (" + du + ")", yLabel: "TVD (" + du + ")", reverseY: true, height: 340 });
  }

  // Donut for time distribution
  function donut(id, segments) {
    var el = clear(id);
    if (!el) return;
    segments = (segments || []).filter(function (s) { return s.value > 0; });
    var total = segments.reduce(function (a, s) { return a + s.value; }, 0);
    if (!total) { el.innerHTML = '<p class="text-sm" style="color:' + MUTED + '">No data.</p>'; return; }
    var W = 320, H = 300, R = 110, r = 62;
    var svg = svgIn(el, W, H);
    var g = svg.append("g").attr("transform", "translate(" + W / 2 + "," + (H / 2 - 6) + ")");
    var pie = d3.pie().sort(null).value(function (d) { return d.value; });
    var arc = d3.arc().innerRadius(r).outerRadius(R);
    var tip = tooltip(el);
    g.selectAll("path").data(pie(segments)).join("path").attr("d", arc).attr("fill", function (d) { return d.data.color; })
      .attr("stroke", "var(--color-surface)").attr("stroke-width", 2)
      .on("mousemove", function (ev, d) {
        tip.style.display = "block";
        tip.innerHTML = '<div style="font-weight:600;color:' + d.data.color + '">' + d.data.label + '</div><div style="color:' + MUTED + '">' + d.data.value.toFixed(1) + ' hrs · ' + (d.data.value / total * 100).toFixed(1) + '%</div>';
        var rc = el.getBoundingClientRect();
        tip.style.left = (ev.clientX - rc.left + 12) + "px"; tip.style.top = (ev.clientY - rc.top - 8) + "px";
      }).on("mouseleave", function () { tip.style.display = "none"; });
    g.append("text").attr("text-anchor", "middle").attr("dy", "-0.1em").attr("fill", TEXT).style("font-size", "22px").style("font-weight", "600").text(total.toFixed(0));
    g.append("text").attr("text-anchor", "middle").attr("dy", "1.3em").attr("fill", MUTED).style("font-size", "12px").text("total hrs");
    legend(el, segments.map(function (s) { return { label: s.label + " (" + (s.value / total * 100).toFixed(0) + "%)", color: s.color }; }));
  }

  // Horizontal bar for NPT by category
  function hbar(id, items, color) {
    var el = clear(id);
    if (!el) return;
    items = (items || []).filter(function (d) { return d.value > 0; });
    if (!items.length) { el.innerHTML = '<p class="text-sm" style="color:' + MUTED + '">No NPT recorded — 100% productive.</p>'; return; }
    var W = 620, rowH = 34, H = items.length * rowH + 30, m = { l: 200, r: 60 };
    var iw = W - m.l - m.r;
    var svg = svgIn(el, W, H);
    var g = svg.append("g").attr("transform", "translate(" + m.l + ",10)");
    var max = d3.max(items, function (d) { return d.value; });
    var x = d3.scaleLinear().domain([0, max]).range([0, iw]);
    var total = d3.sum(items, function (d) { return d.value; });
    var tip = tooltip(el);
    items.forEach(function (d, i) {
      var yy = i * rowH;
      g.append("text").attr("x", -10).attr("y", yy + rowH / 2).attr("dy", "0.32em").attr("text-anchor", "end").attr("fill", TEXT).style("font-size", "12px").text(trunc(d.label, 30));
      g.append("rect").attr("x", 0).attr("y", yy + 6).attr("width", Math.max(1, x(d.value))).attr("height", rowH - 14).attr("fill", color || "#EF4444").attr("rx", 3)
        .style("cursor", "pointer")
        .on("mousemove", function (ev) {
          tip.style.display = "block";
          tip.innerHTML = '<div style="font-weight:600;">' + d.label + '</div><div style="color:' + MUTED + '">' +
            d.value.toFixed(1) + ' h · ' + (total ? (d.value / total * 100).toFixed(1) : 0) + '% of NPT</div>';
          var rc = el.getBoundingClientRect();
          tip.style.left = (ev.clientX - rc.left + 12) + "px"; tip.style.top = (ev.clientY - rc.top - 8) + "px";
        })
        .on("mouseleave", function () { tip.style.display = "none"; });
      g.append("text").attr("x", x(d.value) + 6).attr("y", yy + rowH / 2).attr("dy", "0.32em").attr("fill", MUTED).style("font-size", "11px").text(d.value.toFixed(1) + " h");
    });
  }

  function legend(el, items) {
    var wrap = document.createElement("div");
    wrap.style.cssText = "display:flex;flex-wrap:wrap;gap:14px;justify-content:center;margin-top:8px;";
    items.forEach(function (it) {
      var s = document.createElement("span");
      s.style.cssText = "display:inline-flex;align-items:center;gap:6px;font-size:12px;color:" + MUTED + ";";
      s.innerHTML = '<span style="width:16px;height:0;border-top:' + (it.dashed ? "2px dashed " : "3px solid ") + it.color + ';display:inline-block;"></span>' + it.label;
      wrap.appendChild(s);
    });
    el.appendChild(wrap);
  }

  function fmt(v) {
    if (Math.abs(v) >= 1000) return d3.format(",.0f")(v);
    return (Math.round(v * 100) / 100).toString();
  }
  // Compact money/large-number axis labels: 2,500,000 -> 2.5M, 500,000 -> 500K.
  function compact(v) {
    var a = Math.abs(v);
    if (a >= 1e6) return (v / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(0) + "K";
    return String(Math.round(v));
  }
  function trunc(s, n) { s = String(s); return s.length > n ? s.slice(0, n - 1) + "…" : s; }

  function render(p) {
    if (!window.d3) { setTimeout(function () { render(p); }, 40); return; }
    var DU = p.depth_unit || "ft";
    lineChart("chart-depth-days", {
      xLabel: "Day", yLabel: "Depth MD (" + DU + ")", reverseY: true, height: 320,
      series: [
        { name: "Planned", color: "#8B5CF6", dashed: true, points: p.planned_depth.map(function (d) { return { x: d.day, y: d.md }; }) },
        { name: "Actual", color: "#10B981", points: p.actual_depth.map(function (d) { return { x: d.day, y: d.md }; }) },
      ],
    });
    var budget = p.budget_total;
    var costSeries = [{ name: "Cumulative actual", color: "#3B82F6", points: p.cost_series.map(function (d) { return { x: d.day, y: d.cumulative }; }) }];
    if (budget) {
      var days = p.cost_series.map(function (d) { return d.day; });
      costSeries.push({ name: "AFE budget", color: "#EF4444", dashed: true, points: [{ x: Math.min.apply(null, days) || 1, y: budget }, { x: Math.max.apply(null, days) || 1, y: budget }] });
    }
    lineChart("chart-cost", { xLabel: "Day", yLabel: "Cost", padY: true, height: 320, series: costSeries, yFormat: compact });
    donut("chart-time-dist", (p.time_distribution || []).map(function (d) {
      return { label: d.label, value: d.hours, color: d.key === "NPT" ? "#EF4444" : (d.key === "SC" ? "#F59E0B" : "#10B981") };
    }));
    hbar("chart-npt", (p.npt_by_category || []).map(function (d) { return { label: d.category, value: d.hours }; }), "#EF4444");
    trajChart("chart-traj", p.plan_traj, p.actual_traj, DU);
  }

  window.OpsDashboard = { render: render };
})();
