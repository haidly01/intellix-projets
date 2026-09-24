/* Source unique du Programme Ambassadeur — injecté via [data-cm-ambassadeur] */
(function () {
  var HTML =
    '<div class="section-head ambass-head">' +
    '<p class="eyebrow">Programme Ambassadeur</p>' +
    "<h2>Parrainez — notre conciergerie s'occupe du reste</h2>" +
    "<p>Recommandez Coins Marocain à vos proches. Ils confient leur séjour sur mesure " +
    "à Yasmine — hébergement, activités, transport — avec votre code. " +
    "Chaque réservation confirmée vous récompense.</p>" +
    "</div>" +
    '<ol class="tier-grid ambass-steps">' +
    '<li class="tier">' +
    '<p class="rank">Étape 01</p><h3>Votre code</h3>' +
    '<p class="perk">Un code personnel, illimité.</p><ul>' +
    "<li>Code unique lié à votre profil</li>" +
    "<li>Partageable sans limite de filleuls</li>" +
    "<li>Suivi dans votre espace</li>" +
    "</ul></li>" +
    '<li class="tier feat">' +
    '<p class="rank">Étape 02</p><h3>Ils réservent</h3>' +
    '<p class="perk">La conciergerie compose leur voyage.</p><ul>' +
    "<li>Lieu sélectionné + expériences</li>" +
    "<li>Transport privé avec chauffeur</li>" +
    "<li>Réservation liée à votre code</li>" +
    "</ul></li>" +
    '<li class="tier">' +
    '<p class="rank">Étape 03</p><h3>Vous gagnez</h3>' +
    '<p class="perk">À chaque séjour confirmé.</p><ul>' +
    "<li>Récompense sur chaque confirmation</li>" +
    "<li>Avantages cumulables sur vos voyages</li>" +
    "<li>Accès prioritaire aux nouveautés</li>" +
    "</ul></li>" +
    "</ol>" +
    '<div class="ambass-cta">' +
    '<a class="btn" href="#" data-cm="ambassador">Obtenir mon code ambassadeur →</a>' +
    "</div>";

  document.querySelectorAll("[data-cm-ambassadeur]").forEach(function (el) {
    if (el.getAttribute("data-cm-ambassadeur-ready")) return;
    el.innerHTML = HTML;
    el.setAttribute("data-cm-ambassadeur-ready", "1");
  });
})();
