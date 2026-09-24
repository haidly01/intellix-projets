(function () {
  var root = document.querySelector("[data-esc-tabs]");
  if (!root) return;
  var tabs = Array.prototype.slice.call(root.querySelectorAll("[role='tab']"));
  var panels = Array.prototype.slice.call(root.querySelectorAll("[role='tabpanel']"));

  function activate(id, focusTab) {
    tabs.forEach(function (tab) {
      var on = tab.getAttribute("aria-controls") === id;
      tab.setAttribute("aria-selected", on ? "true" : "false");
      tab.tabIndex = on ? 0 : -1;
      if (on && focusTab) tab.focus();
    });
    panels.forEach(function (panel) {
      var on = panel.id === id;
      if (on) panel.removeAttribute("hidden");
      else panel.setAttribute("hidden", "");
    });
    try {
      history.replaceState(null, "", "#" + id.replace(/^panel-/, ""));
    } catch (e) {}
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      activate(tab.getAttribute("aria-controls"), false);
    });
    tab.addEventListener("keydown", function (e) {
      var i = tabs.indexOf(tab);
      var next = null;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") next = tabs[(i + 1) % tabs.length];
      if (e.key === "ArrowLeft" || e.key === "ArrowUp") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (e.key === "Home") next = tabs[0];
      if (e.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        e.preventDefault();
        activate(next.getAttribute("aria-controls"), true);
      }
    });
  });

  var hash = (location.hash || "").replace(/^#/, "");
  var map = {
    medina: "panel-medina",
    environs: "panel-environs",
    desert: "panel-desert",
    montagne: "panel-montagne",
    activites: "panel-activites",
    activities: "panel-activites",
    mountain: "panel-montagne",
  };
  if (hash && map[hash]) activate(map[hash], false);
  else if (tabs[0]) activate(tabs[0].getAttribute("aria-controls"), false);
})();
