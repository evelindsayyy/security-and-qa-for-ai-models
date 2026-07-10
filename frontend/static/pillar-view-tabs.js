/**
 * List / Compare tab toggle — shared by pillar list pages.
 */
(function () {
  const tabs = document.querySelectorAll(".bench-view-tab");
  const listPanel = document.getElementById("pillar-view-list");
  const comparePanel = document.getElementById("pillar-view-compare");
  if (!tabs.length || !listPanel) return;

  const panels = { list: listPanel, compare: comparePanel };

  function showView(view) {
    tabs.forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    for (const [key, panel] of Object.entries(panels)) {
      if (!panel) continue;
      panel.hidden = key !== view;
    }
    if (view === "compare") {
      history.replaceState(null, "", "#compare");
    } else if (location.hash === "#compare") {
      history.replaceState(null, "", location.pathname);
    }
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => showView(tab.dataset.view));
  });

  if (location.hash === "#compare" && comparePanel) {
    showView("compare");
  }
})();
