(function () {
  var lookup = document.getElementById("carnetLookup");
  var openBtn = document.getElementById("openCarnetLookup");
  var sendBtn = document.getElementById("carnetLookupSend");
  var msg = document.getElementById("carnetLookupMsg");
  var email = document.getElementById("carnetEmail");
  var phone = document.getElementById("carnetPhone");

  function setMsg(text, kind) {
    if (!msg) return;
    msg.textContent = text || "";
    msg.className = "msg" + (kind ? " " + kind : "");
  }

  if (openBtn && lookup) {
    openBtn.addEventListener("click", function () {
      lookup.classList.add("is-open");
      if (email) email.focus();
    });
  }

  if (!sendBtn) return;

  sendBtn.addEventListener("click", function () {
    var e = (email && email.value ? email.value : "").trim();
    var p = (phone && phone.value ? phone.value : "").trim();
    if (!e && !p) {
      setMsg("Indique un e-mail ou un WhatsApp.", "err");
      return;
    }
    sendBtn.disabled = true;
    setMsg("Envoi en cours…", "");

    var body = { email: e, phone: p, source: "carnet_lookup" };
    fetch("/coins/api/carnet/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        return r.json().catch(function () {
          return {};
        }).then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (res.ok && (res.data.ok || res.data.success || res.data.sent)) {
          setMsg("Lien envoyé — vérifie ton e-mail ou WhatsApp.", "ok");
          return;
        }
        /* Soft fallback: no fake magic-link success */
        setMsg(
          "On a bien reçu ta demande. Yasmine te renvoie le lien sous peu si un carnet existe.",
          "ok"
        );
      })
      .catch(function () {
        setMsg(
          "Réseau indisponible. Écris-nous sur WhatsApp ou à info@coinsmarocain.com.",
          "err"
        );
      })
      .finally(function () {
        sendBtn.disabled = false;
      });
  });
})();
