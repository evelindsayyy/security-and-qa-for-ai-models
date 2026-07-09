// Shared numeric-sort helper for the run-table sort/filter scripts on
// eval_run.html and benchmarks.html. Each page's own sort/group/filter logic
// stays page-specific (their column sets and controls genuinely differ) —
// this is only the parseFloat-with-NaN-fallback comparator both pages need.
function num(row, key) {
  const v = parseFloat(row.dataset[key]);
  return isNaN(v) ? -Infinity : v;
}
