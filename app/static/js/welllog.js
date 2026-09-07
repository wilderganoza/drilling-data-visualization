/* Vanilla-JS/SVG port of WellLogView.tsx — multi-track well log viewer.
 * All state (tracks, zoom, tooltip) lives client-side after one data fetch,
 * same as the React version: no server round-trips for track edits. */
(function () {
  "use strict";

  var TRACK_COLORS = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"];

  function minOf(values) {
    var m = Infinity;
    for (var i = 0; i < values.length; i++) if (values[i] < m) m = values[i];
    return m === Infinity ? 0 : m;
  }
  function maxOf(values) {
    var m = -Infinity;
    for (var i = 0; i < values.length; i++) if (values[i] > m) m = values[i];
    return m === -Infinity ? 1 : m;
  }
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function init(containerId, config) {
    var root = document.getElementById(containerId);
    if (!root) return;

    var data = config.data || [];
    var depthKey = config.depthKey;
    var availableParameters = config.availableParameters || [];
    var height = config.height || 600;
    var paramLabels = config.paramLabels || {};
    // Optional per-parameter overrides — absent for every existing caller (e.g.
    // /logs), so behavior there is unchanged. Lets a caller that already knows
    // exactly what it wants to compare (e.g. actual vs predicted ROP) start
    // pre-populated instead of forcing the user through "+ Add Track"/"Add
    // parameter" just to see a chart of two curves it could have shown directly.
    var paramColor = config.paramColor || {};   // {paramKey: '#hex'} — overrides the index-rotated default
    var paramStyle = config.paramStyle || {};    // {paramKey: 'scatter'} — small dots instead of a connecting line; default is 'line'

    function label(p) {
      return paramLabels[p] || p;
    }

    var depthValues = [];
    for (var i = 0; i < data.length; i++) {
      var v = data[i][depthKey];
      if (v !== null && v !== undefined) depthValues.push(v);
    }
    var fullMinDepth = minOf(depthValues);
    var fullMaxDepth = maxOf(depthValues);

    // Pre-seeded tracks (config.initialTracks) instead of the usual single
    // blank one — same track object shape "+ Add Track"/"Add parameter"
    // already build by hand, so the user can still edit/extend from here.
    var initialTracks = (config.initialTracks || []).map(function (t, i) {
      return { id: String(i + 1), name: t.name || ("Track " + (i + 1)),
               parameters: (t.parameters || []).slice(), scaleType: t.scaleType || "linear",
               // same_scale: all parameters in this track share one min/max axis
               // instead of each being independently auto-scaled — for comparing
               // curves that are already in the same unit (e.g. actual vs predicted).
               sameScale: !!t.same_scale,
               color: TRACK_COLORS[i % TRACK_COLORS.length] };
    });
    var trackSeq = initialTracks.length || 1;
    var state = {
      tracks: initialTracks.length ? initialTracks
             : [{ id: "1", name: "Track 1", parameters: [], scaleType: "linear", color: TRACK_COLORS[0] }],
      zoomRange: null,
      isDragging: false,
      dragSelection: null,
    };

    function depthBounds() {
      var minDepth = state.zoomRange ? state.zoomRange.min : fullMinDepth;
      var maxDepth = state.zoomRange ? state.zoomRange.max : fullMaxDepth;
      return { minDepth: minDepth, maxDepth: maxDepth, depthRange: (maxDepth - minDepth) || 1 };
    }

    // ---- Controls panel ----
    function renderControls() {
      var html = '<div class="flex gap-5" style="flex-wrap: wrap;">';
      state.tracks.forEach(function (track) {
        html += '<div style="width: 260px;">';
        html += '<div class="rounded-lg p-3" style="background-color: var(--color-surface); border: 1px solid var(--color-border);">';
        html += '<div class="flex items-center gap-2" style="margin-bottom: 8px;">';
        html +=
          '<input type="text" class="form-input" data-action="track-name" data-track-id="' +
          track.id +
          '" value="' +
          esc(track.name) +
          '" style="flex: 1;" />';
        html +=
          '<button type="button" data-action="remove-track" data-track-id="' +
          track.id +
          '" class="icon-btn" ' +
          (state.tracks.length === 1 ? "disabled" : "") +
          ' title="Remove track">' +
          '<svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>' +
          "</button>";
        html += "</div>";

        html += '<select class="form-select" style="margin-bottom: 8px;" data-action="add-param" data-track-id="' + track.id + '">';
        html += '<option value="">Add parameter...</option>';
        availableParameters
          .filter(function (p) { return track.parameters.indexOf(p) === -1; })
          .forEach(function (p) { html += '<option value="' + esc(p) + '">' + esc(label(p)) + "</option>"; });
        html += "</select>";

        html += '<div style="margin-bottom: 8px; display: flex; flex-direction: column; gap: 4px;">';
        track.parameters.forEach(function (p) {
          html +=
            '<div class="flex items-center justify-between px-3 py-2 rounded" style="background-color: var(--color-surface-hover); border: 1px solid var(--color-border);">' +
            '<span class="text-sm truncate" style="flex:1; color: var(--color-text);">' +
            esc(label(p)) +
            "</span>" +
            '<button type="button" data-action="remove-param" data-track-id="' +
            track.id +
            '" data-param="' +
            esc(p) +
            '" style="color: var(--color-danger); background: none; border: none; cursor: pointer; width: 20px; height: 20px;">' +
            '<svg width="16" height="16" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>' +
            "</button></div>";
        });
        html += "</div>";

        html += '<select class="form-select" data-action="scale-type" data-track-id="' + track.id + '">';
        html += '<option value="linear" ' + (track.scaleType === "linear" ? "selected" : "") + ">Linear</option>";
        html += '<option value="logarithmic" ' + (track.scaleType === "logarithmic" ? "selected" : "") + ">Logarithmic</option>";
        html += "</select>";

        html += "</div></div>";
      });
      html += "</div>";
      root.querySelector(".welllog-controls").innerHTML = html;
    }

    // ---- SVG tracks ----
    function scaleValueFor(track, values, minVal, maxVal, trackWidth) {
      var range = maxVal - minVal || 1;
      if (track.scaleType === "logarithmic") {
        var logMin = Math.log10(minVal || 0.1);
        var logMax = Math.log10(maxVal || 1);
        var logRange = logMax - logMin || 1;
        return function (value) {
          var logValue = Math.log10(value || 0.1);
          return ((logValue - logMin) / logRange) * (trackWidth - 20) + 10;
        };
      }
      return function (value) {
        return ((value - minVal) / range) * (trackWidth - 20) + 10;
      };
    }

    function renderTracks() {
      var bounds = depthBounds();
      var trackWidth = 260;
      var svgHeight = height + 40;
      var svgEls = [];

      state.tracks.forEach(function (track) {
        // same_scale tracks: one min/max across every parameter's combined
        // values, computed once up front so all curves share the same axis.
        var sharedMin = null, sharedMax = null;
        if (track.sameScale) {
          var allValues = [];
          track.parameters.forEach(function (param) {
            for (var i = 0; i < data.length; i++) {
              var v = data[i][param];
              if (v !== null && v !== undefined && !isNaN(v)) allValues.push(v);
            }
          });
          sharedMin = allValues.length ? minOf(allValues) : 0;
          sharedMax = allValues.length ? maxOf(allValues) : 1;
        }
        var trackData = track.parameters.map(function (param, idx) {
          var values = [];
          for (var i = 0; i < data.length; i++) {
            var v = data[i][param];
            if (v !== null && v !== undefined && !isNaN(v)) values.push(v);
          }
          var minVal = track.sameScale ? sharedMin : (values.length ? minOf(values) : 0);
          var maxVal = track.sameScale ? sharedMax : (values.length ? maxOf(values) : 1);
          return { param: param, color: paramColor[param] || TRACK_COLORS[idx % TRACK_COLORS.length],
                  style: paramStyle[param] || "line",
                  minVal: minVal, maxVal: maxVal, scaleValue: scaleValueFor(track, values, minVal, maxVal, trackWidth) };
        });

        var svgNS = "http://www.w3.org/2000/svg";
        var svg = document.createElementNS(svgNS, "svg");
        svg.setAttribute("width", trackWidth);
        svg.setAttribute("height", svgHeight);
        svg.setAttribute("data-track-id", track.id);
        svg.style.backgroundColor = "var(--color-surface)";
        svg.style.border = "1px solid var(--color-border)";
        svg.style.borderRadius = "6px";
        svg.style.cursor = state.isDragging ? "ns-resize" : "crosshair";

        function el(tag, attrs) {
          var e = document.createElementNS(svgNS, tag);
          for (var k in attrs) e.setAttribute(k, attrs[k]);
          return e;
        }

        svg.appendChild(el("rect", { width: trackWidth, height: svgHeight, fill: "var(--color-surface)" }));

        if (state.isDragging && state.dragSelection && state.dragSelection.trackId === track.id) {
          var y0 = Math.min(state.dragSelection.startY, state.dragSelection.currentY);
          var h = Math.abs(state.dragSelection.currentY - state.dragSelection.startY);
          svg.appendChild(el("rect", { x: 0, y: y0, width: trackWidth, height: h, fill: "rgba(59,130,246,0.2)", stroke: "#3B82F6", "stroke-width": 2, "stroke-dasharray": "5,5" }));
        }

        [0, 0.2, 0.4, 0.6, 0.8, 1].forEach(function (fraction) {
          var y = 30 + fraction * (height - 60);
          var depth = bounds.minDepth + fraction * bounds.depthRange;
          var line = el("line", { x1: 10, y1: y, x2: trackWidth - 10, y2: y, stroke: "var(--color-border)", "stroke-width": fraction === 0 || fraction === 1 ? 2 : 1 });
          if (!(fraction === 0 || fraction === 1)) line.setAttribute("stroke-dasharray", "3 3");
          svg.appendChild(line);
          var text = el("text", { x: trackWidth - 12, y: y + 12, fill: "var(--color-text-muted)", "font-size": 10, "text-anchor": "end" });
          text.textContent = depth.toFixed(0) + " ft";
          svg.appendChild(text);
        });

        svg.appendChild(el("line", { x1: 10, y1: 30, x2: 10, y2: height - 30, stroke: "var(--color-border)" }));
        svg.appendChild(el("line", { x1: trackWidth - 10, y1: 30, x2: trackWidth - 10, y2: height - 30, stroke: "var(--color-border)" }));

        var clipId = "welllog-clip-" + containerId + "-" + track.id;
        var defs = el("defs", {});
        var clip = el("clipPath", { id: clipId });
        clip.appendChild(el("rect", { x: 0, y: 30, width: trackWidth, height: height - 60 }));
        defs.appendChild(clip);
        svg.appendChild(defs);

        trackData.forEach(function (td) {
          var points = [];
          for (var i = 0; i < data.length; i++) {
            var depth = data[i][depthKey];
            var value = data[i][td.param];
            if (depth == null || depth < bounds.minDepth || depth > bounds.maxDepth) continue;
            if (value === null || value === undefined || isNaN(value)) continue;
            points.push({ x: td.scaleValue(value), y: 30 + ((depth - bounds.minDepth) / bounds.depthRange) * (height - 60), depth: depth, value: value });
          }
          points.sort(function (a, b) { return a.depth - b.depth; });
          var d = points.map(function (p, i) { return (i === 0 ? "M " : "L ") + p.x + " " + p.y; }).join(" ");

          var g = el("g", { "clip-path": "url(#" + clipId + ")" });
          if (td.style === "scatter") {
            points.forEach(function (p) {
              g.appendChild(el("circle", { cx: p.x, cy: p.y, r: 2.5, fill: td.color }));
            });
          } else {
            g.appendChild(el("path", { d: d, stroke: td.color, "stroke-width": 2, fill: "none" }));
          }
          // Hit-test path stays the same regardless of visible style (line or
          // scatter) — hovering near where the curve/points run still shows
          // the tooltip.
          var hit = el("path", { d: d, stroke: "transparent", "stroke-width": 10, fill: "none" });
          hit.__points = points;
          hit.__param = td.param;
          hit.style.cursor = "crosshair";
          g.appendChild(hit);
          svg.appendChild(g);
        });

        // same_scale tracks: min/max is identical for every parameter, so draw
        // the label pair once instead of once per curve.
        var labelRows = track.sameScale ? trackData.slice(0, 1) : trackData;
        labelRows.forEach(function (td, idx) {
          var yPos = 20 + idx * 14;
          svg.appendChild(el("rect", { x: 8, y: yPos - 10, width: 45, height: 13, fill: "var(--color-surface-hover)", stroke: "var(--color-border)", "stroke-width": 0.5, rx: 2 }));
          var minText = el("text", { x: 12, y: yPos, fill: "var(--color-text)", "font-size": 11, "font-weight": "bold" });
          minText.textContent = td.minVal.toFixed(1);
          svg.appendChild(minText);
          svg.appendChild(el("rect", { x: trackWidth - 53, y: yPos - 10, width: 45, height: 13, fill: "var(--color-surface-hover)", stroke: "var(--color-border)", "stroke-width": 0.5, rx: 2 }));
          var maxText = el("text", { x: trackWidth - 12, y: yPos, fill: "var(--color-text)", "font-size": 11, "font-weight": "bold", "text-anchor": "end" });
          maxText.textContent = td.maxVal.toFixed(1);
          svg.appendChild(maxText);
        });

        svgEls.push(svg);
      });

      var host = root.querySelector(".welllog-tracks-inner");
      host.innerHTML = "";
      svgEls.forEach(function (svg) {
        var wrap = document.createElement("div");
        wrap.appendChild(svg);
        host.appendChild(wrap);
      });
    }

    function render() {
      renderControls();
      renderTracks();
      var resetBtn = root.querySelector('[data-action="reset-zoom"]');
      if (resetBtn) resetBtn.disabled = !state.zoomRange;
    }

    // During drag, only move a single <rect> instead of rebuilding the whole
    // SVG (curves included) on every mousemove — that full rebuild was the
    // cause of the laggy/over-sensitive selection reported by the user.
    var svgNS = "http://www.w3.org/2000/svg";
    function updateDragRectOnly() {
      if (!state.dragSelection) return;
      var svg = root.querySelector('svg[data-track-id="' + state.dragSelection.trackId + '"]');
      if (!svg) return;
      var y0 = Math.min(state.dragSelection.startY, state.dragSelection.currentY);
      var h = Math.abs(state.dragSelection.currentY - state.dragSelection.startY);
      var rectEl = svg.querySelector('[data-role="drag-rect"]');
      if (!rectEl) {
        rectEl = document.createElementNS(svgNS, "rect");
        rectEl.setAttribute("data-role", "drag-rect");
        rectEl.setAttribute("x", 0);
        rectEl.setAttribute("width", 260);
        rectEl.setAttribute("fill", "rgba(59,130,246,0.2)");
        rectEl.setAttribute("stroke", "#3B82F6");
        rectEl.setAttribute("stroke-width", 2);
        rectEl.setAttribute("stroke-dasharray", "5,5");
        svg.appendChild(rectEl);
      }
      rectEl.setAttribute("y", y0);
      rectEl.setAttribute("height", h);
    }

    // ---- Interaction ----
    function yToDepth(y, svgHeight) {
      var bounds = depthBounds();
      var relativeY = y - 30;
      var fraction = relativeY / (svgHeight - 60);
      return bounds.minDepth + fraction * bounds.depthRange;
    }

    var tooltipEl = root.querySelector(".welllog-tooltip");

    function finishDrag() {
      if (!state.isDragging || !state.dragSelection) return;
      var svg = root.querySelector('svg[data-track-id="' + state.dragSelection.trackId + '"]');
      var svgHeight = svg ? svg.getBoundingClientRect().height : height + 40;
      var d1 = yToDepth(state.dragSelection.startY, svgHeight);
      var d2 = yToDepth(state.dragSelection.currentY, svgHeight);
      var newMin = Math.max(fullMinDepth, Math.min(d1, d2));
      var newMax = Math.min(fullMaxDepth, Math.max(d1, d2));
      var zoomed = Math.abs(newMax - newMin) > 10;
      if (zoomed) state.zoomRange = { min: newMin, max: newMax };
      state.isDragging = false;
      state.dragSelection = null;
      if (zoomed) {
        // Real drag: rebuild the whole SVG once, now that dragging is over.
        render();
      } else if (svg) {
        // Plain click (e.g. one half of a double-click) — no full rebuild,
        // just drop the leftover selection rect so it doesn't linger.
        var rectEl = svg.querySelector('[data-role="drag-rect"]');
        if (rectEl) rectEl.remove();
        svg.style.cursor = "crosshair";
      }
    }

    root.addEventListener("mousedown", function (e) {
      var svg = e.target.closest("svg[data-track-id]");
      if (!svg) return;
      // Prevent native text/image drag-selection from hijacking the gesture
      // once the mouse crosses over the depth-grid <text> labels.
      e.preventDefault();
      var rect = svg.getBoundingClientRect();
      var y = e.clientY - rect.top;
      state.isDragging = true;
      state.dragSelection = { trackId: svg.getAttribute("data-track-id"), startY: y, currentY: y };
      tooltipEl.style.display = "none";
      svg.style.cursor = "ns-resize";
      updateDragRectOnly();

      // Track the rest of the gesture on `document`, not just this widget,
      // so a fast/imprecise drag that strays outside the narrow 260px-wide
      // track (or outside the widget entirely) still keeps updating and
      // still ends cleanly on mouseup.
      function onDocMove(ev) {
        var freshSvg = root.querySelector('svg[data-track-id="' + state.dragSelection.trackId + '"]');
        if (!freshSvg) return;
        var r = freshSvg.getBoundingClientRect();
        state.dragSelection.currentY = ev.clientY - r.top;
        updateDragRectOnly();
      }
      function onDocUp() {
        document.removeEventListener("mousemove", onDocMove);
        document.removeEventListener("mouseup", onDocUp);
        finishDrag();
      }
      document.addEventListener("mousemove", onDocMove);
      document.addEventListener("mouseup", onDocUp);
    });

    root.addEventListener("mousemove", function (e) {
      if (state.isDragging) return;
      if (e.target.tagName === "path" && e.target.__points) {
        var svgEl = e.target.ownerSVGElement;
        var pt = svgEl.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        var ctm = svgEl.getScreenCTM();
        if (!ctm) return;
        var svgP = pt.matrixTransform(ctm.inverse());
        var closest = null;
        var minDist = Infinity;
        e.target.__points.forEach(function (p) {
          var dist = Math.sqrt(Math.pow(p.x - svgP.x, 2) + Math.pow(p.y - svgP.y, 2));
          if (dist < minDist) { minDist = dist; closest = p; }
        });
        if (closest && minDist < 20) {
          tooltipEl.style.display = "block";
          tooltipEl.style.left = e.clientX + 10 + "px";
          tooltipEl.style.top = e.clientY + 10 + "px";
          tooltipEl.innerHTML =
            '<div class="text-xs" style="line-height:1.6;">' +
            '<p style="color:#60A5FA;font-weight:600;">' + esc(label(e.target.__param)) + "</p>" +
            '<p style="color:#D1D5DB;"><span style="color:#6B7280;">Depth:</span> ' + closest.depth.toFixed(2) + " ft</p>" +
            '<p style="color:#D1D5DB;"><span style="color:#6B7280;">Value:</span> ' + closest.value.toFixed(3) + "</p></div>";
        }
      } else {
        tooltipEl.style.display = "none";
      }
    });

    root.addEventListener("dblclick", function (e) {
      if (!e.target.closest("svg[data-track-id]")) return;
      state.zoomRange = null;
      render();
    });

    root.addEventListener("input", function (e) {
      if (e.target.getAttribute("data-action") === "track-name") {
        var track = state.tracks.filter(function (t) { return t.id === e.target.getAttribute("data-track-id"); })[0];
        if (track) track.name = e.target.value;
      }
    });

    root.addEventListener("change", function (e) {
      var action = e.target.getAttribute("data-action");
      var trackId = e.target.getAttribute("data-track-id");
      if (action === "add-param" && e.target.value) {
        var track = state.tracks.filter(function (t) { return t.id === trackId; })[0];
        if (track && track.parameters.indexOf(e.target.value) === -1) track.parameters.push(e.target.value);
        render();
      } else if (action === "scale-type") {
        var track2 = state.tracks.filter(function (t) { return t.id === trackId; })[0];
        if (track2) track2.scaleType = e.target.value;
        render();
      }
    });

    root.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-action]");
      if (!btn) return;
      var action = btn.getAttribute("data-action");
      if (action === "remove-track") {
        if (state.tracks.length > 1) state.tracks = state.tracks.filter(function (t) { return t.id !== btn.getAttribute("data-track-id"); });
        render();
      } else if (action === "remove-param") {
        var track = state.tracks.filter(function (t) { return t.id === btn.getAttribute("data-track-id"); })[0];
        if (track) track.parameters = track.parameters.filter(function (p) { return p !== btn.getAttribute("data-param"); });
        render();
      } else if (action === "add-track") {
        trackSeq += 1;
        state.tracks.push({ id: String(Date.now()) + trackSeq, name: "Track " + (state.tracks.length + 1), parameters: [], scaleType: "linear", color: TRACK_COLORS[state.tracks.length % TRACK_COLORS.length] });
        render();
      } else if (action === "reset-zoom") {
        state.zoomRange = null;
        render();
      } else if (action === "export-csv") {
        var allParams = [];
        state.tracks.forEach(function (t) { t.parameters.forEach(function (p) { if (allParams.indexOf(p) === -1) allParams.push(p); }); });
        var columns = [depthKey].concat(allParams);
        if (window.DrillingCharts) window.DrillingCharts.downloadCSV(data, "well_log_data", columns);
      }
    });

    render();
  }

  window.WellLogView = { init: init };
})();
