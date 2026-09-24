/* Hub /activites — stub (catalogue sync label) */
(function () {
  var el = document.getElementById("synced");
  if (!el) return;
  try {
    el.textContent = new Date().toLocaleDateString("fr-FR", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch (e) {
    el.textContent = "à jour";
  }
})();
