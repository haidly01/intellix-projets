/* Mini coverage map — lazy Leaflet, fuzzy zones only (no exact pins/addresses) */
(function () {
  var el = document.getElementById("evtCoverageMap");
  if (!el) return;

  var started = false;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (window.L) {
        resolve();
        return;
      }
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  function initMap() {
    if (started || !window.L) return;
    started = true;
    var map = L.map(el, {
      zoomControl: false,
      attributionControl: false,
      scrollWheelZoom: false,
      dragging: !L.Browser.mobile,
      doubleClickZoom: false,
      boxZoom: false,
      keyboard: false,
    }).setView([31.62, -7.98], 10);

    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 14,
      opacity: 0.92,
    }).addTo(map);

    var zones = [
      { name: "Médina", lat: 31.6295, lng: -7.9811, r: 2200 },
      { name: "Palmeraie", lat: 31.68, lng: -7.95, r: 3200 },
      { name: "Agafay", lat: 31.48, lng: -8.08, r: 4500 },
    ];

    zones.forEach(function (z) {
      L.circle([z.lat, z.lng], {
        radius: z.r,
        color: "#b5732f",
        weight: 1,
        opacity: 0.45,
        fillColor: "#e6b876",
        fillOpacity: 0.22,
        interactive: false,
      }).addTo(map);
      L.circleMarker([z.lat, z.lng], {
        radius: 10,
        color: "transparent",
        fillColor: "#8a4f22",
        fillOpacity: 0.28,
        interactive: false,
        className: "evt-fuzzy-dot",
      }).addTo(map);
    });

    // Soft ~30 min ring around Marrakech centre
    L.circle([31.6295, -7.9811], {
      radius: 28000,
      color: "#8a4f22",
      weight: 1,
      dashArray: "6 10",
      opacity: 0.35,
      fill: false,
      interactive: false,
    }).addTo(map);

    setTimeout(function () {
      map.invalidateSize({ animate: false });
    }, 120);
  }

  function boot() {
    loadScript("/assets/vendor/leaflet/leaflet.js?v=cm90")
      .then(initMap)
      .catch(function () {
        el.innerHTML =
          '<p class="coverage-fallback">Carte indicative — <a href="/carte">voir la carte détaillée</a></p>';
      });
  }

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            io.disconnect();
            boot();
          }
        });
      },
      { rootMargin: "200px 0px" }
    );
    io.observe(el);
  } else {
    boot();
  }
})();
