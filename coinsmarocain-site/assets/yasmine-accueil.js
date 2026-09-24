/* Coins Marocain — conversation d'accueil Yasmine (remplace le quiz cases à cocher).
   API : POST /coins/api/yasmine/accueil/open + /coins/api/yasmine/accueil */
(function () {
  var OPEN_API = "/coins/api/yasmine/accueil/open";
  var CHAT_API = "/coins/api/yasmine/accueil";
  var mount = document.getElementById("yasmineAccueil");
  if (!mount) return;

  function sid() {
    try {
      var s = sessionStorage.getItem("cm_yas_session");
      if (s) return s;
      s = "yas-" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4);
      sessionStorage.setItem("cm_yas_session", s);
      return s;
    } catch (e) {
      return "yas-" + Date.now();
    }
  }

  var sessionId = sid();
  var started = false;
  var opening = false;

  mount.innerHTML =
    '<div class="yas-accueil-card">' +
    '<div class="yas-accueil-head">' +
    '<img src="/assets/img/logo-emblem.png" alt="">' +
    "<div><h3>Yasmine</h3><p>Créatrice d’expérience personnalisée — on compose ton voyage ensemble</p></div>" +
    "</div>" +
    '<div class="yas-accueil-body" id="yasBody"></div>' +
    '<div class="yas-accueil-foot">' +
    '<textarea id="yasInput" rows="1" placeholder="Raconte-moi ce qui t’amène…"></textarea>' +
    '<button type="button" id="yasSend" aria-label="Envoyer">↑</button>' +
    "</div></div>";

  var body = mount.querySelector("#yasBody");
  var input = mount.querySelector("#yasInput");
  var sendBtn = mount.querySelector("#yasSend");

  function scroll() {
    body.scrollTop = body.scrollHeight;
  }

  function bubble(role, text) {
    var el = document.createElement("div");
    el.className = "yas-msg " + (role === "user" ? "user" : "bot");
    el.textContent = text;
    body.appendChild(el);
    scroll();
    return el;
  }

  function typing(on) {
    var t = body.querySelector(".yas-typing");
    if (on && !t) {
      t = document.createElement("div");
      t.className = "yas-typing";
      t.innerHTML = "<span></span><span></span><span></span>";
      body.appendChild(t);
      scroll();
    } else if (!on && t) {
      t.remove();
    }
  }

  function showReco(rec) {
    if (!rec) return;
    var wrap = document.createElement("div");
    wrap.className = "yas-reco";
    var acts = rec.activites || [];
    var html = "";
    if (acts.length) {
      html += '<div class="yas-reco-acts">';
      acts.forEach(function (a) {
        var price = a.public_price ? Math.round(a.public_price) + " MAD" : "";
        var dur = a.duration || "";
        html +=
          '<div class="yas-reco-act"><div class="thumb" aria-hidden="true"></div><div>' +
          "<h4>" +
          esc(a.name || "Expérience") +
          "</h4>" +
          "<p>" +
          esc([a.category, dur, price].filter(Boolean).join(" · ")) +
          "</p></div></div>";
      });
      html += "</div>";
    }
    var cta = rec.cta_url || "/activites.html";
    html +=
      '<a class="yas-reco-cta" href="' +
      esc(cta) +
      '">Réserver cette expérience →</a>';
    wrap.innerHTML = html;
    body.appendChild(wrap);
    scroll();
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function openSession() {
    if (started || opening) return Promise.resolve();
    opening = true;
    typing(true);
    sendBtn.disabled = true;
    return fetch(OPEN_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, language: "fr" }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        typing(false);
        sendBtn.disabled = false;
        if (j && j.session_id) sessionId = j.session_id;
        try {
          sessionStorage.setItem("cm_yas_session", sessionId);
        } catch (e) {}
        // Une seule bulle d'accueil — ignorer re-open si déjà affiché
        var hasBot = !!body.querySelector(".yas-msg.bot");
        var reply = (j && j.reply) || "";
        var broken =
          /restauration|temporairement|unavailable|maintenance/i.test(reply);
        if (broken) {
          bubble(
            "assistant",
            "Le chat est indisponible pour le moment — écrivez-moi directement sur WhatsApp, je vous réponds."
          );
          var wa = document.createElement("a");
          wa.className = "yas-reco-cta";
          wa.href =
            "https://wa.me/212660159177?text=" +
            encodeURIComponent(
              "Bonjour Yasmine, je souhaite composer mon séjour à Marrakech."
            );
          wa.target = "_blank";
          wa.rel = "noopener noreferrer";
          wa.textContent = "Continuer sur WhatsApp →";
          body.appendChild(wa);
          if (input) input.disabled = true;
          if (sendBtn) sendBtn.disabled = true;
        } else if (reply && !(j.already_open && hasBot)) {
          bubble("assistant", reply);
        } else if (!started && !hasBot) {
          bubble("assistant", "Bienvenue… Je suis Yasmine. Dis-moi ce qui t’amène.");
        }
        started = true;
        opening = false;
        window.removeEventListener("scroll", maybeStart);
      })
      .catch(function () {
        typing(false);
        sendBtn.disabled = false;
        if (!started) {
          bubble(
            "assistant",
            "Bienvenue… Je suis Yasmine. Dis-moi simplement ce qui t’amène au Maroc — je t’écoute."
          );
        }
        started = true;
        opening = false;
        window.removeEventListener("scroll", maybeStart);
      });
  }

  function send() {
    var text = (input.value || "").trim();
    if (!text) return;
    input.value = "";
    input.style.height = "auto";
    bubble("user", text);
    typing(true);
    sendBtn.disabled = true;
    fetch(CHAT_API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        message: text,
      }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        typing(false);
        sendBtn.disabled = false;
        var reply =
          (j && j.reply) ||
          "Dis-moi encore un peu — je compose quelque chose qui te ressemble.";
        bubble("assistant", reply);
        if (j && j.recommendation) showReco(j.recommendation);
        if (j && j.hot) {
          var note = document.createElement("div");
          note.className = "yas-msg bot";
          note.style.fontSize = ".85rem";
          note.style.opacity = ".85";
          note.textContent = "Un membre de l’équipe a été prévenu.";
          body.appendChild(note);
          scroll();
        }
      })
      .catch(function () {
        typing(false);
        sendBtn.disabled = false;
        bubble("assistant", "Connexion difficile… Réessaie dans un instant, je reste là.");
      });
  }

  sendBtn.addEventListener("click", function () {
    if (!started) {
      openSession().then(send);
      return;
    }
    send();
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendBtn.click();
    }
  });
  var resizeRaf = 0;
  input.addEventListener("input", function () {
    if (resizeRaf) cancelAnimationFrame(resizeRaf);
    resizeRaf = requestAnimationFrame(function () {
      resizeRaf = 0;
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 90) + "px";
    });
  });

  // Démarrage quand la section entre dans le viewport (évite reflow forcé au parse)
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(
      function (entries) {
        if (started || opening) return;
        for (var i = 0; i < entries.length; i++) {
          if (entries[i].isIntersecting) {
            openSession();
            io.disconnect();
            break;
          }
        }
      },
      { rootMargin: "10% 0px", threshold: 0.01 }
    );
    io.observe(mount);
  } else {
    requestAnimationFrame(function () {
      if (!started && !opening) openSession();
    });
  }

  window.CoinsYasmineAccueil = {
    restart: function () {
      try {
        sessionStorage.removeItem("cm_yas_session");
      } catch (e) {}
      sessionId = sid();
      body.innerHTML = "";
      started = false;
      opening = false;
      openSession();
    },
  };
})();
