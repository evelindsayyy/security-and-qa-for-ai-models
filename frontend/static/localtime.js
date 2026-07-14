/*
 * localtime.js — render server-emitted UTC timestamps in the viewer's own timezone.
 *
 * The server stores and emits every run timestamp in UTC. Rather than guess a
 * timezone server-side, each timestamp is emitted as:
 *
 *   <time class="localtime" data-utc="2026-07-14T18:30:00Z">2026-07-14 18:30 UTC</time>
 *
 * The text inside is a plain UTC fallback (shown if JS is disabled). On load we
 * rewrite it to the browser's local timezone, which is "user customized" for
 * free — it follows each visitor's own OS/browser settings. No login needed.
 *
 * Optional per-element attributes:
 *   data-localtime="date" | "time" | "datetime"  (default: "datetime")
 *   data-localtime-tz  — force a specific IANA zone (e.g. "America/New_York")
 */
(function () {
  "use strict";

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function formatLocal(date, mode, tz) {
    var dateOpts = { year: "numeric", month: "2-digit", day: "2-digit" };
    var timeOpts = { hour: "2-digit", minute: "2-digit", hour12: false };
    if (tz) {
      dateOpts.timeZone = tz;
      timeOpts.timeZone = tz;
    }
    var datePart = "";
    var timePart = "";
    try {
      // Intl gives locale-correct, timezone-correct rendering.
      datePart = new Intl.DateTimeFormat("en-CA", dateOpts).format(date); // YYYY-MM-DD
      timePart = new Intl.DateTimeFormat("en-GB", timeOpts).format(date); // HH:MM
    } catch (err) {
      // Fallback: the runtime local zone via the Date getters.
      datePart =
        date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
      timePart = pad(date.getHours()) + ":" + pad(date.getMinutes());
    }
    if (mode === "date") return datePart;
    if (mode === "time") return timePart;
    return datePart + " " + timePart;
  }

  function tzLabel(date, tz) {
    try {
      var parts = new Intl.DateTimeFormat("en-US", {
        timeZoneName: "short",
        timeZone: tz || undefined,
      }).formatToParts(date);
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === "timeZoneName") return parts[i].value;
      }
    } catch (err) {
      /* ignore */
    }
    return "";
  }

  function convert(el) {
    var raw = el.getAttribute("data-utc");
    if (!raw) return;
    var date = new Date(raw);
    if (isNaN(date.getTime())) return; // leave the server fallback text untouched

    var mode = el.getAttribute("data-localtime") || "datetime";
    var tz = el.getAttribute("data-localtime-tz") || null;

    var label = tzLabel(date, tz);
    var text = formatLocal(date, mode, tz);
    el.textContent = label ? text + " " + label : text;
    // Full detail on hover, plus the canonical UTC value for reference.
    el.setAttribute(
      "title",
      formatLocal(date, "datetime", tz) + (label ? " " + label : "") + " · " + raw
    );
    el.classList.add("localtime-ready");
  }

  function run(root) {
    (root || document).querySelectorAll("time.localtime[data-utc]").forEach(convert);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      run(document);
    });
  } else {
    run(document);
  }

  // Expose for content injected after initial load (e.g. AJAX table refreshes).
  window.renderLocalTimes = run;
})();
