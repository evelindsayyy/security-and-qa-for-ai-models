// Shared row-expand + filter behavior for #findings-table on scan_detail.html
// and safety_detail.html. Rows carry whichever data-finding-* attributes are
// relevant to that pillar (safety adds data-finding-passed/-category; scan
// only sets severity/source) — missing attributes simply never match a
// filter value, so one script covers both tables.
(function () {
  function toggleRow(row) {
    const detail = row.nextElementSibling;
    if (!detail || !detail.classList.contains("finding-detail-row")) return;
    const open = detail.hidden;
    detail.hidden = !open;
    row.setAttribute("aria-expanded", open ? "true" : "false");
    const ind = row.querySelector(".expand-indicator");
    if (ind) ind.textContent = open ? "▾" : "▸";
  }

  document.querySelectorAll("#findings-table .finding-row").forEach(function (row) {
    row.addEventListener("click", function () { toggleRow(row); });
    row.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleRow(row); }
    });
  });

  const sel = document.getElementById("finding-filter");
  if (!sel) return;
  sel.addEventListener("change", function () {
    const v = sel.value;
    document.querySelectorAll("#findings-table .finding-row").forEach(function (row) {
      const passed = row.getAttribute("data-finding-passed");
      const sev = row.getAttribute("data-finding-severity");
      const src = row.getAttribute("data-finding-source");
      const cat = row.getAttribute("data-finding-category");
      const show = v === "all" || v === passed || v === sev || v === src || v === cat;
      row.style.display = show ? "" : "none";
      const detail = row.nextElementSibling;
      if (detail && detail.classList.contains("finding-detail-row")) {
        detail.style.display = show ? "" : "none";
        if (!show) { detail.hidden = true; row.setAttribute("aria-expanded", "false"); }
      }
    });
  });
})();
