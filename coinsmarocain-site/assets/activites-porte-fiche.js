(function () {
  var titleEl = document.getElementById("cmFicheTitle");
  var pillsEl = document.getElementById("cmFichePills");
  var noteEl = document.getElementById("cmFicheNote");
  var galEl = document.getElementById("cmFicheGallery");
  var copyEl = document.getElementById("cmFicheCopy");
  var payEl = document.getElementById("cmFichePay");
  var canonEl = document.getElementById("cmFicheCanon");
  if (!titleEl || !payEl) return;

  var relatedEl = document.getElementById("cmFicheRelated");
  var door = (document.body.getAttribute("data-act-door") || "").trim();
  var label = (document.body.getAttribute("data-act-label") || door || "cette porte").trim();
  var code = (location.pathname.replace(/\/+$/, "").split("/").pop() || "").trim();
  try {
    code = decodeURIComponent(code);
  } catch (e) {}
  if (!door || !code) return;
  var isEn = /^\/en(\/|$)/.test(location.pathname || "/");
  var prefix = isEn ? "/en/activites/" : "/activites/";

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
      (isEn ? "from " : "dès ") +
      v.toLocaleString(isEn ? "en-GB" : "fr-FR", {
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
      if (isEn) return d + (d > 1 ? " days" : " day");
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
        "https://coinsmarocain.com" +
          prefix +
          encodeURIComponent(door) +
          "/" +
          encodeURIComponent(code)
      );
    }
  }

  var SISTER = {
    marrakech: [
      ["essaouira", "Essaouira"],
      ["agadir", "Agadir"],
    ],
    essaouira: [
      ["marrakech", "Marrakech"],
      ["agadir", "Agadir"],
    ],
    agadir: [
      ["marrakech", "Marrakech"],
      ["essaouira", "Essaouira"],
    ],
    rabat: [
      ["casablanca", "Casablanca"],
      ["fes", "Fès"],
    ],
    casablanca: [
      ["rabat", "Rabat"],
      ["marrakech", "Marrakech"],
    ],
    fes: [
      ["chefchaouen", "Chefchaouen"],
      ["rabat", "Rabat"],
    ],
    chefchaouen: [
      ["fes", "Fès"],
      ["tanger", "Tanger"],
    ],
    tanger: [
      ["chefchaouen", "Chefchaouen"],
      ["rabat", "Rabat"],
    ],
    desert: [
      ["marrakech", "Marrakech"],
      ["fes", "Fès"],
    ],
  };

  function pickRelated(items, current, n) {
    var rest = items.filter(function (p) {
      return p.code && p.code !== current;
    });
    var picked = [];
    var used = {};
    function stem(t) {
      return String(t || "")
        .toLowerCase()
        .replace(/[^a-zàâäéèêëïîôùûüç0-9]+/gi, " ")
        .trim()
        .split(/\s+/)
        .slice(0, 3)
        .join(" ");
    }
    rest.forEach(function (p) {
      if (picked.length >= n) return;
      var s = stem(p.title);
      if (s && used[s]) return;
      if (s) used[s] = 1;
      picked.push(p);
    });
    rest.forEach(function (p) {
      if (picked.length >= n) return;
      if (picked.indexOf(p) < 0) picked.push(p);
    });
    return picked;
  }

  function paintRelated(products, rewMap) {
    if (!relatedEl) return;
    var pool = (products || []).slice(0, 18);
    var sibs = pickRelated(pool, code, 4);
    var sisters = SISTER[door] || [];
    if (!sibs.length && !sisters.length) {
      relatedEl.hidden = true;
      relatedEl.innerHTML = "";
      return;
    }
    var cards = sibs
      .map(function (p) {
        var rec = rewMap && rewMap[p.code];
        var title = isEn
          ? (rec && (rec.title_en || rec.titre_reecrit)) || p.title || p.code
          : (rec && rec.titre_reecrit) || p.title || p.code;
        var href = prefix + encodeURIComponent(door) + "/" + encodeURIComponent(p.code);
        return (
          '<li><a href="' +
          href +
          '">' +
          esc(title) +
          "</a></li>"
        );
      })
      .join("");
    var more = sisters
      .map(function (pair) {
        return (
          '<a href="' +
          prefix +
          encodeURIComponent(pair[0]) +
          '">' +
          esc(pair[1]) +
          "</a>"
        );
      })
      .join(" · ");
    relatedEl.hidden = false;
    relatedEl.innerHTML =
      "<h2>" +
      (isEn ? "Also in " + label : "Autres expériences à " + label) +
      "</h2><ul>" +
      cards +
      "</ul><p class=\"cm-act-related-doors\"><a href=\"" +
      prefix +
      encodeURIComponent(door) +
      "\">" +
      (isEn ? "All " + label + " experiences" : "Toutes les expériences à " + label) +
      "</a>" +
      (more ? " · " + more : "") +
      "</p>";
  }

  function hashStr(s) {
    var h = 0;
    var i;
    s = String(s || "");
    for (i = 0; i < s.length; i++) h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
    return Math.abs(h);
  }

  function titleBlob(p) {
    return String((p && p.title) || "").toLowerCase();
  }

  function detectPlace(p) {
    var t = titleBlob(p);
    if (/agafay/.test(t)) return { fr: "Agafay", en: "Agafay", loc: "le plateau d'Agafay, à 40 minutes de Marrakech" };
    if (/ourika|setti fatma/.test(t)) return { fr: "l'Ourika", en: "Ourika", loc: "la vallée de l'Ourika, au pied de l'Atlas" };
    if (/ouzoud/.test(t)) return { fr: "Ouzoud", en: "Ouzoud", loc: "les cascades d'Ouzoud" };
    if (/imlil|toubkal/.test(t)) return { fr: "Imlil", en: "Imlil", loc: "Imlil et les sentiers sous le Toubkal" };
    if (/essaouira/.test(t)) return { fr: "Essaouira", en: "Essaouira", loc: "Essaouira, vent et remparts" };
    if (/hammam/.test(t)) return { fr: "un hammam", en: "a hammam", loc: "un hammam à Marrakech" };
    if (/palmeraie/.test(t)) return { fr: "la palmeraie", en: "the Palmeraie", loc: "la palmeraie aux portes de Marrakech" };
    if (/médina|medina|souk|jemaa|jamaa/.test(t)) return { fr: "la médina", en: "the medina", loc: "la médina de Marrakech" };
    if (/cuisine|cooking|tajine|tagine/.test(t)) return { fr: "un atelier cuisine", en: "a cooking class", loc: "un atelier de cuisine marocaine" };
    if (/montgolfi|balloon/.test(t)) return { fr: "les airs au-dessus de Marrakech", en: "the skies over Marrakech", loc: "un décollage près de Marrakech" };
    if (/merzouga|erg chebbi/.test(t)) return { fr: "Merzouga", en: "Merzouga", loc: "les dunes de Merzouga" };
    return { fr: label, en: label, loc: label };
  }

  function detectBeats(p) {
    var t = titleBlob(p);
    var beats = [];
    if (/quad|buggy/.test(t)) beats.push(isEn ? "quad" : "quad");
    if (/chameau|camel/.test(t)) beats.push(isEn ? "camel" : "chameau");
    if (/dîner|diner|dinner|spectacle/.test(t)) beats.push(isEn ? "dinner" : "dîner");
    if (/sunset|coucher/.test(t)) beats.push(isEn ? "sunset" : "sunset");
    if (/nuit|overnight|night|camp/.test(t)) beats.push(isEn ? "night" : "nuit");
    if (/piscine|pool|day pass/.test(t)) beats.push(isEn ? "pool" : "piscine");
    if (/cascade|waterfall/.test(t)) beats.push(isEn ? "waterfalls" : "cascades");
    if (/randonn|hike|trekking/.test(t)) beats.push(isEn ? "walk" : "marche");
    if (/cheval|horse/.test(t)) beats.push(isEn ? "horse" : "cheval");
    return beats;
  }

  function looksCopiedTitle(title) {
    var t = String(title || "");
    if (!t) return true;
    if (/\b(Quad Bike|Camel Ride|Day Trip|Hot Air Balloon|Promenade et)\b/i.test(t)) return true;
    if (t.length > 88) return true;
    return false;
  }

  function composeTitle(p, place) {
    var beats = detectBeats(p);
    var loc = isEn ? place.en : place.fr;
    if (isEn) {
      if (beats.length) return loc + " — " + beats.slice(0, 3).join(", ");
      return "Time in " + loc;
    }
    if (beats.indexOf("sunset") !== -1 && beats.indexOf("dîner") !== -1) {
      return "Soirée à " + loc + " — " + beats.filter(function (b) { return b !== "sunset"; }).join(", ");
    }
    if (beats.length) {
      return loc.charAt(0).toUpperCase() + loc.slice(1) + " — " + beats.slice(0, 3).join(", ");
    }
    return "Une sortie à " + loc;
  }

  function composeCopy(p, place) {
    var beats = detectBeats(p);
    var dur = durationLabel(p);
    var variant = hashStr(p.code || p.title) % 3;
    if (isEn) {
      return [
        "This outing sits around " +
          place.en +
          " — close enough to Marrakech for a real half-day, far enough to change the air. Coins Marocain does not paste the operator brochure.",
        beats.length
          ? "What it actually involves: " + beats.join(", ") + ". Keep one or two strong moments rather than a stacked checklist."
          : "The day stays readable: a place, a duration, a transfer — not six forced shop stops.",
        "Listed duration: " +
          (dur || "set by the operator") +
          ". Prices are in euros (Viator currency). You pay on Viator.",
      ].join("\n\n");
    }
    var openings = [
      "On quitte Marrakech pour " + place.loc + ". Ce n'est pas un ramassage d'hôtel en hôtel : le format catalogue se réserve, le rythme reste le vôtre.",
      place.loc.charAt(0).toUpperCase() +
        place.loc.slice(1) +
        " se mérite par un créneau choisi — lumière, chaleur, fatigue du voyage — plutôt que par un départ figé pour tout le car.",
      "Coins Marocain raconte le lieu avant le listing. Ici : " + place.loc + ", pour un groupe qui veut voir quelque chose, pas enchaîner six arrêts boutique.",
    ];
    var mid = beats.length
      ? "Au programme, sans recopier la brochure : " +
        beats.join(", ") +
        ". Une ou deux activités fortes suffisent ; le reste est du remplissage."
      : "Le déroulé tient en une sortie lisible. Durée, transfert, et ce que vous voulez vraiment faire se calent avec Yasmine si le format catalogue ne suffit pas.";
    var end =
      "Durée indiquée : " +
      (dur || "selon le prestataire") +
      ". Les prix s'affichent en euros, devise Viator ; le paiement se fait chez eux. Annulation et langues suivent la fiche opérateur.";
    return [openings[variant], mid, end].join("\n\n");
  }

  function sidecarOk(rew) {
    if (!rew) return false;
    if (Number(rew.reecriture_version || rew.rewrite_version || 0) < 4) return false;
    var title = rew.titre_reecrit || rew.title_en;
    var body =
      rew.description_longue_reecrite ||
      rew.description_courte_reecrite ||
      rew.description_longue_en ||
      rew.description_courte_en;
    return !!(title && body);
  }

  function gallery(p) {
    var urls = (p.images && p.images.length ? p.images : []).slice(0, 12);
    if (!urls.length && p.image) urls.push(p.image);
    if (!galEl) return;
    galEl.className = "cm-act-gallery";
    if (urls.length === 1) galEl.classList.add("cm-act-gallery--one");
    else if (urls.length === 2) galEl.classList.add("cm-act-gallery--two");
    else if (urls.length) galEl.classList.add("cm-act-gallery--mosaic");
    galEl.innerHTML = urls
      .map(function (u) {
        return '<img src="' + esc(u) + '" alt="" loading="lazy">';
      })
      .join("");
  }

  function pills(p) {
    if (!pillsEl) return;
    var items = [];
    var dur = durationLabel(p);
    if (dur) items.push({ k: isEn ? "Duration" : "Durée", v: dur });
    var langs = (p.languages || []).map(langLabel).filter(Boolean);
    if (langs.length) items.push({ k: isEn ? "Languages" : "Langues", v: langs.join(", ") });
    var rating = p.rating != null && p.rating !== "" ? Number(p.rating) : NaN;
    var reviews = p.reviews != null && p.reviews !== "" ? Number(p.reviews) : NaN;
    if (isFinite(rating) && rating > 0) {
      var avis =
        rating.toLocaleString("fr-FR", {
          minimumFractionDigits: 1,
          maximumFractionDigits: 1,
        }) + " / 5";
      if (isFinite(reviews) && reviews > 0) avis += " · " + reviews + (isEn ? " reviews" : " avis");
      items.push({ k: isEn ? "Reviews" : "Avis", v: avis });
    } else if (isFinite(reviews) && reviews > 0) {
      items.push({ k: isEn ? "Reviews" : "Avis", v: reviews + (isEn ? " reviews" : " avis") });
    }
    var price = money(p.price);
    if (price) items.push({ k: isEn ? "Price" : "Prix", v: price });
    if (p.free_cancel) items.push({ k: isEn ? "Cancellation" : "Annulation", v: isEn ? "free" : "gratuite" });
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
    fetch("/assets/data/activites-" + encodeURIComponent(door) + ".json").then(function (r) {
      if (!r.ok) throw new Error("catalogue");
      return r.json();
    }),
    fetch("/assets/data/activites-maroc.rewritten.json?v=cm-titres2")
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .catch(function () {
        return {};
      }),
  ])
    .then(function (pair) {
      var rewMap = (pair[1] && pair[1].products) || {};
      var catalog = (pair[0] && pair[0].products) || [];
      var p = catalog.filter(function (x) {
        return String(x.code) === String(code);
      })[0];
      if (!p) {
        titleEl.textContent = isEn
          ? "This experience is not in the " + label + " catalogue."
          : "Cette expérience n’est pas au catalogue " + label + ".";
        setMeta(
          isEn ? "Experience in " + label : "Expérience à " + label,
          isEn
            ? "Experience in " + label + " — Coins Marocain. Pay on Viator."
            : "Expérience à " + label + " — Coins Marocain. Paiement sur Viator."
        );
        payEl.hidden = true;
        return;
      }

      var rew = rewMap[code] || null;
      var place = detectPlace(p);
      var useSidecar = sidecarOk(rew);
      var sidecarTitle = isEn
        ? (rew && (rew.title_en || rew.titre_reecrit)) || ""
        : (rew && rew.titre_reecrit) || "";
      var h1 = sidecarTitle;
      if (!h1 || looksCopiedTitle(h1)) h1 = composeTitle(p, place);

      titleEl.textContent = h1;
      gallery(p);
      pills(p);

      /* Sidecar réécrit si dispo ; sinon texte Coins. Jamais p.desc / itinéraire Viator. */
      var longTxt = "";
      if (useSidecar) {
        longTxt = isEn
          ? (rew.description_longue_en || rew.description_courte_en || "")
          : (rew.description_longue_reecrite || rew.description_courte_reecrite || "");
      }
      if (!longTxt) longTxt = composeCopy(p, place);
      if (copyEl) {
        copyEl.hidden = false;
        copyEl.innerHTML = longTxt
          .split(/\n\n+/)
          .map(function (para) {
            return "<p>" + esc(para.replace(/\n/g, " ").trim()) + "</p>";
          })
          .join("");
      }

      var metaDesc = (longTxt.split(/\n\n+/)[0] || "").slice(0, 160);
      setMeta(h1, metaDesc);
      payEl.hidden = false;
      payEl.href = p.url || "#";
      var relatedPool = catalog.filter(function (x) {
        if (x.code === p.code) return false;
        var a = detectPlace(x).fr;
        return a === place.fr;
      });
      if (relatedPool.length < 4) relatedPool = catalog;
      paintRelated(relatedPool, rewMap);
    })
    .catch(function () {
      titleEl.textContent = isEn ? "Page temporarily unavailable." : "Fiche temporairement indisponible.";
      payEl.hidden = true;
    });
})();
