// Shared scroll-preserving log update, used by the polling scripts on
// eval_run_detail.html and benchmark_detail.html: replace a <pre> log
// element's text without yanking the viewport away from wherever the
// reader has scrolled to, unless they were already pinned to the bottom.
function updateLogPreservingScroll(logEl, text) {
  if (typeof text !== "string" || text === logEl.textContent) return;
  const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 48;
  const prevTop = logEl.scrollTop;
  logEl.textContent = text;
  logEl.scrollTop = atBottom ? logEl.scrollHeight : prevTop;
}
