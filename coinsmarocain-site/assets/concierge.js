/* Coins Marocain — widget flottant Yasmine (chat site).
   Contrat : window.CoinsYasmine.open(msg) + POST /coins/api/concierge
   Ne remplace pas yasmine-accueil.js (#yasmineAccueil). */
(function () {
  if (window.CoinsYasmine) return;

  var API = "/coins/api/concierge";
  var WA_FALLBACK =
    "https://wa.me/212660159177?text=" +
    encodeURIComponent(
      "Bonjour Yasmine, je souhaite composer mon séjour à Marrakech."
    );
  var messages = [];
  var sending = false;
  var openedOnce = false;

  var style = document.createElement("style");
  style.textContent =
    "#cmYasFab,#cmYasPanel{font-family:Georgia,'Times New Roman',serif}" +
    "#cmYasFab{position:fixed;right:20px;bottom:20px;z-index:99980;" +
    "display:flex;align-items:center;gap:10px;border:0;cursor:pointer;" +
    "padding:12px 16px 12px 12px;border-radius:999px;" +
    "background:var(--gold-3,#b8954a);color:#1c1712;" +
    "box-shadow:0 10px 28px rgba(44,38,32,.28);font:600 14px/1.2 " +
    "'Cormorant Garamond',Georgia,serif}" +
    "#cmYasFab:hover{filter:brightness(1.05)}" +
    "#cmYasFab .dot{width:10px;height:10px;border-radius:50%;" +
    "background:#2d6a4f;box-shadow:0 0 0 3px rgba(45,106,79,.18)}" +
    "#cmYasPanel{position:fixed;right:20px;bottom:84px;z-index:99981;" +
    "width:min(380px,calc(100vw - 28px));height:min(520px,70vh);" +
    "display:none;flex-direction:column;overflow:hidden;" +
    "background:#f7f1e6;color:var(--ink,#2c2620);" +
    "border:1px solid rgba(184,149,74,.35);border-radius:18px;" +
    "box-shadow:0 18px 50px rgba(44,38,32,.28)}" +
    "#cmYasPanel.open{display:flex}" +
    "#cmYasPanel .hd{display:flex;align-items:center;gap:10px;" +
    "padding:14px 16px;background:#2c2620;color:#f7f1e6}" +
    "#cmYasPanel .hd h3{margin:0;font:600 1.15rem/1.2 " +
    "'Cormorant Garamond',Georgia,serif}" +
    "#cmYasPanel .hd p{margin:2px 0 0;opacity:.75;font:12px/1.3 " +
    "system-ui,sans-serif}" +
    "#cmYasPanel .hd button{margin-left:auto;background:transparent;" +
    "border:0;color:#f7f1e6;font-size:22px;cursor:pointer;line-height:1}" +
    "#cmYasBody{flex:1;overflow:auto;padding:14px 14px 8px;" +
    "display:flex;flex-direction:column;gap:10px;font:15px/1.45 " +
    "system-ui,-apple-system,sans-serif}" +
    "#cmYasBody .msg{max-width:88%;padding:10px 12px;border-radius:14px;" +
    "white-space:pre-wrap}" +
    "#cmYasBody .bot{align-self:flex-start;background:#fff;" +
    "border:1px solid rgba(44,38,32,.08)}" +
    "#cmYasBody .user{align-self:flex-end;background:#e8d7b0}" +
    "#cmYasBody .note{align-self:flex-start;font-size:.85rem;opacity:.85}" +
    "#cmYasBody .wa{align-self:flex-start;display:inline-block;" +
    "margin-top:2px;padding:8px 12px;border-radius:999px;" +
    "background:var(--gold-3,#b8954a);color:#1c1712;text-decoration:none;" +
    "font:600 13px/1.2 system-ui,sans-serif}" +
    "#cmYasBody .typing{align-self:flex-start;display:flex;gap:5px;" +
    "padding:10px 14px}" +
    "#cmYasBody .typing span{width:6px;height:6px;border-radius:50%;" +
    "background:#b8954a;animation:cmYasPulse 1s infinite}" +
    "#cmYasBody .typing span:nth-child(2){animation-delay:.15s}" +
    "#cmYasBody .typing span:nth-child(3){animation-delay:.3s}" +
    "@keyframes cmYasPulse{0%,80%,100%{opacity:.25}40%{opacity:1}}" +
    "#cmYasFoot{display:flex;gap:8px;padding:10px 12px 12px;" +
    "border-top:1px solid rgba(44,38,32,.08);background:#f3ead8}" +
    "#cmYasFoot textarea{flex:1;resize:none;min-height:40px;max-height:90px;" +
    "border:1px solid rgba(44,38,32,.15);border-radius:12px;" +
    "padding:10px 12px;font:15px/1.4 system-ui,sans-serif;" +
    "background:#fff;color:#2c2620}" +
    "#cmYasFoot button{width:42px;height:42px;border:0;border-radius:12px;" +
    "background:#2c2620;color:#f7f1e6;cursor:pointer;font-size:18px}" +
    "#cmYasFoot button:disabled{opacity:.45;cursor:default}";
  document.head.appendChild(style);

  var fab = document.createElement("button");
  fab.id = "cmYasFab";
  fab.type = "button";
  fab.setAttribute("aria-label", "Ouvrir le chat Yasmine");
  fab.innerHTML = '<span class="dot" aria-hidden="true"></span>Yasmine';
  document.body.appendChild(fab);

  var panel = document.createElement("div");
  panel.id = "cmYasPanel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Chat Yasmine");
  panel.innerHTML =
    '<div class="hd">' +
    "<div><h3>Yasmine</h3><p>Concierge Coins Marocain</p></div>" +
    '<button type="button" id="cmYasClose" aria-label="Fermer">×</button>' +
    "</div>" +
    '<div id="cmYasBody"></div>' +
    '<div id="cmYasFoot">' +
    '<textarea id="cmYasInput" rows="1" placeholder="Racontez-moi votre séjour…"></textarea>' +
    '<button type="button" id="cmYasSend" aria-label="Envoyer">↑</button>' +
    "</div>";
  document.body.appendChild(panel);

  var body = panel.querySelector("#cmYasBody");
  var input = panel.querySelector("#cmYasInput");
  var sendBtn = panel.querySelector("#cmYasSend");

  function scroll() {
    body.scrollTop = body.scrollHeight;
  }

  function bubble(role, text) {
    var el = document.createElement("div");
    el.className = "msg " + (role === "user" ? "user" : "bot");
    el.textContent = text;
    body.appendChild(el);
    scroll();
    return el;
  }

  function typing(on) {
    var t = body.querySelector(".typing");
    if (on && !t) {
      t = document.createElement("div");
      t.className = "typing";
      t.innerHTML = "<span></span><span></span><span></span>";
      body.appendChild(t);
      scroll();
    } else if (!on && t) {
      t.remove();
    }
  }

  function waLink(url, label) {
    var a = document.createElement("a");
    a.className = "wa";
    a.href = url || WA_FALLBACK;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = label || "Continuer sur WhatsApp →";
    body.appendChild(a);
    scroll();
  }

  function brokenReply(reply) {
    return /restauration|temporairement|unavailable|maintenance|stub/i.test(
      reply || ""
    );
  }

  function showBroken() {
    bubble(
      "assistant",
      "Le chat est indisponible pour le moment — écrivez-moi directement sur WhatsApp, je vous réponds."
    );
    waLink(WA_FALLBACK);
    if (input) input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;
  }

  function openPanel() {
    panel.classList.add("open");
    if (!openedOnce) {
      openedOnce = true;
      if (!body.querySelector(".msg")) {
        bubble(
          "assistant",
          "Bienvenue… Je suis Yasmine. Dites-moi ce qui vous amène à Marrakech — je compose avec vous."
        );
      }
    }
    try {
      input.focus();
    } catch (e) {}
  }

  function closePanel() {
    panel.classList.remove("open");
  }

  function postChat(userText) {
    if (sending) return;
    sending = true;
    typing(true);
    sendBtn.disabled = true;
    fetch(API, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: messages }),
    })
      .then(function (r) {
        return r.json().catch(function () {
          return {};
        });
      })
      .then(function (j) {
        typing(false);
        sendBtn.disabled = false;
        sending = false;
        var reply = (j && j.reply) || "";
        if (!j || j.ok === false || brokenReply(reply)) {
          showBroken();
          return;
        }
        bubble("assistant", reply);
        messages.push({ role: "assistant", content: reply });
        if (j.hot) {
          var note = document.createElement("div");
          note.className = "msg bot note";
          note.textContent = "Un membre de l’équipe a été prévenu.";
          body.appendChild(note);
          scroll();
        }
        if (j.offer_whatsapp && j.whatsapp_url) {
          waLink(j.whatsapp_url, "Continuer sur WhatsApp →");
        }
      })
      .catch(function () {
        typing(false);
        sendBtn.disabled = false;
        sending = false;
        bubble(
          "assistant",
          "Connexion difficile… Réessayez dans un instant, ou écrivez-moi sur WhatsApp."
        );
        waLink(WA_FALLBACK);
      });
  }

  function send(text) {
    var value = (text != null ? text : input.value || "").trim();
    if (!value || sending) return;
    input.value = "";
    input.style.height = "auto";
    bubble("user", value);
    messages.push({ role: "user", content: value });
    postChat(value);
  }

  fab.addEventListener("click", function () {
    if (panel.classList.contains("open")) closePanel();
    else openPanel();
  });
  panel.querySelector("#cmYasClose").addEventListener("click", closePanel);
  sendBtn.addEventListener("click", function () {
    send();
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendBtn.click();
    }
  });
  input.addEventListener("input", function () {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 90) + "px";
  });

  window.CoinsYasmine = {
    open: function (msg) {
      openPanel();
      if (msg && !messages.length) send(String(msg));
    },
    close: closePanel,
  };
})();
