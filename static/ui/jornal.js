"use strict";

(function () {
  const d = document;

  function initNewsCarousel() {
    const root = d.querySelector("[data-news-carousel]");
    if (!root) return;
    const slides = Array.from(root.querySelectorAll(".jornal-news-card__slide"));
    if (slides.length <= 1) {
      slides.forEach((slide) => slide.setAttribute("aria-hidden", "false"));
      return;
    }
    const dots = Array.from(root.querySelectorAll("[data-carousel-index]"));
    const prev = root.querySelector("[data-carousel-prev]");
    const next = root.querySelector("[data-carousel-next]");
    const interval = Math.max(parseInt(root.getAttribute("data-autoplay-interval") || "9000", 10), 4000);
    let current = 0;
    let timer = null;

    const apply = (index) => {
      current = (index + slides.length) % slides.length;
      slides.forEach((slide, idx) => {
        const active = idx === current;
        slide.classList.toggle("is-active", active);
        slide.setAttribute("aria-hidden", active ? "false" : "true");
      });
      dots.forEach((dot, idx) => {
        const active = idx === current;
        dot.classList.toggle("is-active", active);
        if (active) {
          dot.setAttribute("aria-current", "true");
        } else {
          dot.removeAttribute("aria-current");
        }
      });
    };

    const stop = () => {
      if (timer) {
        window.clearInterval(timer);
        timer = null;
      }
    };

    const start = () => {
      if (root.getAttribute("data-autoplay") === "false") return;
      stop();
      timer = window.setInterval(() => apply(current + 1), interval);
    };

    prev?.addEventListener("click", () => {
      apply(current - 1);
      start();
    });

    next?.addEventListener("click", () => {
      apply(current + 1);
      start();
    });

    dots.forEach((dot) => {
      dot.addEventListener("click", () => {
        const idx = Number.parseInt(dot.getAttribute("data-carousel-index") || "0", 10);
        apply(idx);
        start();
      });
    });

    root.addEventListener("mouseenter", stop);
    root.addEventListener("mouseleave", start);
    root.addEventListener("focusin", stop);
    root.addEventListener("focusout", () => {
      if (!root.matches(":focus-within")) start();
    });

    apply(0);
    start();
  }

  function initHelperSidebar() {
    const launcher = d.getElementById("jornal-helper-launcher");
    const sidebar = d.getElementById("jornal-helper-sidebar");
    const panel = sidebar?.querySelector(".jornal-helper-sidebar__panel");
    const body = d.getElementById("jornal-helper-body");
    const pathInput = d.getElementById("jornal-helper-path");
    if (!launcher || !sidebar || !panel || !body || !pathInput) return;
    const closeButtons = sidebar.querySelectorAll("[data-helper-close]");
    let restore = null;
    let inertTargets = [];

    const focusableSelector = [
      "a[href]",
      "button:not([disabled])",
      "textarea:not([disabled])",
      "input:not([disabled])",
      "select:not([disabled])",
      "[tabindex]:not([tabindex='-1'])",
    ].join(",");

    const trapFocus = (event) => {
      if (event.key !== "Tab") return;
      const focusable = Array.from(panel.querySelectorAll(focusableSelector)).filter(
        (el) => el.offsetParent !== null
      );
      if (!focusable.length) {
        event.preventDefault();
        panel.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey) {
        if (d.activeElement === first || d.activeElement === panel) {
          event.preventDefault();
          last.focus();
        }
      } else if (d.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    const setInert = (state) => {
      if (!sidebar.parentElement) return;
      if (!inertTargets.length) {
        inertTargets = Array.from(sidebar.parentElement.children).filter((child) => child !== sidebar);
      }
      inertTargets.forEach((el) => {
        if (!(el instanceof HTMLElement)) return;
        if (state) {
          el.setAttribute("inert", "");
        } else {
          el.removeAttribute("inert");
        }
      });
    };

    const open = () => {
      if (sidebar.classList.contains("is-open")) return;
      restore = d.activeElement instanceof HTMLElement ? d.activeElement : null;
      pathInput.value = window.location.pathname || "/";
      sidebar.classList.add("is-open");
      sidebar.setAttribute("aria-hidden", "false");
      setInert(true);
      d.addEventListener("keydown", trapFocus);
      panel.focus({ preventScroll: true });
      window.requestAnimationFrame(() => {
        body.dispatchEvent(new Event("helper:open", { bubbles: true }));
      });
    };

    const close = () => {
      if (!sidebar.classList.contains("is-open")) return;
      sidebar.classList.remove("is-open");
      sidebar.setAttribute("aria-hidden", "true");
      setInert(false);
      d.removeEventListener("keydown", trapFocus);
      if (restore && typeof restore.focus === "function") {
        restore.focus();
      }
      restore = null;
    };

    launcher.addEventListener("click", open);
    closeButtons.forEach((btn) => {
      btn.addEventListener("click", close);
    });
    sidebar.addEventListener("click", (event) => {
      if (event.target instanceof HTMLElement && event.target.dataset.helperClose !== undefined) {
        close();
      }
    });
    d.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && sidebar.classList.contains("is-open")) {
        event.preventDefault();
        close();
      }
    });
    if (window.htmx) {
      body.addEventListener("htmx:afterSwap", () => {
        body.scrollTop = 0;
      });
    }
  }

  if (d.readyState === "loading") {
    d.addEventListener("DOMContentLoaded", () => {
      initNewsCarousel();
      initHelperSidebar();
    });
  } else {
    initNewsCarousel();
    initHelperSidebar();
  }
})();
