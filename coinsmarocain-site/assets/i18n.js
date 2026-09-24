/* Coins Marocain — true bilingual: URL switcher + opt-in banner (no title rewrite) */
(function () {
  var STORE = "lang_pref";
  var LEGACY = "cm_lang";

  var SHARED = {
    fr: {
      nav_home: "Accueil",
      nav_blog: "Blogue",
      nav_partners: "Partenaires",
      nav_carnet: "Carnet du Voyageur",
      nav_open: "Ouvrir le menu",
      nav_close: "Fermer le menu",
      foot_privacy: "Politique de confidentialité et cookies",
      foot_affiliation: "Affiliation",
      foot_wedding_planner: "Wedding planner",
      foot_journee_piscine: "Journée piscine",
      foot_agence_voyage: "Agence de voyage",
      banner_text: "This page is available in English. Switch language?",
      banner_go: "English",
      banner_stay: "Stay in French"
    },
    en: {
      nav_home: "Home",
      nav_blog: "Blog",
      nav_partners: "Partners",
      nav_carnet: "Traveler's Notebook",
      nav_open: "Open menu",
      nav_close: "Close menu",
      foot_privacy: "Privacy & cookie policy",
      foot_affiliation: "Affiliation",
      foot_wedding_planner: "Wedding planner",
      foot_journee_piscine: "Pool day",
      foot_agence_voyage: "Travel agency",
      banner_text: "Cette page est aussi disponible en français.",
      banner_go: "Français",
      banner_stay: "Stay in English"
    }
  };

  function normPath(p) {
    if (!p) return "/";
    p = p.split("?")[0].split("#")[0];
    if (p.length > 1 && p.endsWith("/")) p = p.slice(0, -1);
    if (p === "/index.html") return "/";
    if (p.endsWith(".html")) p = p.slice(0, -5);
    return p || "/";
  }

  function getPref() {
    try {
      var v = localStorage.getItem(STORE) || localStorage.getItem(LEGACY);
      if (v === "en" || v === "fr") return v;
    } catch (e) {}
    return "";
  }

  function setPref(lang) {
    try {
      localStorage.setItem(STORE, lang);
      localStorage.setItem(LEGACY, lang);
    } catch (e) {}
  }

  function pageLang() {
    var htmlLang = (document.documentElement.getAttribute("lang") || "fr").toLowerCase();
    if (htmlLang.indexOf("en") === 0) return "en";
    var path = normPath(location.pathname);
    if (path === "/en" || path.indexOf("/en/") === 0) return "en";
    return "fr";
  }

  function twinUrl(fromLang) {
    var map = window.CM_LANG_MAP || { frToEn: {}, enToFr: {} };
    var path = normPath(location.pathname);
    if (fromLang === "fr") {
      return map.frToEn[path] || map.frToEn[path + "/"] || "/en/";
    }
    return map.enToFr[path] || map.enToFr[path + "/"] || "/";
  }

  function ensureSwitcher() {
    var header = document.querySelector(".header-inner");
    if (!header) return;
    var box = header.querySelector(".cm-lang-switch");
    var lang = pageLang();
    var twin = twinUrl(lang);
    if (!box) {
      box = document.createElement("div");
      box.className = "cm-lang-switch";
      box.setAttribute("role", "group");
      box.setAttribute("aria-label", "Language");
      var actions = header.querySelector(".header-actions");
      if (actions) actions.insertBefore(box, actions.firstChild);
      else header.appendChild(box);
    }
    box.innerHTML =
      '<a href="' +
      (lang === "fr" ? location.pathname : twin) +
      '" hreflang="fr" class="' +
      (lang === "fr" ? "on" : "") +
      '" data-lang-pref="fr">FR</a>' +
      '<span aria-hidden="true">|</span>' +
      '<a href="' +
      (lang === "en" ? location.pathname : twin) +
      '" hreflang="en" class="' +
      (lang === "en" ? "on" : "") +
      '" data-lang-pref="en">EN</a>';
    if (box.getAttribute("data-bound") === "1") return;
    box.setAttribute("data-bound", "1");
    box.addEventListener("click", function (e) {
      var a = e.target.closest("[data-lang-pref]");
      if (!a) return;
      setPref(a.getAttribute("data-lang-pref"));
    });
  }

  function applyChromeDict() {
    var lang = pageLang();
    var dict = SHARED[lang] || SHARED.fr;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      var key = el.getAttribute("data-i18n");
      if (dict[key] != null) el.textContent = dict[key];
    });
    document.querySelectorAll("[data-i18n-aria]").forEach(function (el) {
      var key = el.getAttribute("data-i18n-aria");
      if (dict[key] != null) el.setAttribute("aria-label", dict[key]);
    });
  }

  function showBannerIfNeeded() {
    if (getPref()) return;
    var navLang = (navigator.language || navigator.userLanguage || "").toLowerCase();
    var wantsEn = navLang.indexOf("en") === 0;
    var lang = pageLang();
    if (!wantsEn || lang === "en") {
      if (!getPref()) setPref(lang);
      return;
    }
    if (document.querySelector(".cm-lang-banner")) return;
    var dict = SHARED.fr;
    var twin = twinUrl("fr");
    var bar = document.createElement("div");
    bar.className = "cm-lang-banner";
    bar.innerHTML =
      '<div class="wrap">' +
      "<p>" +
      dict.banner_text +
      "</p>" +
      '<div class="cm-lang-actions">' +
      '<a class="cm-lang-go" href="' +
      twin +
      '">' +
      dict.banner_go +
      "</a>" +
      '<button type="button" class="cm-lang-stay">' +
      dict.banner_stay +
      "</button>" +
      "</div></div>";
    document.body.appendChild(bar);
    requestAnimationFrame(function () {
      bar.classList.add("on");
    });
    bar.querySelector(".cm-lang-go").addEventListener("click", function () {
      setPref("en");
    });
    bar.querySelector(".cm-lang-stay").addEventListener("click", function () {
      setPref("fr");
      bar.classList.remove("on");
      setTimeout(function () {
        bar.remove();
      }, 280);
    });
  }

  function init() {
    ensureSwitcher();
    applyChromeDict();
    showBannerIfNeeded();
    if (window.CoinsCookies && window.CoinsCookies.refresh) window.CoinsCookies.refresh();
  }

  window.CoinsI18n = {
    pageLang: pageLang,
    twinUrl: twinUrl,
    setPref: setPref,
    getPref: getPref
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
