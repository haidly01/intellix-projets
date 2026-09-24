/* Coins Marocain — bandeau cookies par catégories + consentement contact Yasmine / WhatsApp */
(function () {
  var KEY = "cm_cookie_consent";
  var CONTACT_KEY = "cm_contact_consent";
  var GA_ID = "G-Q6Q7711QDJ";
  var META_PIXEL_ID = "1727159081667962";
  /* Test Events uniquement via ?test_event_code= / ?meta_test= — jamais en prod. */

  function isEn() {
    var lang = (document.documentElement.getAttribute("lang") || "fr").toLowerCase();
    var path = location.pathname || "";
    return lang.indexOf("en") === 0 || path.indexOf("/en/") === 0;
  }

  function t(key) {
    var dict = {
      fr: {
        title: "Cookies",
        msg: "Les cookies nécessaires font fonctionner le site. Audience et marketing restent optionnels.",
        policy: "Politique de confidentialité et cookies",
        necessary: "Nécessaires — toujours actifs",
        analytics: "Mesure d’audience (Google Analytics)",
        marketing: "Marketing (Meta Pixel)",
        refuse: "Tout refuser",
        save: "Enregistrer",
        all: "Tout accepter",
        gateTitle: "Avant d’écrire à Yasmine",
        gateMsg: "Le chat et WhatsApp collectent votre nom et votre numéro. Confirmez que vous acceptez d’être contacté au sujet de cette demande.",
        gateCheck: "J’accepte d’être contacté par Yasmine au sujet de cette demande.",
        gateGo: "Continuer",
        gateCancel: "Annuler",
      },
      en: {
        title: "Cookies",
        msg: "Necessary cookies keep the site working. Analytics and marketing stay optional.",
        policy: "Privacy and cookie policy",
        necessary: "Necessary — always on",
        analytics: "Audience measurement (Google Analytics)",
        marketing: "Marketing (Meta Pixel)",
        refuse: "Reject all",
        save: "Save",
        all: "Accept all",
        gateTitle: "Before writing to Yasmine",
        gateMsg: "Chat and WhatsApp collect your name and number. Confirm you agree to be contacted about this request.",
        gateCheck: "I agree to be contacted by Yasmine about this request.",
        gateGo: "Continue",
        gateCancel: "Cancel",
      },
    };
    return (isEn() ? dict.en : dict.fr)[key];
  }

  function readChoice() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return null;
      if (raw === "accepted") return { necessary: true, analytics: true, marketing: true };
      if (raw === "refused") return { necessary: true, analytics: false, marketing: false };
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function saveChoice(choice) {
    var payload = {
      necessary: true,
      analytics: !!choice.analytics,
      marketing: !!choice.marketing,
      at: new Date().toISOString(),
    };
    try {
      localStorage.setItem(KEY, JSON.stringify(payload));
    } catch (e) {}
    return payload;
  }

  function metaTestCode() {
    try {
      var q = new URLSearchParams(location.search || "");
      return (q.get("test_event_code") || q.get("meta_test") || "").trim();
    } catch (e) {
      return "";
    }
  }

  function metaTrack(eventName, payload) {
    if (typeof window.fbq !== "function") return false;
    if (!eventName || eventName === "Purchase" || eventName === "AddToCart") return false;
    var data = payload || {};
    var testCode = metaTestCode();
    if (testCode) window.fbq("track", eventName, data, { testEventCode: testCode });
    else window.fbq("track", eventName, data);
    return true;
  }

  function notifyMetaReady() {
    try {
      window.dispatchEvent(new Event("cm-meta-ready"));
    } catch (e) {}
  }

  function loadGA() {
    if (window.__cmGaLoaded) return;
    window.__cmGaLoaded = true;
    window.dataLayer = window.dataLayer || [];
    window.gtag = function () { window.dataLayer.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", GA_ID);
    var s = document.createElement("script");
    s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id=" + GA_ID;
    document.head.appendChild(s);
  }

  function loadMetaPixel() {
    if (window.__cmMetaLoaded) return;
    window.__cmMetaLoaded = true;
    var f = window;
    var b = document;
    var testCode = metaTestCode();
    if (f.fbq) {
      f.fbq("init", META_PIXEL_ID);
      if (testCode) f.fbq("track", "PageView", {}, { testEventCode: testCode });
      else f.fbq("track", "PageView");
      notifyMetaReady();
      return;
    }
    var n = f.fbq = function () {
      n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
    };
    if (!f._fbq) f._fbq = n;
    n.push = n;
    n.loaded = true;
    n.version = "2.0";
    n.queue = [];
    var tEl = b.createElement("script");
    tEl.async = true;
    tEl.src = "https://connect.facebook.net/en_US/fbevents.js";
    var first = b.getElementsByTagName("script")[0];
    if (first && first.parentNode) first.parentNode.insertBefore(tEl, first);
    else b.head.appendChild(tEl);
    f.fbq("init", META_PIXEL_ID);
    if (testCode) f.fbq("track", "PageView", {}, { testEventCode: testCode });
    else f.fbq("track", "PageView");
    notifyMetaReady();
  }

  function applyChoice(choice) {
    hideBanner();
    if (choice && choice.analytics) loadGA();
    if (choice && choice.marketing) loadMetaPixel();
  }

  function hideBanner() {
    var el = document.getElementById("cmCookie");
    if (el) el.remove();
  }

  function privacyHref() {
    return "/confidentialite";
  }

  function showBanner() {
    if (document.getElementById("cmCookie")) return;
    var el = document.createElement("div");
    el.id = "cmCookie";
    el.className = "cm-cookie on";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-label", t("title"));
    el.innerHTML =
      "<h2>" + t("title") + "</h2>" +
      "<p>" + t("msg") + ' <a href="' + privacyHref() + '">' + t("policy") + "</a>.</p>" +
      '<div class="cm-cookie-cats">' +
      '<label><input type="checkbox" checked disabled> ' + t("necessary") + "</label>" +
      '<label><input type="checkbox" id="cmCookieAnalytics"> ' + t("analytics") + "</label>" +
      '<label><input type="checkbox" id="cmCookieMarketing"> ' + t("marketing") + "</label>" +
      "</div>" +
      '<div class="cm-cookie-actions">' +
      '<button type="button" class="cm-cookie-refuse" id="cmCookieRefuse">' + t("refuse") + "</button>" +
      '<button type="button" class="cm-cookie-save" id="cmCookieSave">' + t("save") + "</button>" +
      '<button type="button" class="cm-cookie-btn" id="cmCookieAll">' + t("all") + "</button>" +
      "</div>";
    document.body.appendChild(el);
    document.getElementById("cmCookieRefuse").addEventListener("click", function () {
      applyChoice(saveChoice({ analytics: false, marketing: false }));
    });
    document.getElementById("cmCookieSave").addEventListener("click", function () {
      applyChoice(saveChoice({
        analytics: document.getElementById("cmCookieAnalytics").checked,
        marketing: document.getElementById("cmCookieMarketing").checked,
      }));
    });
    document.getElementById("cmCookieAll").addEventListener("click", function () {
      applyChoice(saveChoice({ analytics: true, marketing: true }));
    });
  }

  function hasContactConsent() {
    try { return !!sessionStorage.getItem(CONTACT_KEY); } catch (e) { return false; }
  }

  function setContactConsent() {
    try { sessionStorage.setItem(CONTACT_KEY, new Date().toISOString()); } catch (e) {}
  }

  function isContactTrigger(el) {
    if (!el) return false;
    if (el.closest && el.closest("[data-open-yasmine]")) return true;
    var a = el.closest ? el.closest("a[href]") : null;
    if (!a) return false;
    var href = a.getAttribute("href") || "";
    return href.indexOf("wa.me") !== -1 || href.indexOf("whatsapp.com") !== -1;
  }

  function resumeTrigger(target) {
    var yasmine = target.closest("[data-open-yasmine]");
    if (yasmine) {
      yasmine.click();
      return;
    }
    var a = target.closest("a[href]");
    if (a) window.open(a.href, a.target || "_blank", "noopener");
  }

  function showContactGate(target) {
    if (document.getElementById("cmContactGate")) return;
    var wrap = document.createElement("div");
    wrap.id = "cmContactGate";
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-modal", "true");
    wrap.innerHTML =
      '<div class="cm-gate">' +
      "<h2>" + t("gateTitle") + "</h2>" +
      "<p>" + t("gateMsg") + "</p>" +
      '<label><input type="checkbox" id="cmGateCheck"> ' + t("gateCheck") + "</label>" +
      '<div class="cm-cookie-actions">' +
      '<button type="button" class="cm-cookie-refuse" id="cmGateCancel">' + t("gateCancel") + "</button>" +
      '<button type="button" class="cm-cookie-btn" id="cmGateGo" disabled>' + t("gateGo") + "</button>" +
      "</div></div>";
    document.body.appendChild(wrap);
    var box = document.getElementById("cmGateCheck");
    var go = document.getElementById("cmGateGo");
    box.addEventListener("change", function () {
      go.disabled = !box.checked;
    });
    document.getElementById("cmGateCancel").addEventListener("click", function () {
      wrap.remove();
    });
    go.addEventListener("click", function () {
      if (!box.checked) return;
      setContactConsent();
      wrap.remove();
      resumeTrigger(target);
    });
  }

  document.addEventListener("click", function (e) {
    if (!isContactTrigger(e.target)) return;
    if (hasContactConsent()) return;
    if (document.getElementById("cmContactGate")) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    e.preventDefault();
    e.stopPropagation();
    showContactGate(e.target);
  }, true);

  window.CoinsCookies = {
    reopen: function () {
      try { localStorage.removeItem(KEY); } catch (e) {}
      hideBanner();
      showBanner();
    },
    loadGAIfConsented: function () {
      var c = readChoice();
      if (c && c.analytics) loadGA();
    },
    loadMetaIfConsented: function () {
      var c = readChoice();
      if (c && c.marketing) loadMetaPixel();
    },
    pixelId: META_PIXEL_ID,
    track: metaTrack,
  };

  function init() {
    var choice = readChoice();
    if (choice) applyChoice(choice);
    else showBanner();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
