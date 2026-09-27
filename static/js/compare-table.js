"use strict";

// overflow-x:auto also establishes a vertical sticky scroll ancestor. Keep
// the real thead in that scroller for exact column alignment, compensating
// only for the page's vertical scroll. No cloned/fixed header or inner y scroll.
const table = document.querySelector(".compare-page .comparison-table");
const navigation = document.querySelector(".site-header");

if (table && navigation) {
  let frame = null;

  function updateHeader() {
    frame = null;
    const tableTop = table.getBoundingClientRect().top;
    const headerHeight = table.tHead.getBoundingClientRect().height;
    const lastBody = table.tBodies[table.tBodies.length - 1];
    const bodyBottom = lastBody.getBoundingClientRect().bottom;
    const navigationBottom = navigation.getBoundingClientRect().bottom;
    // Stop at the final data row, not at the caption below the table.
    const limit = Math.max(0, bodyBottom - tableTop - headerHeight);
    const offset = Math.max(0, Math.min(navigationBottom - tableTop, limit));
    table.style.setProperty("--comparison-header-offset", `${offset}px`);
  }

  function scheduleUpdate() {
    if (frame === null) frame = requestAnimationFrame(updateHeader);
  }

  // One passive listener, coalesced into a single frame only while scrolling.
  // ResizeObserver also catches zoom, navigation wrapping and KaTeX layout.
  window.addEventListener("scroll", scheduleUpdate, { passive: true });
  const resizeObserver = new ResizeObserver(scheduleUpdate);
  resizeObserver.observe(navigation);
  resizeObserver.observe(table);
  window.addEventListener("pageshow", scheduleUpdate);
  window.addEventListener("pagehide", (event) => {
    if (event.persisted) return;
    window.removeEventListener("scroll", scheduleUpdate);
    window.removeEventListener("pageshow", scheduleUpdate);
    resizeObserver.disconnect();
    if (frame !== null) cancelAnimationFrame(frame);
  });
  updateHeader();
}
