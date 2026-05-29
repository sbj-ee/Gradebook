// Timestamps (login times, creation times) are stored in UTC. This rewrites any
// ".js-utc" element to the viewer's local time zone for display.
(function () {
  function pad(n) { return String(n).padStart(2, "0"); }

  // A stored "YYYY-MM-DD HH:MM[:SS]" (UTC) -> Date.
  function parseUtc(s) {
    if (!s) return null;
    var iso = s.trim().replace(" ", "T");
    if (!/([zZ]|[+-]\d{2}:?\d{2})$/.test(iso)) iso += "Z";
    var d = new Date(iso);
    return isNaN(d.getTime()) ? null : d;
  }

  function fmtLocal(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()) +
      " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }

  function init() {
    document.querySelectorAll(".js-utc").forEach(function (el) {
      var d = parseUtc(el.getAttribute("datetime") || el.textContent);
      if (d) el.textContent = fmtLocal(d);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
