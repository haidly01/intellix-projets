/* Hub /partenaires — crée l’espace commerçant puis ouvre la fiche */
(function () {
  var form = document.getElementById("cmPartSignup");
  if (!form) return;
  var statusEl = document.getElementById("cmPartSignupStatus");
  var btn = document.getElementById("cmPartSignupSubmit");

  function notifyOdoo(payload) {
    try {
      var fd = new FormData();
      Object.keys(payload).forEach(function (k) {
        if (payload[k]) fd.append(k, payload[k]);
      });
      fetch("/coins/api/carte/signup", { method: "POST", body: fd }).catch(function () {});
    } catch (e) {}
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    if (statusEl) {
      statusEl.textContent = "";
      statusEl.className = "cm-part-status";
    }
    var placeName = (form.place_name.value || "").trim();
    var category = (form.category.value || "").trim();
    var email = (form.email.value || "").trim();
    var phone = (form.phone.value || "").trim();
    if (!placeName || !category || !email || !phone) {
      if (statusEl) {
        statusEl.textContent = "Merci de remplir tous les champs requis.";
        statusEl.className = "cm-part-status err";
      }
      return;
    }
    var payload = {
      name: placeName,
      category: category,
      contact_name: (form.contact_name.value || "").trim(),
      email: email,
      phone: phone,
      description: (form.description && form.description.value) || "",
      region: (form.quartier && form.quartier.value) || "Médina",
      signup_channel: "site_partenaires",
    };
    if (btn) btn.disabled = true;
    if (statusEl) statusEl.textContent = "Création de l’espace…";
    var create = window.CMPartner
      ? CMPartner.post("/signup", payload)
      : fetch("/partner-api/signup", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }).then(function (r) { return r.json(); });
    create
      .then(function (j) {
        if (!j || !j.ok || !j.portal_url) {
          throw new Error((j && j.error) || "signup");
        }
        if (window.CMPartner) CMPartner.rememberToken(j.token);
        notifyOdoo({
          place_name: placeName,
          category: category,
          contact_name: payload.contact_name,
          email: email,
          phone: phone,
          description: payload.description,
          signup_channel: "site_partenaires",
        });
        if (statusEl) {
          statusEl.textContent = "Espace créé. Ouverture de la fiche…";
          statusEl.className = "cm-part-status ok";
        }
        location.href = j.portal_url + (j.portal_url.indexOf("?") >= 0 ? "&" : "?") + "next=fiche#fiche";
      })
      .catch(function () {
        if (statusEl) {
          statusEl.textContent = "Impossible de créer l’accès — réessayez ou WhatsApp.";
          statusEl.className = "cm-part-status err";
        }
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  });
})();
