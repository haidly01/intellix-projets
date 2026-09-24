(function () {
  var list = document.getElementById("cmActList");
  var more = document.getElementById("cmActMore");
  var note = document.getElementById("cmActFx");
  if (!list) return;

  var isEn = /^\/en(\/|$)/.test(location.pathname || "/");
  var pathBits = (location.pathname || "/")
    .replace(/^\/en(?=\/)/, "")
    .replace(/\/+$/, "")
    .split("/")
    .filter(Boolean);
  var slug = pathBits[pathBits.length - 1] || "";

  var SLUG_FILTERS = {
    "desert-agafay": { terms: ["agafay"], place: "Agafay", placeEn: "Agafay" },
    agafay: { terms: ["agafay"], place: "Agafay", placeEn: "Agafay" },
    "vallee-ourika": { terms: ["ourika", "setti fatma"], place: "l'Ourika", placeEn: "Ourika" },
    ourika: { terms: ["ourika", "setti fatma"], place: "l'Ourika", placeEn: "Ourika" },
    "cascades-ouzoud": { terms: ["ouzoud"], place: "Ouzoud", placeEn: "Ouzoud" },
    ouzoud: { terms: ["ouzoud"], place: "Ouzoud", placeEn: "Ouzoud" },
    "essaouira-journee": { terms: ["essaouira"], place: "Essaouira", placeEn: "Essaouira" },
    "imlil-randonnee": { terms: ["imlil", "toubkal"], place: "Imlil", placeEn: "Imlil" },
    imlil: { terms: ["imlil", "toubkal"], place: "Imlil", placeEn: "Imlil" },
    "visite-medina-nuit": {
      terms: ["médina", "medina", "souk", "jemaa", "jamaa"],
      place: "la médina",
      placeEn: "the medina",
    },
    "cours-cuisine-marocaine": {
      terms: ["cuisine", "cooking", "tajine", "tagine", "culinaire"],
      place: "la cuisine",
      placeEn: "cooking classes",
    },
    "hammam-traditionnel": { terms: ["hammam"], place: "le hammam", placeEn: "hammam" },
    hammam: { terms: ["hammam"], place: "le hammam", placeEn: "hammam" },
    "balade-cheval-palmeraie": {
      terms: ["palmeraie", "horseback", "horse riding", "à cheval", "a cheval"],
      place: "la palmeraie",
      placeEn: "the Palmeraie",
    },
  };

  function parseTerms(raw) {
    return String(raw || "")
      .split(",")
      .map(function (s) {
        return s.trim().toLowerCase();
      })
      .filter(Boolean);
  }

  var attrFilter = parseTerms(document.body.getAttribute("data-act-filter"));
  var meta = SLUG_FILTERS[slug] || null;
  var filterTerms = attrFilter.length ? attrFilter : meta ? meta.terms : [];

  var door = (document.body.getAttribute("data-act-door") || "").trim();
  if (!door && pathBits[0] === "activites" && pathBits[1] && pathBits[1] !== slug) {
    door = pathBits[1];
  }
  if (!door && meta) door = "marrakech";
  if (!door) return;

  var prefix = isEn ? "/en/activites/" : "/activites/";
  var PAGE = 18;
  var shown = 0;
  var products = [];

  function ensureCatalogStyle() {
    if (document.getElementById("cmActCatalogStyle")) return;
    var s = document.createElement("style");
    s.id = "cmActCatalogStyle";
    s.textContent =
      ".cm-act-viator-block{max-width:1100px;margin:28px auto 64px;padding:0 20px}" +
      ".cm-act-viator-block .eyebrow{margin:0 0 6px;letter-spacing:.14em;text-transform:uppercase;font-size:12px;color:#8a4f22}" +
      ".cm-act-viator-block h2{margin:0 0 4px;font-size:1.55rem;line-height:1.2}" +
      ".cm-act-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:18px;margin:22px 0 12px}" +
      ".cm-act-card{display:flex;flex-direction:column;overflow:hidden;border-radius:14px;border:1px solid #e6d9c0;background:#fffdf8;text-decoration:none;color:inherit}" +
      ".cm-act-card:hover{border-color:#c9a227;transform:translateY(-2px)}" +
      ".cm-act-card img{width:100%;height:168px;object-fit:cover;background:#efe4d0;display:block}" +
      ".cm-act-card .body{display:flex;flex-direction:column;gap:8px;padding:14px 16px 16px;flex:1}" +
      ".cm-act-card h3{margin:0;font-size:1.05rem;line-height:1.28;font-weight:600}" +
      ".cm-act-card .cm-act-meta{margin-top:auto;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:#8a4f22}" +
      ".cm-act-card .cm-act-go{font-size:13px;color:#8a4f22}" +
      ".cm-act-fx{margin:8px 0 0;font-size:12px;color:#6b5c4a}" +
      ".cm-act-more{appearance:none;margin:8px 0 0;padding:10px 16px;border-radius:999px;border:1px solid #e6d9c0;background:#fff9ef;color:#8a4f22;font:inherit;font-weight:500;cursor:pointer}";
    document.head.appendChild(s);
  }
  ensureCatalogStyle();

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

  function card(p) {
    var img = p.image
      ? '<img src="' + esc(p.image) + '" alt="" width="540" height="360" loading="lazy">'
      : "";
    var bits = [];
    var price = money(p.price);
    if (price) bits.push(price);
    if (p.rating) bits.push(Number(p.rating).toFixed(1) + "/5");
    if (p.reviews) bits.push(p.reviews + (isEn ? " reviews" : " avis"));
    return (
      '<a class="cm-act-card" href="' +
      prefix +
      encodeURIComponent(door) +
      "/" +
      encodeURIComponent(p.code) +
      '">' +
      img +
      '<div class="body"><h3>' +
      esc(p.title) +
      '</h3><div class="cm-act-meta">' +
      esc(bits.join(" · ")) +
      '</div><span class="cm-act-go">' +
      (isEn ? "See the page" : "Voir la fiche") +
      "</span></div></a>"
    );
  }

  function productUrls(p) {
    var urls = p.images && p.images.length ? p.images.slice() : [];
    if (!urls.length && p.image) urls.push(p.image);
    return urls;
  }

  function pickFeatured(items) {
    var want = (document.body.getAttribute("data-act-featured") || "").trim();
    var found = null;
    if (want) {
      found = items.filter(function (x) {
        return x.code === want;
      })[0];
    }
    if (found) return found;
    return items.filter(function (x) {
      return (x.images && x.images.length) || x.image;
    })[0];
  }

  function paintStrip(p) {
    var strip = document.getElementById("cmActPhotoStrip");
    if (!strip || !p) return;
    var urls = productUrls(p);
    if (!urls.length) {
      strip.hidden = true;
      strip.innerHTML = "";
      return;
    }
    var extra = urls.length > 5 ? urls.length - 5 : 0;
    var show = urls.slice(0, 5);
    var href = prefix + encodeURIComponent(door) + "/" + encodeURIComponent(p.code);
    strip.hidden = false;
    strip.innerHTML = show
      .map(function (u, i) {
        var moreN =
          i === show.length - 1 && extra > 0
            ? '<span class="cm-act-photo-more">+' + extra + "</span>"
            : "";
        return (
          '<a class="cm-act-photo" href="' +
          href +
          '"><img src="' +
          esc(u) +
          '" alt="" width="220" height="220" loading="lazy">' +
          moreN +
          "</a>"
        );
      })
      .join("");
  }

  function paint() {
    var next = products.slice(0, shown + PAGE);
    shown = next.length;
    list.innerHTML = next.map(card).join("");
    if (more) more.hidden = shown >= products.length;
  }

  function isV4(r) {
    if (!r) return false;
    var ver = Number(r.reecriture_version || r.rewrite_version || 0);
    var title = r.titre_reecrit || r.title_en;
    var body =
      r.description_longue_reecrite ||
      r.description_courte_reecrite ||
      r.description_longue_en ||
      r.description_courte_en;
    return ver >= 4 && !!title && !!body;
  }

  function applySidecar(data, rew, requireV4) {
    var map = (rew && rew.products) || {};
    var kept = [];
    (data.products || []).forEach(function (p) {
      var r = map[p.code];
      if (requireV4 && !isV4(r)) return;
      if (isV4(r)) {
        if (isEn) {
          p.title = r.title_en || r.titre_reecrit || p.title;
        } else if (r.titre_reecrit) {
          p.title = r.titre_reecrit;
        }
      }
      kept.push(p);
    });
    data.products = kept;
    return data;
  }

  function matchesPlace(p, terms) {
    if (!terms.length) return true;
    var blob = ((p.title || "") + " " + (p.url || "")).toLowerCase();
    var i;
    for (i = 0; i < terms.length; i++) {
      if (blob.indexOf(terms[i]) !== -1) return true;
    }
    return false;
  }

  function filterProducts(items) {
    if (!filterTerms.length) return items;
    return items.filter(function (p) {
      return matchesPlace(p, filterTerms);
    });
  }

  function setHeading(count) {
    var titleEl = document.getElementById("cmActTitle");
    var place = (document.body.getAttribute("data-act-place") || "").trim();
    if (!place && meta) place = isEn ? meta.placeEn : meta.place;
    if (titleEl && place) {
      titleEl.textContent = isEn
        ? "Viator experiences in " + place
        : "Autres expériences à " + place;
    }
    if (note) {
      if (!count) {
        note.textContent = isEn
          ? "No matching Viator listings for this place right now."
          : "Aucune activité Viator pour ce lieu pour le moment.";
        return;
      }
      note.textContent = isEn
        ? count + " experiences · prices in euros, Viator currency"
        : count + " expériences · prix en euros, devise Viator";
    }
  }

  Promise.all([
    fetch("/assets/data/activites-" + encodeURIComponent(door) + ".json").then(function (r) {
      if (!r.ok) throw new Error("catalogue");
      return r.json();
    }),
    fetch("/assets/data/activites-maroc.rewritten.json?v=cm-hub15")
      .then(function (r) {
        return r.ok ? r.json() : {};
      })
      .catch(function () {
        return {};
      }),
  ])
    .then(function (pair) {
      var data = applySidecar(pair[0], pair[1], !filterTerms.length);
      products = filterProducts(data.products || []).slice();
      products.sort(function (a, b) {
        return Number(b.reviews || 0) - Number(a.reviews || 0);
      });
      paintStrip(pickFeatured(products));
      setHeading(products.length);
      paint();
      if (more) more.addEventListener("click", paint);
    })
    .catch(function () {
      list.innerHTML = isEn
        ? "<p>Catalogue temporarily unavailable.</p>"
        : "<p>Catalogue temporairement indisponible.</p>";
    });
})();
