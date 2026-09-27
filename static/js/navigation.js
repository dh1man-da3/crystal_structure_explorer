// Progressive enhancement: links stay available if JavaScript cannot load.
const navigationHeader = document.querySelector(".site-header");
const navigationToggle = document.querySelector(".site-nav-toggle");
const navigationMenu = document.getElementById("site-navigation");

if (navigationHeader && navigationToggle && navigationMenu) {
  const compactNavigation = window.matchMedia("(max-width: 760px)");

  function setNavigationOpen(open, restoreFocus = false) {
    const isOpen = open && compactNavigation.matches;
    navigationHeader.classList.toggle("is-navigation-open", isOpen);
    navigationToggle.setAttribute("aria-expanded", String(isOpen));
    navigationToggle.setAttribute("aria-label", isOpen ? "Close navigation" : "Open navigation");
    if (restoreFocus) navigationToggle.focus();
  }

  navigationHeader.classList.add("navigation-enhanced");
  navigationToggle.hidden = false;

  navigationToggle.addEventListener("click", () => {
    setNavigationOpen(navigationToggle.getAttribute("aria-expanded") !== "true");
  });
  document.addEventListener("click", (event) => {
    if (!navigationHeader.contains(event.target)) setNavigationOpen(false);
  });
  navigationMenu.addEventListener("click", (event) => {
    if (event.target.closest("a")) setNavigationOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && navigationToggle.getAttribute("aria-expanded") === "true") {
      setNavigationOpen(false, true);
    }
  });
  compactNavigation.addEventListener("change", () => {
    const moveFocus = compactNavigation.matches && navigationMenu.contains(document.activeElement);
    setNavigationOpen(false, moveFocus);
  });
}
