/* Hub /activites — 9 portes, compteurs statiques. Aucun fetch Viator.
   Source des totaux : étape 0, 30 août 2026, Viator products/search totalCount, devise EUR.
   Désert = Merzouga (50275, 270) + Ouarzazate (23956, 106). Rabat = CITY 26851, pas TOWN 50936.
*/
(function () {
  var PORTES = [
    { slug: "marrakech", label: "Marrakech", dest: 5408, total: 7460, lat: 31.63, lng: -7.99 },
    { slug: "essaouira", label: "Essaouira", dest: 22822, total: 372, lat: 31.51, lng: -9.76 },
    { slug: "fes", label: "Fès", dest: 22151, total: 1647, lat: 34.03, lng: -5.00 },
    { slug: "chefchaouen", label: "Chefchaouen", dest: 50203, total: 170, lat: 35.17, lng: -5.26 },
    { slug: "casablanca", label: "Casablanca", dest: 4396, total: 1230, lat: 33.57, lng: -7.59 },
    { slug: "desert", label: "Désert", dest: "50275+23956", total: 374, lat: 31.20, lng: -5.40 },
    { slug: "rabat", label: "Rabat", dest: 26851, total: 281, lat: 34.02, lng: -6.84 },
    { slug: "tanger", label: "Tanger", dest: 4388, total: 900, lat: 35.76, lng: -5.83 },
    { slug: "agadir", label: "Agadir", dest: 4383, total: 1666, lat: 30.43, lng: -9.60 }
  ];

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function fmt(n) {
    return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0");
  }

  var mapEl = document.getElementById("cmActMap");
  if (!mapEl || !window.L) return;

  var map = L.map(mapEl, { scrollWheelZoom: false }).setView([32.4, -7.1], 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap"
  }).addTo(map);

  PORTES.forEach(function (d) {
    var m = L.marker([d.lat, d.lng], {
      icon: L.divIcon({
        className: "",
        html: '<div class="cm-pin-act cm-pin-sun"><span class="cm-act-disc"></span></div>',
        iconSize: [22, 22],
        iconAnchor: [11, 11]
      })
    }).addTo(map);
    m.bindPopup(
      "<b>" +
        esc(d.label) +
        "</b><br>" +
        fmt(d.total) +
        ' expériences<br><a href="/activites/' +
        d.slug +
        '">Ouvrir la porte</a>'
    );
  });
})();
