/* Shared D3 renderers for the pre-spud Engineering calculators. Two chart
   types cover every module: `depthPlot` (value on X, depth on Y increasing
   downward — the drilling convention) and `xyPlot` (generic X/Y). Called from
   inline scripts inside HTMX-swapped module partials; d3 is loaded globally. */
(function () {
  "use strict";
  var AXIS = "var(--color-chart-axis)", GRID = "var(--color-border)", MUTED = "var(--color-text-muted)";

  function el(id) { var e = document.getElementById(id); if (e) e.innerHTML = ""; return e; }
  function svg(e, w, h) {
    return d3.select(e).append("svg").attr("width", "100%").attr("height", h)
      .attr("viewBox", "0 0 " + w + " " + h).attr("preserveAspectRatio", "xMidYMid meet");
  }
  function fmt(v) { var a = Math.abs(v); if (a >= 1e6) return (v/1e6).toFixed(1)+"M"; if (a >= 1e4) return (v/1e3).toFixed(0)+"K"; return (Math.round(v*100)/100).toString(); }

  function legend(e, items) {
    var w = document.createElement("div");
    w.style.cssText = "display:flex;flex-wrap:wrap;gap:14px;justify-content:center;margin-top:6px;";
    items.forEach(function (it) {
      var s = document.createElement("span");
      s.style.cssText = "display:inline-flex;align-items:center;gap:6px;font-size:12px;color:" + MUTED + ";";
      s.innerHTML = '<span style="width:16px;border-top:' + (it.dashed ? "2px dashed " : "3px solid ") + it.color + ';display:inline-block;"></span>' + it.label;
      w.appendChild(s);
    });
    e.appendChild(w);
  }

  function frame(id, w, h, m, opts) {
    var e = el(id); if (!e) return null;
    var s = svg(e, w, h);
    var g = s.append("g").attr("transform", "translate(" + m.l + "," + m.t + ")");
    return { e: e, g: g, iw: w - m.l - m.r, ih: h - m.t - m.b };
  }

  // Tooltip number format: keep precision for small values (e.g. SF 2.32), group
  // thousands for depths/pressures.
  function tf(v) {
    if (v == null || !isFinite(v)) return "-";
    var a = Math.abs(v);
    if (a >= 1000) return Math.round(v).toLocaleString();
    if (a >= 10) return (Math.round(v * 10) / 10).toString();
    return (Math.round(v * 100) / 100).toString();
  }

  function nearestBy(points, key, val) {
    var best = null, bd = Infinity;
    for (var i = 0; i < points.length; i++) {
      var p = points[i];
      if (p[key] == null || !isFinite(p[key])) continue;
      var dd = Math.abs(p[key] - val);
      if (dd < bd) { bd = dd; best = p; }
    }
    return best;
  }

  // Interactive crosshair + tooltip over a plot. mode "depth" tracks the Y
  // (depth) axis; mode "xy" tracks the X axis. Shows every series value at the
  // hovered position.
  function addFocus(f, x, y, series, opts, mode) {
    f.e.style.position = "relative";
    var tip = document.createElement("div");
    tip.style.cssText = "position:absolute;pointer-events:none;opacity:0;transition:opacity .08s;" +
      "background:var(--color-bg);border:1px solid var(--color-border);border-radius:6px;padding:6px 8px;" +
      "font-size:11px;color:var(--color-text);box-shadow:0 6px 18px rgba(0,0,0,.4);z-index:20;white-space:nowrap;";
    f.e.appendChild(tip);
    var focus = f.g.append("g").style("display", "none").style("pointer-events", "none");
    var guide = focus.append("line").attr("stroke", MUTED).attr("stroke-dasharray", "3,3");
    var dots = series.map(function (s) {
      return focus.append("circle").attr("r", 4).attr("fill", s.color).attr("stroke", "var(--color-bg)").attr("stroke-width", 1.5);
    });
    f.g.append("rect").attr("width", f.iw).attr("height", f.ih).attr("fill", "transparent")
      .style("pointer-events", "all").style("cursor", "crosshair")
      .on("mouseenter", function () { focus.style("display", null); tip.style.opacity = 1; })
      .on("mouseleave", function () { focus.style("display", "none"); tip.style.opacity = 0; })
      .on("mousemove", function (event) {
        var pt = d3.pointer(event, f.g.node());
        var rows = [], header, ref = null;
        series.forEach(function (s, i) {
          var p = mode === "depth" ? nearestBy(s.points, "y", y.invert(pt[1])) : nearestBy(s.points, "x", x.invert(pt[0]));
          if (!p) { dots[i].style("display", "none"); return; }
          dots[i].style("display", null).attr("cx", x(p.x)).attr("cy", y(p.y));
          rows.push({ s: s, v: mode === "depth" ? p.x : p.y });
          if (ref === null) ref = p;
        });
        if (ref === null) return;
        if (mode === "depth") {
          guide.attr("x1", 0).attr("x2", f.iw).attr("y1", y(ref.y)).attr("y2", y(ref.y));
          header = (opts.yLabel || "Depth") + ": " + tf(ref.y);
        } else {
          guide.attr("y1", 0).attr("y2", f.ih).attr("x1", x(ref.x)).attr("x2", x(ref.x));
          header = (opts.xLabel || "X") + ": " + tf(ref.x);
        }
        var html = '<div style="font-weight:600;margin-bottom:3px;">' + header + "</div>";
        rows.forEach(function (r) {
          html += '<div style="display:flex;align-items:center;gap:6px;">' +
            '<span style="width:9px;height:9px;border-radius:2px;background:' + r.s.color + ';display:inline-block;"></span>' +
            r.s.name + ": " + tf(r.v) + "</div>";
        });
        tip.innerHTML = html;
        var rect = f.e.getBoundingClientRect();
        var lx = event.clientX - rect.left + 14, ty = event.clientY - rect.top + 14;
        if (lx + 170 > rect.width) lx = Math.max(4, event.clientX - rect.left - 176);
        tip.style.left = lx + "px"; tip.style.top = ty + "px";
      });
  }

  // series: [{name,color,dashed,points:[{x,y}]}]  (y = depth, increases downward)
  function depthPlot(id, opts) {
    var series = (opts.series || []).filter(function (s) { return s.points && s.points.length; });
    var W = 560, H = opts.height || 420, m = { t: 16, r: 20, b: 46, l: 64 };
    var f = frame(id, W, H, m, opts); if (!f) return;
    if (!series.length) { f.e.innerHTML = '<p class="text-sm" style="color:' + MUTED + '">No data.</p>'; return; }
    var xs = [], ys = [];
    series.forEach(function (s) { s.points.forEach(function (p) { if (p.x != null) xs.push(p.x); if (p.y != null) ys.push(p.y); }); });
    var x = d3.scaleLinear().domain([Math.min(0, d3.min(xs)), d3.max(xs)]).nice().range([0, f.iw]);
    var y = d3.scaleLinear().domain([d3.min(ys), d3.max(ys)]).nice().range([0, f.ih]); // depth down
    y.ticks(8).forEach(function (v) {
      f.g.append("line").attr("x1", 0).attr("x2", f.iw).attr("y1", y(v)).attr("y2", y(v)).attr("stroke", GRID).attr("stroke-dasharray", "3,3");
      f.g.append("text").attr("x", -8).attr("y", y(v)).attr("dy", "0.32em").attr("text-anchor", "end").attr("fill", AXIS).style("font-size", "11px").text(fmt(v));
    });
    var xa = f.g.append("g").attr("transform", "translate(0," + f.ih + ")");
    xa.append("line").attr("x1", 0).attr("x2", f.iw).attr("stroke", AXIS);
    x.ticks(6).forEach(function (v) {
      xa.append("line").attr("x1", x(v)).attr("x2", x(v)).attr("y2", 5).attr("stroke", AXIS);
      xa.append("text").attr("x", x(v)).attr("y", 18).attr("text-anchor", "middle").attr("fill", AXIS).style("font-size", "11px").text(fmt(v));
    });
    f.g.append("text").attr("x", f.iw / 2).attr("y", f.ih + 42).attr("text-anchor", "middle").attr("fill", MUTED).style("font-size", "12px").text(opts.xLabel || "");
    f.g.append("text").attr("transform", "rotate(-90)").attr("x", -f.ih / 2).attr("y", -50).attr("text-anchor", "middle").attr("fill", MUTED).style("font-size", "12px").text(opts.yLabel || "Depth");
    var line = d3.line().defined(function (p) { return p.x != null && isFinite(p.x); }).x(function (p) { return x(p.x); }).y(function (p) { return y(p.y); });
    series.forEach(function (s) {
      f.g.append("path").datum(s.points).attr("fill", "none").attr("stroke", s.color).attr("stroke-width", 2).attr("stroke-dasharray", s.dashed ? "6,4" : null).attr("d", line);
    });
    addFocus(f, x, y, series, opts, "depth");
    legend(f.e, series.map(function (s) { return { label: s.name, color: s.color, dashed: s.dashed }; }));
  }

  // Generic X/Y (X value, Y value). series same shape.
  function xyPlot(id, opts) {
    var series = (opts.series || []).filter(function (s) { return s.points && s.points.length; });
    var W = 560, H = opts.height || 340, m = { t: 16, r: 20, b: 46, l: 64 };
    var f = frame(id, W, H, m, opts); if (!f) return;
    if (!series.length) { f.e.innerHTML = '<p class="text-sm" style="color:' + MUTED + '">No data.</p>'; return; }
    var xs = [], ys = [];
    series.forEach(function (s) { s.points.forEach(function (p) { if (p.x != null) xs.push(p.x); if (p.y != null) ys.push(p.y); }); });
    var x = d3.scaleLinear().domain(d3.extent(xs)).nice().range([0, f.iw]);
    var y = d3.scaleLinear().domain([Math.min(0, d3.min(ys)), d3.max(ys)]).nice().range([f.ih, 0]);
    y.ticks(6).forEach(function (v) {
      f.g.append("line").attr("x1", 0).attr("x2", f.iw).attr("y1", y(v)).attr("y2", y(v)).attr("stroke", GRID).attr("stroke-dasharray", "3,3");
      f.g.append("text").attr("x", -8).attr("y", y(v)).attr("dy", "0.32em").attr("text-anchor", "end").attr("fill", AXIS).style("font-size", "11px").text(fmt(v));
    });
    var xa = f.g.append("g").attr("transform", "translate(0," + f.ih + ")");
    xa.append("line").attr("x1", 0).attr("x2", f.iw).attr("stroke", AXIS);
    x.ticks(7).forEach(function (v) {
      xa.append("line").attr("x1", x(v)).attr("x2", x(v)).attr("y2", 5).attr("stroke", AXIS);
      xa.append("text").attr("x", x(v)).attr("y", 18).attr("text-anchor", "middle").attr("fill", AXIS).style("font-size", "11px").text(fmt(v));
    });
    f.g.append("text").attr("x", f.iw / 2).attr("y", f.ih + 42).attr("text-anchor", "middle").attr("fill", MUTED).style("font-size", "12px").text(opts.xLabel || "");
    f.g.append("text").attr("transform", "rotate(-90)").attr("x", -f.ih / 2).attr("y", -50).attr("text-anchor", "middle").attr("fill", MUTED).style("font-size", "12px").text(opts.yLabel || "");
    var line = d3.line().defined(function (p) { return p.y != null && isFinite(p.y); }).x(function (p) { return x(p.x); }).y(function (p) { return y(p.y); });
    series.forEach(function (s) {
      f.g.append("path").datum(s.points).attr("fill", "none").attr("stroke", s.color).attr("stroke-width", 2).attr("stroke-dasharray", s.dashed ? "6,4" : null).attr("d", line);
    });
    addFocus(f, x, y, series, opts, "xy");
    legend(f.e, series.map(function (s) { return { label: s.name, color: s.color, dashed: s.dashed }; }));
  }

  window.EngCharts = { depthPlot: depthPlot, xyPlot: xyPlot };
})();
