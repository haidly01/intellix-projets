(function () {
  var titleEl = document.getElementById("cmFicheTitle");
  var pillsEl = document.getElementById("cmFichePills");
  var noteEl = document.getElementById("cmFicheNote");
  var galEl = document.getElementById("cmFicheGallery");
  var heroArt = document.getElementById("cmFicheHeroArt");
  var copyEl = document.getElementById("cmFicheCopy");
  var payEl = document.getElementById("cmFichePay");
  var canonEl = document.getElementById("cmFicheCanon");
  var relatedEl = document.getElementById("cmFicheRelated");
  if (!titleEl || !payEl) return;

  var code = (location.pathname.replace(/\/+$/, "").split("/").pop() || "").trim();

  var LANGS = {
    fr: "Français",
    en: "Anglais",
    es: "Espagnol",
    de: "Allemand",
    it: "Italien",
    ar: "Arabe",
    pt: "Portugais",
    nl: "Néerlandais",
    ja: "Japonais",
    zh: "Chinois",
    zh_cn: "Chinois",
    zh_tw: "Chinois",
    ru: "Russe",
    pl: "Polonais",
    tr: "Turc",
    ko: "Coréen",
    sv: "Suédois",
    da: "Danois",
    no: "Norvégien",
    fi: "Finnois",
    el: "Grec",
    he: "Hébreu",
    cs: "Tchèque",
    hu: "Hongrois",
    ro: "Roumain",
    uk: "Ukrainien",
    th: "Thaï",
    vi: "Vietnamien",
    id: "Indonésien",
    ms: "Malais",
    ca: "Catalan",
    hi: "Hindi",
  };

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function money(n) {
    if (n == null || n === "") return "";
    var v = Number(n);
    if (!isFinite(v)) return "";
    return (
      "dès " +
      v.toLocaleString("fr-FR", {
        minimumFractionDigits: v % 1 ? 2 : 0,
        maximumFractionDigits: 2,
      }) +
      " €"
    );
  }

  function minutesLabel(n) {
    var m = Number(n);
    if (!isFinite(m) || m <= 0) return "";
    if (m >= 1440 && m % 1440 === 0) {
      var d = m / 1440;
      return d + (d > 1 ? " jours" : " jour");
    }
    if (m < 60) return Math.round(m) + " min";
    var h = Math.floor(m / 60);
    var rest = Math.round(m % 60);
    if (!rest) return h + " h";
    return h + " h " + rest;
  }

  function durationLabel(p) {
    var fixed = minutesLabel(p.duration_min);
    if (fixed) return fixed;
    var from = minutesLabel(p.duration_from);
    var to = minutesLabel(p.duration_to);
    if (from && to && from !== to) return from + " – " + to;
    return from || to || "";
  }

  function langLabel(codeLang) {
    var k = String(codeLang || "").toLowerCase().replace("-", "_");
    return LANGS[k] || String(codeLang || "").toUpperCase();
  }

  function productUrls(p) {
    var urls = p.images && p.images.length ? p.images.slice() : [];
    if (!urls.length && p.image) urls.push(p.image);
    return urls;
  }

  function setMeta(title, desc) {
    document.title = title + " | Coins Marocain";
    var md = document.querySelector('meta[name="description"]');
    if (md) md.setAttribute("content", desc);
    var ogt = document.querySelector('meta[property="og:title"]');
    if (ogt) ogt.setAttribute("content", title);
    var ogd = document.querySelector('meta[property="og:description"]');
    if (ogd) ogd.setAttribute("content", desc);
    if (canonEl) {
      canonEl.setAttribute(
        "href",
        "https://coinsmarocain.com/activites/essaouira/" + encodeURIComponent(code)
      );
    }
  }

  function heroAndStrip(p) {
    var urls = productUrls(p);
    if (heroArt && urls[0]) {
      heroArt.style.backgroundImage = 'url("' + urls[0].replace(/"/g, "") + '")';
    }
    if (!galEl) return;
    if (urls.length < 2) {
      galEl.hidden = true;
      galEl.innerHTML = "";
      return;
    }
    var extra = urls.length > 5 ? urls.length - 5 : 0;
    var show = urls.slice(0, 5);
    galEl.hidden = false;
    galEl.innerHTML = show
      .map(function (u, i) {
        var more =
          i === show.length - 1 && extra > 0
            ? '<span class="cm-act-photo-more">+' + extra + "</span>"
            : "";
        return (
          '<span class="cm-act-photo"><img src="' +
          esc(u) +
          '" alt="" width="220" height="220" loading="lazy">' +
          more +
          "</span>"
        );
      })
      .join("");
  }

  function pills(p) {
    if (!pillsEl) return;
    var items = [];
    var dur = durationLabel(p);
    if (dur) items.push({ k: "Durée", v: dur });
    var langs = (p.languages || []).map(langLabel).filter(Boolean);
    if (langs.length) items.push({ k: "Langues", v: langs.join(", ") });
    var rating = p.rating != null && p.rating !== "" ? Number(p.rating) : NaN;
    var reviews = p.reviews != null && p.reviews !== "" ? Number(p.reviews) : NaN;
    if (isFinite(rating) && rating > 0) {
      var avis = rating.toLocaleString("fr-FR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      }) + " / 5";
      if (isFinite(reviews) && reviews > 0) avis += " · " + reviews + " avis";
      items.push({ k: "Avis", v: avis });
    } else if (isFinite(reviews) && reviews > 0) {
      items.push({ k: "Avis", v: reviews + " avis" });
    }
    var price = money(p.price);
    if (price) items.push({ k: "Prix", v: price });
    if (p.free_cancel) items.push({ k: "Annulation", v: "gratuite" });
    pillsEl.innerHTML = items
      .map(function (it) {
        return "<li><span>" + esc(it.k) + "</span><b>" + esc(it.v) + "</b></li>";
      })
      .join("");
    pillsEl.hidden = !items.length;
    if (noteEl) {
      noteEl.hidden = !(isFinite(rating) && rating > 0) && !(isFinite(reviews) && reviews > 0);
    }
  }

  Promise.all([
    fetch("/assets/data/activites-essaouira.json").then(function (r) {
      if (!r.ok) throw new Error("catalogue");
      return r.json();
    }),
    fetch("/assets/data/activites-maroc.rewritten.json?v=cm-hub11")
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .catch(function () {
        return {};
      }),
  ])
    .then(function (pair) {
      var products = (pair[0] && pair[0].products) || [];
      var rew = ((pair[1] && pair[1].products) || {})[code] || null;
      var p = products.filter(function (x) {
        return x.code === code;
      })[0];
      if (!p) {
        titleEl.textContent = "Cette expérience n’est pas au catalogue Essaouira.";
        setMeta(
          "Expérience à Essaouira",
          "Expérience à Essaouira — Coins Marocain. Paiement sur Viator."
        );
        payEl.hidden = true;
        return;
      }

      var h1 = (rew && rew.titre_reecrit) || p.title || "Expérience à Essaouira";
      titleEl.textContent = h1;
      heroAndStrip(p);
      pills(p);

      /* Texte long : sidecar seulement. Jamais p.desc / itinerary / avis Viator. */
      var longTxt =
        (rew && (rew.description_longue_reecrite || rew.description_courte_reecrite)) || "";
      if (copyEl) {
        if (longTxt) {
          copyEl.hidden = false;
          copyEl.innerHTML = "<p>" + esc(longTxt) + "</p>";
        } else {
          copyEl.hidden = true;
          copyEl.innerHTML = "";
        }
      }

      var metaDesc =
        rew && rew.description_courte_reecrite
          ? rew.description_courte_reecrite
          : "Expérience à Essaouira — Coins Marocain. Paiement sur Viator.";
      setMeta(h1, metaDesc);
      payEl.href = p.url || "#";
      if (relatedEl) {
        var rest = products.filter(function (x) {
          return x.code && x.code !== code;
        }).slice(0, 4);
        var cards = rest
          .map(function (sib) {
            var t =
              (pair[1] &&
                pair[1].products &&
                pair[1].products[sib.code] &&
                pair[1].products[sib.code].titre_reecrit) ||
              sib.title ||
              sib.code;
            return (
              '<li><a href="/activites/essaouira/' +
              encodeURIComponent(sib.code) +
              '">' +
              esc(t) +
              "</a></li>"
            );
          })
          .join("");
        relatedEl.hidden = !cards;
        relatedEl.innerHTML =
          "<h2>Autres expériences à Essaouira</h2><ul>" +
          cards +
          '</ul><p class="cm-act-related-doors"><a href="/activites/essaouira">Toutes les expériences à Essaouira</a> · <a href="/activites/marrakech">Marrakech</a> · <a href="/activites/agadir">Agadir</a></p>';
      }
    })
    .catch(function () {
      titleEl.textContent = "Fiche temporairement indisponible.";
      payEl.hidden = true;
    });
})();
