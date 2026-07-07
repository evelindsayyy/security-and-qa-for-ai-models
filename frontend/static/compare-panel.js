/**
 * Shared compare-checkbox panel — catalog and pillar list pages.
 */
(function () {
  const compareUrl = document.body.dataset.compareUrl || "/compare";

  function selectedSlugs() {
    return Array.from(document.querySelectorAll(".compare-select:checked"))
      .map((el) => el.dataset.slug)
      .filter(Boolean);
  }

  function updateBar() {
    const bar = document.getElementById("compare-bar");
    const btn = document.getElementById("compare-selected-btn");
    if (!bar || !btn) return;
    const n = selectedSlugs().length;
    bar.hidden = n === 0;
    btn.textContent = `Compare selected (${n})`;
  }

  document.addEventListener("change", (ev) => {
    if (ev.target && ev.target.classList.contains("compare-select")) {
      updateBar();
    }
  });

  const btn = document.getElementById("compare-selected-btn");
  if (btn) {
    btn.addEventListener("click", () => {
      const slugs = selectedSlugs();
      if (!slugs.length) return;
      window.location = `${compareUrl}?models=${encodeURIComponent(slugs.join(","))}`;
    });
  }

  updateBar();
})();
