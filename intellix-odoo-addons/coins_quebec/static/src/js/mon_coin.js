(function () {
  function addLine(container, kind) {
    var wrap = document.createElement("div");
    wrap.className = "line";
    wrap.innerHTML =
      '<input type="hidden" name="' + kind + '_id" value="">' +
      '<input type="text" name="' + kind + '_name" placeholder="Nom">' +
      '<input type="text" name="' + kind + '_price" placeholder="Prix CAD">' +
      '<input type="text" name="' + kind + '_unit" placeholder="Unité / détail">' +
      '<button type="button" class="btn btn-ghost mc-remove">✕</button>';
    container.appendChild(wrap);
  }
  document.querySelectorAll("[data-add]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var kind = btn.getAttribute("data-add");
      var box = document.getElementById(kind + "-lines");
      if (box) addLine(box, kind === "packages" ? "offer" : "service");
    });
  });
  document.addEventListener("click", function (ev) {
    if (ev.target.classList.contains("mc-remove")) {
      var line = ev.target.closest(".line");
      if (line) line.remove();
    }
    var reportBtn = ev.target.closest("[data-toggle-report]");
    if (reportBtn) {
      var row = reportBtn.closest("tr");
      var next = row && row.nextElementSibling;
      if (next && next.classList.contains("mini-report")) {
        next.classList.toggle("open");
      }
    }
    var filter = ev.target.closest("[data-filter-review]");
    if (filter) {
      var active = filter.classList.toggle("is-filtering");
      filter.classList.toggle("off", !active);
      document.querySelectorAll("#call-log tr").forEach(function (r) {
        if (r.classList.contains("mini-report")) {
          if (!active) r.classList.remove("open");
          return;
        }
        r.style.display = (!active || r.classList.contains("to-review")) ? "" : "none";
      });
    }
  });
})();
