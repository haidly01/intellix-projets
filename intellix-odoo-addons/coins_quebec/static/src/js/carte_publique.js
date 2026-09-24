(function () {
  var el = document.getElementById("cq-map");
  if (!el || typeof L === "undefined") return;
  var listings = [];
  try {
    listings = JSON.parse(el.getAttribute("data-listings") || "[]");
  } catch (e) {
    listings = [];
  }
  var map = L.map("cq-map").setView([45.5, -73.4], 8);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap",
  }).addTo(map);
  var bounds = [];
  listings.forEach(function (item) {
    if (item.lat == null || item.lng == null) return;
    var marker = L.marker([item.lat, item.lng]).addTo(map);
    var href = "/coins-quebec/fiche/" + item.odoo_id;
    marker.bindPopup(
      "<b>" + (item.name || "") + "</b><br>" +
      (item.address || "") +
      '<br><a href="' + href + '">Voir la fiche</a>'
    );
    marker.on("click", function () {
      fetch("/coins-quebec/carte/click/" + item.odoo_id, { method: "POST" });
    });
    bounds.push([item.lat, item.lng]);
  });
  if (bounds.length) map.fitBounds(bounds, { padding: [40, 40], maxZoom: 12 });
})();
