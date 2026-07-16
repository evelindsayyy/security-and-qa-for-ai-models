import "./styles/app.css";
import { mountAllIslands } from "./mount.tsx";

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", mountAllIslands);
} else {
  mountAllIslands();
}

// Shell interactions (sidebar drawer, expandable text)
document.addEventListener("click", (e) => {
  const toggle = (e.target as HTMLElement).closest("[data-sidebar-toggle]");
  if (toggle) {
    document.body.classList.toggle("sidebar-open");
  }
});

function initExpandables(root: ParentNode = document): void {
  root.querySelectorAll<HTMLElement>(".expandable").forEach((el) => {
    if (el.dataset.expandableInit) return;
    el.dataset.expandableInit = "1";
    const body = el.querySelector<HTMLElement>(".expandable-body");
    const btn = el.querySelector<HTMLButtonElement>(".expandable-toggle");
    if (!body || !btn) return;
    const checkOverflow = () => {
      if (el.classList.contains("is-expanded")) return;
      const overflowed = body.scrollHeight > body.clientHeight + 2;
      el.classList.toggle("is-overflow", overflowed);
      btn.hidden = !overflowed;
    };
    checkOverflow();
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const expanded = el.classList.toggle("is-expanded");
      btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      btn.textContent = expanded ? "See less" : "See more";
      if (!expanded) checkOverflow();
    });
  });
}

function initRowLinks(): void {
  const go = (row: HTMLElement) => {
    const href = row.getAttribute("data-href");
    if (href) window.location.href = href;
  };
  document.addEventListener("click", (e) => {
    const row = (e.target as HTMLElement).closest<HTMLElement>("tr.row-link");
    if (!row || (e.target as HTMLElement).closest("a, button, form, input, select, textarea, label, .expandable-toggle")) return;
    go(row);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const row = (e.target as HTMLElement).closest<HTMLElement>("tr.row-link");
    if (!row) return;
    e.preventDefault();
    go(row);
  });
}

function initPillarTabs(): void {
  const tabs = document.querySelectorAll<HTMLButtonElement>(".bench-view-tab");
  const listPanel = document.getElementById("pillar-view-list") || document.getElementById("bench-view-list");
  const comparePanel = document.getElementById("pillar-view-compare") || document.getElementById("bench-view-compare");
  if (!tabs.length || !listPanel) return;

  const show = (view: string) => {
    tabs.forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    listPanel.hidden = view !== "list";
    if (comparePanel) comparePanel.hidden = view !== "compare";
    if (view === "compare") {
      history.replaceState(null, "", "#compare");
    } else if (location.hash === "#compare") {
      history.replaceState(null, "", location.pathname + location.search);
    }
  };

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => show(tab.dataset.view || "list"));
  });

  if (location.hash === "#compare" && comparePanel) {
    show("compare");
  }
}

function initGuidePanels(): void {
  document.querySelectorAll<HTMLDetailsElement>(".guide-panel").forEach((panel) => {
    if (panel.dataset.guideInit) return;
    panel.dataset.guideInit = "1";
    if (panel.dataset.openDefault === "true") panel.open = true;
  });
}

function initCompareBar(): void {
  const bar = document.getElementById("compare-bar");
  if (!bar || bar.dataset.compareInit) return;
  bar.dataset.compareInit = "1";
  const countEl = bar.querySelector("[data-compare-count]");
  const btn = bar.querySelector<HTMLButtonElement>("[data-compare-go]");
  const compareUrl = document.body.dataset.compareUrl || "/compare";
  const maxCompare = 5;

  const sync = () => {
    const all = document.querySelectorAll<HTMLInputElement>(".compare-select");
    const selected = [...all].filter((el) => el.checked).map((el) => el.value);
    all.forEach((cb) => {
      if (!cb.checked && selected.length >= maxCompare) {
        cb.disabled = true;
      } else {
        cb.disabled = false;
      }
    });
    if (countEl) {
      countEl.textContent =
        selected.length >= maxCompare ? `${selected.length} (max ${maxCompare})` : String(selected.length);
    }
    if (btn) btn.disabled = selected.length === 0;
    bar.hidden = selected.length === 0;
  };

  document.querySelectorAll<HTMLInputElement>(".compare-select").forEach((cb) => {
    cb.addEventListener("change", () => {
      const all = document.querySelectorAll<HTMLInputElement>(".compare-select");
      const selected = [...all].filter((el) => el.checked);
      if (selected.length > maxCompare) {
        cb.checked = false;
      }
      sync();
    });
  });
  btn?.addEventListener("click", () => {
    const selected = [...document.querySelectorAll<HTMLInputElement>(".compare-select:checked")].map(
      (el) => el.value,
    );
    if (selected.length) {
      const params = selected.map((s) => `models=${encodeURIComponent(s)}`).join("&");
      window.location.href = `${compareUrl}?${params}`;
    }
  });
  sync();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    initExpandables();
    initRowLinks();
    initPillarTabs();
    initGuidePanels();
    initCompareBar();
  });
} else {
  initExpandables();
  initRowLinks();
  initPillarTabs();
  initGuidePanels();
  initCompareBar();
}
