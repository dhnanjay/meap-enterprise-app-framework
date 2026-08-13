/* ============================================================================
   MEAP Shell — Minimal Application JavaScript (Section 19)
   Only for UI5 event bridging, HTMX enhancement, and browser APIs.
   No client-side application framework. No client-side business state.
   ============================================================================ */

(function () {
  "use strict";

  // ── HTMX global configuration ────────────────────────────────────────────
  document.body.addEventListener("htmx:configRequest", function (evt) {
    // All HTMX requests target #main-content by default
    evt.detail.headers["X-Requested-With"] = "MEAP-HTMX";
  });

  function updateActiveNavigation() {
    const path = window.location.pathname;
    document.querySelectorAll(".meap-nav-item").forEach(function (item) {
      const href = item.getAttribute("href");
      const active = href === "/" ? path === "/" : path.startsWith(href);
      item.classList.toggle("meap-nav-item--active", active);
      if (active) item.setAttribute("aria-current", "page");
      else item.removeAttribute("aria-current");
    });
  }

  function enhanceDensity() {
    const button = document.getElementById("meap-density-toggle");
    if (!button) return;

    const saved = window.localStorage.getItem("meap-density");
    const initial = saved === "comfortable" ? "comfortable" : "compact";

    function applyDensity(density) {
      const comfortable = density === "comfortable";
      document.body.dataset.density = density;
      button.textContent = comfortable ? "Comfortable" : "Compact";
      button.setAttribute("aria-label", comfortable ? "Switch to compact density" : "Switch to comfortable density");
      button.setAttribute("title", "Table density: " + density);
    }

    applyDensity(initial);
    button.addEventListener("click", function () {
      const next = document.body.dataset.density === "compact" ? "comfortable" : "compact";
      window.localStorage.setItem("meap-density", next);
      applyDensity(next);
    });
  }

  function enhanceNavigation() {
    const toggle = document.getElementById("meap-sidenav-toggle");
    const sidenav = document.getElementById("meap-sidenav");
    const scrim = document.getElementById("meap-nav-scrim");
    if (!toggle || !sidenav) return;

    function setOpen(open) {
      const isMobile = window.matchMedia("(max-width: 960px)").matches;
      sidenav.classList.toggle(isMobile ? "open" : "collapsed", !open);
      if (isMobile) sidenav.classList.toggle("open", open);
      document.body.classList.toggle("meap-nav-open", isMobile && open);
      document.body.classList.toggle("meap-rail-collapsed", !isMobile && !open);
      toggle.setAttribute("aria-expanded", String(open));
    }

    toggle.addEventListener("click", function () {
      const isMobile = window.matchMedia("(max-width: 960px)").matches;
      const open = isMobile ? sidenav.classList.contains("open") : !sidenav.classList.contains("collapsed");
      setOpen(!open);
    });
    if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
    sidenav.addEventListener("click", function (event) {
      if (event.target.closest("a") && window.matchMedia("(max-width: 960px)").matches) setOpen(false);
    });

    // Align the DOM and aria state with the responsive layout on first load.
    if (window.matchMedia("(max-width: 960px)").matches) {
      sidenav.classList.remove("collapsed");
      setOpen(false);
    } else {
      setOpen(true);
    }
  }

  // ── HTMX: scroll to top on navigation ─────────────────────────────────────
  document.body.addEventListener("htmx:afterSwap", function (evt) {
    if (evt.detail && evt.detail.target && evt.detail.target.id === "main-content") {
      evt.detail.target.scrollTop = 0;
      window.scrollTo({ top: 0, behavior: "instant" });
      updateActiveNavigation();
    }
  });

  // ── HTMX: loading indicator ───────────────────────────────────────────────
  document.body.addEventListener("htmx:beforeRequest", function () {
    const main = document.getElementById("main-content");
    if (main) main.classList.add("htmx-request");
  });

  document.body.addEventListener("htmx:afterRequest", function () {
    const main = document.getElementById("main-content");
    if (main) main.classList.remove("htmx-request");
  });

  document.body.addEventListener("htmx:responseError", function (evt) {
    const main = document.getElementById("main-content");
    if (main) main.classList.remove("htmx-request");
  });

  window.addEventListener("popstate", updateActiveNavigation);

  // ── Init ──────────────────────────────────────────────────────────────────
  function init() {
    enhanceNavigation();
    enhanceDensity();
    updateActiveNavigation();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
