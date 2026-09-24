(function () {
  var form = document.getElementById("ctForm");
  if (!form) return;

  var voyageurBlock = document.getElementById("ctVoyageur");
  var entrepriseBlock = document.getElementById("ctEntreprise");
  var statusEl = document.getElementById("ctStatus");
  var submitBtn = document.getElementById("ctSubmit");

  function requestType() {
    var checked = form.querySelector('input[name="request_type"]:checked');
    return checked ? checked.value : "voyageur";
  }

  function syncPanels() {
    var t = requestType();
    var isV = t === "voyageur";
    if (voyageurBlock) voyageurBlock.hidden = !isV;
    if (entrepriseBlock) entrepriseBlock.hidden = isV;
    form.querySelectorAll("#ctVoyageur [name], #ctVoyageur input").forEach(function (el) {
      if (el.name) el.disabled = !isV;
    });
    form.querySelectorAll("#ctEntreprise [name], #ctEntreprise input").forEach(function (el) {
      if (el.name) el.disabled = isV;
    });
  }

  form.querySelectorAll('input[name="request_type"]').forEach(function (r) {
    r.addEventListener("change", syncPanels);
  });
  syncPanels();

  function setStatus(msg, kind) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.className = "ct-status" + (kind ? " " + kind : "");
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    setStatus("");
    var t = requestType();
    function val(n) {
      var el = form.elements.namedItem(n);
      if (!el) return "";
      if (el instanceof RadioNodeList) return (el.value || "").trim();
      return (el.value || "").trim();
    }
    var name = val("name");
    var email = val("email");
    var phone = val("phone");
    var message = val("message");
    if (!name || !email || !phone) {
      setStatus("Merci de renseigner nom, courriel et téléphone.", "err");
      return;
    }

    var consentEl = form.elements.namedItem("consentement_promo_whatsapp");
    var payload = {
      request_type: t,
      name: name,
      email: email,
      phone: phone,
      message: message,
      consentement_promo_whatsapp: !!(consentEl && consentEl.checked),
    };

    if (t === "voyageur") {
      payload.date_arrivee = val("date_arrivee");
      payload.date_depart = val("date_depart");
      payload.taille_groupe = val("taille_groupe_v");
      payload.budget = val("budget");
      payload.interests = Array.prototype.map
        .call(form.querySelectorAll('input[name="interest"]:checked'), function (c) {
          return c.value;
        });
    } else {
      payload.company_name = val("company_name");
      payload.taille_groupe = val("taille_groupe_e");
      payload.date_arrivee = val("date_entreprise_debut");
      payload.date_depart = val("date_entreprise_fin");
      payload.event_type = val("event_type");
      if (!payload.company_name) {
        setStatus("Merci d’indiquer le nom de l’entreprise.", "err");
        return;
      }
    }

    if (submitBtn) submitBtn.disabled = true;
    setStatus("Envoi en cours…");

    fetch("/coins/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok && j && j.ok, j: j };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          var err = (res.j && res.j.error) || "server";
          var map = {
            email: "Courriel invalide.",
            phone: "Téléphone requis.",
            name: "Nom requis.",
            request_type: "Choisissez Voyageur ou Entreprise.",
          };
          setStatus(map[err] || "Envoi impossible pour le moment. Réessayez ou WhatsApp.", "err");
          return;
        }
        form.reset();
        var voyageurRadio = form.querySelector('input[name="request_type"][value="voyageur"]');
        if (voyageurRadio) voyageurRadio.checked = true;
        syncPanels();
        setStatus(
          "Merci — votre message est bien parti. Nous vous répondons rapidement (un accusé a aussi été envoyé par courriel).",
          "ok"
        );
      })
      .catch(function () {
        setStatus("Réseau indisponible. Réessayez ou contactez-nous sur WhatsApp.", "err");
      })
      .finally(function () {
        if (submitBtn) submitBtn.disabled = false;
      });
  });
})();
