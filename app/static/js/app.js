(function () {
  "use strict";

  // Apply the persisted sidebar preference (set on <html> by the early
  // head script) to <body> as soon as this deferred script runs, so the
  // toggle survives reloads without a full flash of the wrong state.
  var sidebarPref = document.documentElement.getAttribute("data-sidebar-pref");
  if (sidebarPref) document.body.setAttribute("data-sidebar", sidebarPref);

  // ---- Theme toggle (mirrors useTheme.ts: localStorage 'theme', data-theme attr) ----
  function toggleTheme() {
    var current = document.documentElement.getAttribute("data-theme") || "dark";
    var next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("theme", next);
    var btn = document.getElementById("theme-toggle-btn");
    if (btn) btn.textContent = next === "dark" ? "☀️" : "🌙";
  }

  // ---- Sidebar toggle (mirrors appStore sidebarOpen, persisted to localStorage) ----
  function toggleSidebar() {
    var isOpen = document.body.getAttribute("data-sidebar") !== "closed";
    var next = isOpen ? "closed" : "open";
    document.body.setAttribute("data-sidebar", next);
    localStorage.setItem("sidebarOpen", String(next === "open"));
  }

  // ---- Toast notifications, driven by HX-Trigger: {"toast": {...}} ----
  function showToast(detail) {
    var container = document.getElementById("toast-container");
    if (!container || !detail) return;
    var type = detail.type || "success";
    var el = document.createElement("div");
    el.className = "toast " + type;
    var icons = { success: "✓", error: "✕", warning: "⚠", info: "ℹ" };
    el.innerHTML =
      '<span style="font-weight:700;font-size:18px;">' + (icons[type] || icons.success) + "</span>" +
      '<p style="flex:1;margin:0;">' + (detail.message || "") + "</p>" +
      '<button type="button" aria-label="Dismiss">×</button>';
    el.querySelector("button").addEventListener("click", function () { el.remove(); });
    container.appendChild(el);
    setTimeout(function () { el.remove(); }, 3000);
  }

  document.body.addEventListener("toast", function (evt) {
    showToast(evt.detail);
  });

  // ---- Global htmx error feedback ----
  // htmx does not swap the DOM on a 4xx/5xx response, so without this a
  // click on a guard-rejected action (locked/approved report, permission
  // denied, oversized upload, etc.) did NOTHING VISIBLE — the server's
  // careful error message was written but never reached the user. FastAPI's
  // HTTPException bodies are JSON {"detail": "..."}; fall back to the status
  // text for anything else (e.g. a raw 500).
  document.body.addEventListener("htmx:responseError", function (evt) {
    var xhr = evt.detail.xhr;
    var message = "Something went wrong (" + xhr.status + ").";
    try {
      var body = JSON.parse(xhr.responseText);
      if (body && body.detail) message = typeof body.detail === "string" ? body.detail : message;
    } catch (e) { /* not JSON — keep the generic message */ }
    showToast({ type: "error", message: message });
  });
  document.body.addEventListener("htmx:sendError", function () {
    showToast({ type: "error", message: "Network error — the request never reached the server." });
  });

  // ---- Custom confirm modal, replacing window.confirm() (parity with ConfirmDialog.tsx) ----
  var confirmResolver = null;

  function openConfirmModal(message) {
    var backdrop = document.getElementById("confirm-modal-backdrop");
    var messageEl = document.getElementById("confirm-modal-message");
    if (!backdrop || !messageEl) return Promise.resolve(true);
    messageEl.textContent = message;
    backdrop.classList.add("open");
    return new Promise(function (resolve) {
      confirmResolver = resolve;
    });
  }

  function closeConfirmModal(result) {
    var backdrop = document.getElementById("confirm-modal-backdrop");
    if (backdrop) backdrop.classList.remove("open");
    if (confirmResolver) {
      confirmResolver(result);
      confirmResolver = null;
    }
  }

  document.body.addEventListener("htmx:confirm", function (evt) {
    var question = evt.detail.question;
    if (!question) return;
    evt.preventDefault();
    openConfirmModal(question).then(function (ok) {
      if (ok) evt.detail.issueRequest(true);
    });
  });

  // ---- Generic form modals (data-open-modal="#id" / data-close-modal) ----
  // Delegated so this works for modals swapped in later by htmx, without
  // per-instance listener setup — mirrors the combo-dropdown pattern.
  document.addEventListener("click", function (e) {
    var opener = e.target.closest("[data-open-modal]");
    if (opener) {
      var target = document.querySelector(opener.getAttribute("data-open-modal"));
      if (target) {
        target.classList.add("open");
        var firstField = target.querySelector("input, select, textarea");
        if (firstField) firstField.focus();
      }
      return;
    }
    var closer = e.target.closest("[data-close-modal]");
    if (closer) {
      var backdrop = closer.closest(".modal-backdrop");
      if (backdrop) backdrop.classList.remove("open");
      return;
    }
    if (e.target.classList.contains("modal-backdrop")) {
      e.target.classList.remove("open");
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    document.querySelectorAll(".modal-backdrop.open").forEach(function (m) { m.classList.remove("open"); });
  });

  document.addEventListener("DOMContentLoaded", function () {
    var themeBtn = document.getElementById("theme-toggle-btn");
    if (themeBtn) {
      var currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
      themeBtn.textContent = currentTheme === "dark" ? "☀️" : "🌙";
      themeBtn.addEventListener("click", toggleTheme);
    }

    var sidebarBtn = document.getElementById("sidebar-toggle-btn");
    if (sidebarBtn) sidebarBtn.addEventListener("click", toggleSidebar);

    var confirmYes = document.getElementById("confirm-modal-confirm-btn");
    var confirmNo = document.getElementById("confirm-modal-cancel-btn");
    if (confirmYes) confirmYes.addEventListener("click", function () { closeConfirmModal(true); });
    if (confirmNo) confirmNo.addEventListener("click", function () { closeConfirmModal(false); });
    var backdrop = document.getElementById("confirm-modal-backdrop");
    if (backdrop) {
      backdrop.addEventListener("click", function (e) {
        if (e.target === backdrop) closeConfirmModal(false);
      });
    }
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeConfirmModal(false);
    });
  });

  // Sidebar hierarchy tree: every full page load re-fetches the tree from
  // scratch (no SPA state carries across navigations), so without this it
  // resets to fully-collapsed on every click. The server hands down the
  // ancestor-id chain for whatever entity the current page is showing via
  // data-open-ids/data-active-id; this walks that chain, opening each
  // <details> in turn by setting .open = true, which fires the native
  // `toggle` event that the tree's existing `hx-trigger="toggle once"`
  // already listens for — no parallel pre-expanded rendering path needed.
  function expandTreeChain(container, ids, activeId) {
    if (!ids.length) return;
    var id = ids[0];
    var node = container.querySelector('[data-node-id="' + id + '"]');
    if (!node) return;
    if (id === activeId) {
      var link = node.querySelector("a");
      if (link) {
        link.classList.add("tree-active");
        link.scrollIntoView({ block: "center" });
      }
    }
    if (node.tagName !== "DETAILS") return;
    var rest = ids.slice(1);
    if (!rest.length) return;
    if (node.open) {
      var children = node.querySelector(".tree-children");
      if (children) expandTreeChain(children, rest, activeId);
      return;
    }
    node.addEventListener(
      "htmx:afterSwap",
      function onSwap() {
        var children = node.querySelector(".tree-children");
        if (children) expandTreeChain(children, rest, activeId);
      },
      { once: true }
    );
    node.open = true;
  }

  document.body.addEventListener("htmx:afterSwap", function (evt) {
    var tree = evt.detail && evt.detail.target;
    if (!tree || tree.id !== "ops-tree") return;
    var openIds = (tree.dataset.openIds || "").split(",").filter(Boolean);
    var activeId = tree.dataset.activeId || "";
    if (openIds.length) expandTreeChain(tree, openIds, activeId);
  });

  // Report subsection tab bars: highlight whichever [data-tab-btn] was
  // clicked. The actual content swap is plain htmx (hx-get/hx-target); this
  // only owns the active-state styling, kept generic so every future
  // subsection tab bar (Fluids, Daily Cost, ...) reuses it for free.
  document.body.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-tab-btn]");
    if (!btn) return;
    var bar = btn.closest(".tab-bar");
    if (!bar) return;
    bar.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
    btn.classList.add("active");
  });
})();
