/* Fiche lieu publique — /lieux/<slug> */
(function () {
  var root = document.getElementById("cmLieuRoot");
  if (!root) return;

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  /* Affichage : devise stockée partenaire (EUR/MAD/CAD). Pas de FX géo silencieux
     sur les fiches hébergement. Le sélecteur manuel existant reste. CQ inchangé. */
  var FX_ALLOWED = ["CAD", "EUR", "MAD", "USD"];
  var FX_REF = "EUR";
  var FX_LS = "cm_fiche_currency";
  var FX_NOTE = "prix dans la devise saisie — confirmé à la réservation";
  var FX_EURO = {
    AT: 1, BE: 1, CY: 1, DE: 1, EE: 1, ES: 1, FI: 1, FR: 1, GR: 1, HR: 1,
    IE: 1, IT: 1, LT: 1, LU: 1, LV: 1, MT: 1, NL: 1, PT: 1, SI: 1, SK: 1,
    MC: 1, AD: 1
  };
  var FX_SUFFIX = { CAD: " $ CA", EUR: " €", MAD: " DH", USD: " $ US" };

  function fxNorm(code, fallback) {
    var c = String(code || "").toUpperCase();
    if (FX_ALLOWED.indexOf(c) !== -1) return c;
    var fb = String(fallback || FX_REF).toUpperCase();
    return FX_ALLOWED.indexOf(fb) !== -1 ? fb : FX_REF;
  }

  function fxCountryToCurrency(cc) {
    var c = String(cc || "").trim().toUpperCase();
    if (c.length !== 2 || c === "XX" || c === "T1") return null;
    if (c === "CA") return "CAD";
    if (c === "MA") return "MAD";
    if (FX_EURO[c]) return "EUR";
    return "USD";
  }

  function isHebergementFiche() {
    return !!(root && (root.classList.contains("cm-fiche") || root.querySelector(".cm-fiche-rooms")));
  }

  function fxPick(override, country, ref) {
    var r = fxNorm(ref, FX_REF);
    var ov = String(override || "").toUpperCase();
    if (FX_ALLOWED.indexOf(ov) !== -1) return ov;
    /* Hébergement Marocain : devise stockée visible. Pas de CAD/USD selon l’IP. */
    if (isHebergementFiche()) return r;
    var geo = fxCountryToCurrency(country);
    return geo || r;
  }

  function fxFormat(amount, currency, kind, approx) {
    if (!amount) return kind === "from" || kind === "day" ? "Tarif sur demande" : "Sur devis";
    var suffix = FX_SUFFIX[fxNorm(currency)] || " €";
    if (kind === "day" || kind === "privatisation") {
      var day = Math.round(amount) + suffix + " / jour";
      if (approx) day = "≈ " + day;
      return "Privatisation dès " + day;
    }
    var body = Math.round(amount) + suffix + " / nuit";
    if (approx) body = "≈ " + body;
    if (kind === "from") return "À partir de " + body;
    return body;
  }

  function fxSelectorHtml(active) {
    var on = fxNorm(active);
    var buttons = FX_ALLOWED.map(function (c) {
      return (
        '<button type="button" class="cm-fiche-fx-btn' +
        (c === on ? " is-on" : "") +
        '" data-fx="' +
        c +
        '" aria-pressed="' +
        (c === on ? "true" : "false") +
        '">' +
        c +
        "</button>"
      );
    }).join("");
    return (
      '<div class="cm-fiche-fx" id="cmFicheFx"><div class="cm-fiche-fx-sel" role="group" aria-label="Devise">' +
      buttons +
      '</div><p class="cm-fiche-fx-note">' +
      FX_NOTE +
      "</p></div>"
    );
  }

  function fxParseLegacy(text) {
    var raw = String(text || "");
    var m = raw.match(/(\d+(?:[.,]\d+)?)\s*(?:€|EUR|\$\s*CA|CAD|DH|MAD|\$\s*US|USD)/i);
    if (!m) return 0;
    return parseFloat(m[1].replace(",", ".")) || 0;
  }

  function fxConvert(amount, src, dest, rates) {
    var a = fxNorm(src);
    var b = fxNorm(dest);
    if (a === b) return amount;
    if (!rates) return null;
    var rf = Number(rates[a] || 0);
    var rt = Number(rates[b] || 0);
    if (rf <= 0 || rt <= 0) return null;
    return amount * (rt / rf);
  }

  function fxEnsureNodes() {
    var ref = fxNorm(root.getAttribute("data-currency-ref") || FX_REF);
    root.setAttribute("data-currency-ref", ref);
    root.querySelectorAll(".cm-fiche-price, .cm-fiche-room-price, .cm-fiche-book-mobile span").forEach(function (el) {
      if (el.getAttribute("data-price-ref")) return;
      var n = fxParseLegacy(el.textContent);
      if (!n) return;
      el.setAttribute("data-price-ref", String(Math.round(n)));
      el.setAttribute("data-currency-ref", ref);
      el.setAttribute(
        "data-price-kind",
        el.classList.contains("cm-fiche-room-price") ? "room" : "from"
      );
    });
    if (!document.getElementById("cmFicheFx")) {
      var priceEl = root.querySelector(".cm-fiche-price");
      if (priceEl) priceEl.insertAdjacentHTML("afterend", fxSelectorHtml(ref));
    }
  }

  function fxApply(display, rates) {
    var ref = fxNorm(root.getAttribute("data-currency-ref") || FX_REF);
    root.querySelectorAll("[data-price-ref]").forEach(function (el) {
      var src = fxNorm(el.getAttribute("data-currency-ref") || ref);
      var amount = Number(el.getAttribute("data-price-ref") || 0);
      var kind = el.getAttribute("data-price-kind") || "room";
      if (!amount) return;
      var converted = fxConvert(amount, src, display, rates);
      var approx = display !== src;
      var shown = amount;
      var shownCur = src;
      if (approx && converted != null) {
        shown = converted;
        shownCur = display;
      } else {
        approx = false;
      }
      el.textContent = fxFormat(shown, shownCur, kind, approx);
    });
    var box = document.getElementById("cmFicheFx");
    if (!box) return;
    box.querySelectorAll("[data-fx]").forEach(function (btn) {
      var on = btn.getAttribute("data-fx") === display;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function fxLoadJson(url) {
    return fetch(url, { cache: "no-cache" }).then(function (r) {
      if (!r.ok) throw new Error("fx");
      return r.json();
    });
  }

  function fxLoadRates() {
    return fxLoadJson("/api/taux.json")
      .catch(function () {
        return fxLoadJson("/assets/taux.json");
      })
      .catch(function () {
        return fxLoadJson("https://open.er-api.com/v6/latest/CAD").then(function (d) {
          return { rates: d.rates || {}, source: "open.er-api.com" };
        });
      })
      .catch(function () {
        return { rates: { CAD: 1 } };
      });
  }

  function fxLoadCountry() {
    return fxLoadJson("/api/geo.json")
      .then(function (d) {
        return d && d.country != null ? String(d.country) : "";
      })
      .catch(function () {
        return "";
      });
  }

  function bindFicheCurrency() {
    fxEnsureNodes();
    var ref = fxNorm(root.getAttribute("data-currency-ref") || FX_REF);
    var rates = { CAD: 1 };
    var country = "";
    function current() {
      var ov = "";
      try {
        ov = localStorage.getItem(FX_LS) || "";
      } catch (e) {
        ov = "";
      }
      var box = document.getElementById("cmFicheFx");
      var picked = box && box.getAttribute("data-user-picked") === "1";
      if (isHebergementFiche() && !picked) return ref;
      return fxPick(ov, country, ref);
    }
    function paint() {
      fxApply(current(), rates.rates || rates);
    }
    var box = document.getElementById("cmFicheFx");
    if (box && !box.getAttribute("data-bound")) {
      box.setAttribute("data-bound", "1");
      box.addEventListener("click", function (ev) {
        var btn = ev.target.closest("[data-fx]");
        if (!btn) return;
        var code = fxNorm(btn.getAttribute("data-fx"));
        try {
          localStorage.setItem(FX_LS, code);
        } catch (e) {}
        box.setAttribute("data-user-picked", "1");
        paint();
      });
    }
    paint();
    Promise.all([fxLoadRates(), fxLoadCountry()]).then(function (pair) {
      rates = pair[0] || { rates: { CAD: 1 } };
      country = pair[1] || "";
      paint();
    });
  }


  var OCCASIONS_BY_SLUG = {
    "casa-alma": [
      { href: "/evenements/soiree-entreprise", label: "soirée entreprise" },
      { href: "/evenements/anniversaires", label: "anniversaire" },
      { href: "/evenements/groupes-amis-famille", label: "groupe" }
    ],
    "villa-michelle": [
      { href: "/evenements/mariages", label: "mariage" },
      { href: "/evenements/soiree-entreprise", label: "soirée entreprise" },
      { href: "/evenements/galas-levees-de-fonds", label: "gala" }
    ],
    "villa-nafsi": [
      { href: "/evenements/fiancailles", label: "fiançailles" },
      { href: "/evenements/anniversaires", label: "anniversaire" },
      { href: "/evenements/team-building-retraites", label: "retraite" }
    ],
    "dar-sacada": [
      { href: "/evenements/fiancailles", label: "fiançailles" },
      { href: "/evenements/groupes-amis-famille", label: "petit groupe" },
      { href: "/evenements/team-building-retraites", label: "retraite" }
    ],
    "la-casa-ysabella": [
      { href: "/evenements/groupes-amis-famille", label: "groupe" },
      { href: "/evenements/anniversaires", label: "anniversaire" },
      { href: "/evenements/team-building-retraites", label: "retraite" }
    ],
    "riad-ines": [
      { href: "/evenements/mariages", label: "mariage intime" },
      { href: "/evenements/anniversaires", label: "anniversaire" }
    ]
  };

  var YSABELLA_ALIASES = {
    "la-casa-ysabella": true,
    "riad-la-casa-ysabella-marrakech": true,
    "riad-medina-marrakech-la-casa-ysabella": true,
    ysabella: true,
    "casa-ysabella": true,
    "la-casa-isabella": true,
    "casa-isabella": true,
  };
  var YSABELLA_PUBLIC_PATH = "/lieux/riad-medina-marrakech-la-casa-ysabella";
  var YSABELLA_SEO = {
    27: { file: "chambre-emilia-1", alt: "Chambre Emilia, suite familiale du riad La Casa Ysabella à Marrakech", crop: "left" },
    28: { file: "chambre-emilia-2", alt: "Autre vue de la chambre Emilia au riad La Casa Ysabella à Marrakech", crop: "mid" },
    29: { file: "chambre-emilia-3", alt: "Détail de la chambre Emilia du riad La Casa Ysabella à Marrakech", crop: "left" },
    32: { file: "chambre-emilia-tableau", alt: "Chambre Emilia du riad La Casa Ysabella à Marrakech, tableau rouge et chaise artisanale", crop: "left" },
    33: { file: "chambre-julia", alt: "Chambre Julia du riad La Casa Ysabella à Marrakech, plats tissés et vitrail", crop: "left" },
    35: { file: "chambre-nael-1", alt: "Chambre Nael du riad La Casa Ysabella à Marrakech, lit et tapis berbère", crop: "mid" },
    36: { file: "chambre-nael-2", alt: "Autre angle de la chambre Nael au riad La Casa Ysabella à Marrakech", crop: "right-low" },
    37: { file: "chambre-nael-3", alt: "Détail de la chambre Nael du riad La Casa Ysabella à Marrakech", crop: "mid" },
    38: { file: "chambre-antonella", alt: "Chambre Antonella, suite triple du riad La Casa Ysabella à Marrakech", crop: "right" },
    42: { file: "chambre-nada-1", alt: "Chambre Nada du riad La Casa Ysabella à Marrakech", crop: "left" },
    43: { file: "chambre-nada-2", alt: "Autre vue de la chambre Nada au riad La Casa Ysabella à Marrakech", crop: "mid" },
    46: { file: "suite-ysabella", alt: "Suite Ysabella, chambre triple du riad La Casa Ysabella à Marrakech", crop: "left" },
    50: { file: "salon-the-marocain", alt: "Service à thé marocain dans un salon du riad La Casa Ysabella à Marrakech", crop: "low" },
    51: { file: "salon-poterie-coussins", alt: "Poterie et coussins berbères dans le salon du riad La Casa Ysabella à Marrakech", crop: "mid" },
    52: { file: "salle-a-manger", alt: "Salle à manger du riad La Casa Ysabella à Marrakech", crop: "low" },
    53: { file: "patio-fontaine", alt: "Patio et fontaine du riad La Casa Ysabella à Marrakech, pétales de roses", crop: "low" },
    54: { file: "salon-banquettes", alt: "Salon à banquettes du riad La Casa Ysabella à Marrakech", crop: "mid" },
    55: { file: "salon-arche", alt: "Salon sous arche du riad La Casa Ysabella à Marrakech", crop: "mid" },
    56: { file: "plaque-entree", alt: "Plaque d’entrée La Casa Ysabella sur la porte du riad à Marrakech", crop: "mid" },
    57: { file: "table-dressee-patio", alt: "Table dressée dans le patio du riad La Casa Ysabella à Marrakech", crop: "low" },
    58: { file: "table-longue", alt: "Longue table dressée au riad La Casa Ysabella à Marrakech", crop: "low" },
    59: { file: "service-the", alt: "Service à thé du riad La Casa Ysabella à Marrakech", crop: "left" },
    60: { file: "the-zellige", alt: "Thé marocain sur zellige au riad La Casa Ysabella à Marrakech", crop: "mid" },
    61: { file: "table-roses", alt: "Table dressée avec roses au riad La Casa Ysabella à Marrakech", crop: "mid" },
    62: { file: "terrasse-table", alt: "Table de terrasse du riad La Casa Ysabella à Marrakech, coussins bleus", crop: "bottom" },
    63: { file: "the-table", alt: "Thé servi à table au riad La Casa Ysabella à Marrakech", crop: "mid" },
    64: { file: "patio-fontaine-dessus", alt: "Fontaine étoilée vue du dessus, patio du riad La Casa Ysabella à Marrakech", crop: "low" }
  };

  function slugFromPath() {
    var m = (location.pathname || "").match(/\/lieux\/([a-z0-9-]+)\/?/i);
    var raw = m ? m[1].toLowerCase() : "";
    if (!raw) {
      var q = new URLSearchParams(location.search || "");
      raw = (q.get("slug") || "").toLowerCase();
    }
    if (YSABELLA_ALIASES[raw]) return "la-casa-ysabella";
    return raw;
  }

  function publicLieuPath(lieu) {
    var slug = (lieu && lieu.slug) || slugFromPath();
    if (slug === "la-casa-ysabella" || YSABELLA_ALIASES[slug]) {
      return YSABELLA_PUBLIC_PATH;
    }
    if (lieu && lieu.detail_url) return lieu.detail_url;
    return slug ? "/lieux/" + slug : location.pathname;
  }

  function seoPhotoMeta(ph) {
    if (!ph) return null;
    return YSABELLA_SEO[ph.id] || YSABELLA_SEO[String(ph.id)] || null;
  }

  function photoCrop(ph) {
    var meta = seoPhotoMeta(ph);
    return (meta && meta.crop) || "";
  }

  function cropAttr(ph) {
    var crop = photoCrop(ph);
    return crop ? ' data-crop="' + escapeHtml(crop) + '"' : "";
  }

  function seoPhotoUrl(ph, width) {
    var meta = seoPhotoMeta(ph);
    if (!meta) return "";
    var u = "/photos/riad-la-casa-ysabella-marrakech-" + meta.file + ".jpg";
    return width ? u + "?w=" + width : u;
  }

  function photoAlt(ph, fallback) {
    var meta = seoPhotoMeta(ph);
    if (meta) return meta.alt;
    var raw = String((ph && ph.legende) || fallback || "").trim();
    raw = raw.split(" — ")[0].split(" - ")[0];
    if (raw && raw === raw.toUpperCase() && raw.length > 3) {
      raw = raw.charAt(0) + raw.slice(1).toLowerCase();
    }
    return raw || fallback || "";
  }

  function zoneLabel(z) {
    var map = {
      marrakech_centre: "Marrakech centre",
      palmeraie: "Palmeraie",
      agafay: "Agafay",
      autre: "Autour de Marrakech",
    };
    return map[z] || (z ? String(z).replace(/_/g, " ") : "");
  }

  function stripHtml(html) {
    return String(html || "")
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function truncateWords(text, limit) {
    var t = String(text || "").trim();
    var max = limit || 168;
    if (t.length <= max) return t;
    var snippet = t.slice(0, max + 1);
    var cut = snippet.lastIndexOf(" ");
    if (cut < Math.floor(max * 0.55)) cut = max;
    return snippet.slice(0, cut).replace(/[ ,.;:…]+$/, "") + "…";
  }

  function roomDescMarkup(descFull, roomId) {
    var full = String(descFull || "");
    var tid = escapeHtml(roomId || "x");
    if (full.length <= 150) {
      return '<p class="cm-fiche-room-desc">' + escapeHtml(full) + "</p>";
    }
    return (
      '<input type="checkbox" class="cm-fiche-room-toggle" id="cm-room-more-' +
      tid +
      '" aria-hidden="true">' +
      '<p class="cm-fiche-room-desc" id="cm-room-desc-' +
      tid +
      '" data-short="' +
      escapeHtml(truncateWords(full)) +
      '">' +
      escapeHtml(full) +
      "</p>" +
      '<label class="cm-fiche-room-more" for="cm-room-more-' +
      tid +
      '" aria-controls="cm-room-desc-' +
      tid +
      '"><span class="cm-fiche-room-more-open">Lire plus</span>' +
      '<span class="cm-fiche-room-more-close">Lire moins</span></label>'
    );
  }

  function placePhrase(lieu) {
    var district = String(lieu.district || "").trim();
    var city = String(lieu.city || "Marrakech").trim();
    var zone = String(lieu.zone || "").trim();
    if (district.toLowerCase() === "bab doukala") district = "Bab Doukkala";
    if (district) {
      return city && city.toLowerCase().indexOf(district.toLowerCase()) === -1
        ? district + " " + city
        : district;
    }
    if (zone === "palmeraie") return "Palmeraie Marrakech";
    if (zone === "agafay") return "désert d'Agafay";
    return city || "Marrakech";
  }

  function keywordPrincipal(lieu) {
    var blob = (
      String(lieu.name || "") +
      " " +
      stripHtml(lieu.narrative_html || lieu.description_html || "")
    ).toLowerCase();
    if (blob.indexOf("riad") !== -1) return "Riad à louer";
    if (blob.indexOf("villa") !== -1) return "Villa à louer";
    if (blob.indexOf("maison d'hôtes") !== -1 || blob.indexOf("maison d’hôtes") !== -1) {
      return "Maison d'hôtes";
    }
    if (lieu.pillar === "villas_riads") return "Maison à louer";
    return "Séjour à Marrakech";
  }

  function seoTitle(lieu) {
    return (
      (lieu.name || "Lieu") +
      " — " +
      keywordPrincipal(lieu) +
      " " +
      placePhrase(lieu) +
      " | Coins Marocain"
    );
  }

  function seoDescription(lieu) {
    var cur = fxNorm((lieu && (lieu.currency || lieu.currency_ref)) || root.getAttribute("data-currency-ref"), FX_REF);
    var suffix = FX_SUFFIX[cur] || " €";
    if (isYsabellaLieu(lieu) || (lieu.slug || slugFromPath()) === "la-casa-ysabella") {
      return "Riad de 6 chambres à Bab Doukkala, quartier authentique de la médina. Dès 75 € la nuit, privatisation 585 €. Petit-déjeuner inclus. Réservation directe via Coins Marocain.";
    }
    var price = Number(lieu.price_from || 0);
    var priceBit = price ? " dès " + Math.round(price) + suffix + "/nuit" : "";
    return (
      (lieu.name || "Ce lieu") +
      " — " +
      keywordPrincipal(lieu).replace(" à louer", "").toLowerCase() +
      " à " +
      placePhrase(lieu) +
      priceBit +
      ". Réservation directe via Coins Marocain."
    );
  }

  function isYsabellaLieu(lieu) {
    var slug = (lieu && lieu.slug) || slugFromPath();
    return slug === "la-casa-ysabella" || !!YSABELLA_ALIASES[slug];
  }

  function propertyKind(lieu) {
    var blob = (
      String((lieu && lieu.name) || "") +
      " " +
      String((lieu && lieu.property_type) || "") +
      " " +
      stripHtml((lieu && (lieu.narrative_html || lieu.description_html)) || "")
    ).toLowerCase();
    if (blob.indexOf("riad") !== -1) return "Riad";
    if (blob.indexOf("villa") !== -1) return "Villa";
    if (blob.indexOf("château") !== -1 || blob.indexOf("chateau") !== -1) {
      return "Château";
    }
    if (blob.indexOf("maison d'hôtes") !== -1 || blob.indexOf("maison d’hôtes") !== -1) {
      return "Maison d'hôtes";
    }
    if (lieu && lieu.pillar === "villas_riads") return "Maison";
    return "Lieu";
  }

  function seoKeyword(lieu) {
    var kind = propertyKind(lieu);
    if (kind !== "Lieu") return kind;
    var raw = keywordPrincipal(lieu).replace(" à louer", "").trim();
    if (raw.toLowerCase().indexOf("séjour") === 0) return "Séjour";
    return raw || kind;
  }

  function normalizedDistrict(lieu) {
    var district = String((lieu && lieu.district) || "").trim();
    if (district.toLowerCase() === "bab doukala") return "Bab Doukkala";
    return district;
  }

  function isMedinaArea(lieu) {
    var district = normalizedDistrict(lieu).toLowerCase();
    var zone = String((lieu && lieu.zone) || "").trim().toLowerCase();
    return (
      district === "bab doukkala" ||
      district === "bab doukala" ||
      district === "médina" ||
      district === "medina" ||
      zone === "marrakech_centre"
    );
  }

  function seoRegion(lieu) {
    if (seoKeyword(lieu).toLowerCase() === "riad" && isMedinaArea(lieu)) {
      return "médina";
    }
    var district = normalizedDistrict(lieu);
    if (district) {
      var d = district.toLowerCase();
      if (d === "médina" || d === "medina") return "médina";
      return district;
    }
    var zone = String((lieu && lieu.zone) || "").trim();
    if (zone === "palmeraie") return "Palmeraie";
    if (zone === "agafay") return "Agafay";
    return "";
  }

  function seoCity(lieu) {
    return String((lieu && lieu.city) || "Marrakech").trim() || "Marrakech";
  }

  function seoPlaceTail(lieu) {
    var region = seoRegion(lieu);
    var city = seoCity(lieu);
    var parts = [];
    if (region) parts.push(region);
    if (city && (region || "").toLowerCase().indexOf(city.toLowerCase()) === -1) {
      parts.push(city);
    }
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  function seoShortName(lieu) {
    var name = ((lieu && lieu.name) || "Lieu").trim();
    return name.replace(/^(la|le|les|l['’])\s*/i, "").trim() || name;
  }

  function galleryPlacePhrase(lieu) {
    return seoPlaceTail(lieu) || seoCity(lieu);
  }

  function seoH1(lieu) {
    var name = ((lieu && lieu.name) || "Lieu").trim();
    var kind = seoKeyword(lieu);
    var place = seoPlaceTail(lieu);
    var nameLow = name.toLowerCase();
    var kindLow = String(kind || "").toLowerCase();
    /* OTA-style: ville large puis localisation précise. */
    if (isNougatLieu(lieu)) {
      var city = seoCity(lieu);
      var district = normalizedDistrict(lieu);
      var nougatPlace =
        city && district && city.toLowerCase() !== district.toLowerCase()
          ? city + ", " + district
          : place || city || district;
      return (name + (nougatPlace ? " — " + nougatPlace : "")).replace(/\s+/g, " ").trim();
    }
    /* Évite « Château Nougat — Château Tameslouht ». */
    if (kindLow && nameLow.indexOf(kindLow) === 0) {
      return (name + (place ? " — " + place : "")).replace(/\s+/g, " ").trim();
    }
    return (name + " — " + kind + " " + place).replace(/\s+/g, " ").trim();
  }

  function ledePlacePhrase(lieu) {
    var region = seoRegion(lieu);
    var city = seoCity(lieu);
    if (!region) return "à " + city;
    var key = region.toLowerCase();
    if (key === "médina" || key === "medina") {
      return key.indexOf(city.toLowerCase()) === -1
        ? "de la médina de " + city
        : "de la médina";
    }
    if (key === "palmeraie") {
      return key.indexOf(city.toLowerCase()) === -1
        ? "de la " + region + " à " + city
        : "de la " + region;
    }
    if ("aeiouéèàâä".indexOf(key.charAt(0)) !== -1) {
      return "d'" + region + (key.indexOf(city.toLowerCase()) === -1 ? " à " + city : "");
    }
    return "à " + region + (key.indexOf(city.toLowerCase()) === -1 ? ", " + city : "");
  }

  function seoLede(lieu) {
    var name = ((lieu && lieu.name) || "Ce lieu").trim();
    var kind = seoKeyword(lieu).toLowerCase();
    var article = kind.indexOf("villa") === 0 || kind.indexOf("maison") === 0 ? "une" : "un";
    var place = ledePlacePhrase(lieu);
    var core = name + " est " + article + " " + kind + " " + place;
    var district = normalizedDistrict(lieu);
    var region = seoRegion(lieu);
    var extraDistrict = "";
    if (
      district &&
      region &&
      district.toLowerCase() !== region.toLowerCase() &&
      place.toLowerCase().indexOf(district.toLowerCase()) === -1
    ) {
      extraDistrict = ", à " + district;
    }
    var text = stripHtml((lieu && (lieu.narrative_html || lieu.description_html)) || "").toLowerCase();
    var features = [];
    if (text.indexOf("patio") !== -1 && text.indexOf("fontaine") !== -1) {
      features.push("patio et fontaine");
    } else if (text.indexOf("piscine") !== -1) {
      features.push("piscine");
    }
    var cur = fxNorm((lieu && (lieu.currency || lieu.currency_ref)) || root.getAttribute("data-currency-ref"), FX_REF);
    var suffix = FX_SUFFIX[cur] || " €";
    var price = Number((lieu && lieu.price_from) || 0);
    var priceBit = price ? "chambres dès " + Math.round(price) + suffix + " la nuit" : "";
    if (isYsabellaLieu(lieu)) {
      features = ["quartier authentique"];
      priceBit = "six chambres dès 75 € la nuit";
    }
    if (isNougatLieu(lieu)) {
      features = ["privatisation familles & groupes", "jusqu’à 30 personnes"];
      var priv = Number((lieu && lieu.tarif_privatisation_jour) || 0);
      if (priv) {
        priceBit = "privatisation dès " + Math.round(priv) + " € / jour";
      } else if (price) {
        priceBit = "chambres dès " + Math.round(price) + suffix + " la nuit";
      }
    }
    var after = features.concat(priceBit ? [priceBit] : []).join(", ");
    if (extraDistrict && after) return core + extraDistrict + " : " + after + ".";
    if (extraDistrict) return core + extraDistrict + ".";
    if (after) return core + " : " + after + ".";
    return core + ".";
  }

  function seoGalleryH2(lieu) {
    return (seoKeyword(lieu) + " " + seoPlaceTail(lieu) + " " + seoShortName(lieu))
      .replace(/\s+/g, " ")
      .trim();
  }

  function seoRoomsH2(lieu) {
    return gallerySectionHeading("chambres", lieu, "Les chambres");
  }

  function galleryH2Title(lieu) {
    return seoGalleryH2(lieu);
  }

  function pageH1(lieu) {
    return seoH1(lieu);
  }

  function pageLede(lieu) {
    return seoLede(lieu);
  }

  function roomsH2Title(lieu) {
    return seoRoomsH2(lieu);
  }

  function galleryH2Subtitle(lieu, n) {
    if (isYsabellaLieu(lieu)) return n + " photos — chambres, patio, table";
    return n + " photos";
  }

  var KIND_ARTICLES = {
    Riad: { de: "du", a: "au" },
    Villa: { de: "de la", a: "à la" },
    Château: { de: "du", a: "au" },
    "Maison d'hôtes": { de: "de la", a: "à la" },
    Maison: { de: "de la", a: "à la" },
    Lieu: { de: "du", a: "au" }
  };
  var SECTION_HEADS = {
    chambres: { noun: "Chambres", art: "de" },
    aires_communes: { noun: "Aires communes", art: "de" },
    restauration: { noun: "Restauration", art: "a" },
    exterieur_piscine: { noun: "Extérieur et piscine", art: "de" },
    bien_etre: { noun: "Bien-être et spa", art: "de" }
  };

  function gallerySectionHeading(code, lieu, fallback) {
    var spec = SECTION_HEADS[code];
    if (!spec) return fallback || code;
    var kind = propertyKind(lieu);
    var arts = KIND_ARTICLES[kind] || KIND_ARTICLES.Lieu;
    var art = spec.art === "a" ? arts.a : arts.de;
    var name = ((lieu && lieu.name) || "ce lieu").trim();
    var city = String((lieu && lieu.city) || "Marrakech").trim() || "Marrakech";
    return spec.noun + " " + art + " " + kind.toLowerCase() + " " + name + " à " + city;
  }

  function categoryCodes(lieu) {
    var codes = (lieu.category_codes || []).slice();
    (lieu.categories || []).forEach(function (c) {
      if (c && c.code && codes.indexOf(c.code) === -1) codes.push(c.code);
    });
    return codes;
  }

  function shouldNoindex(lieu) {
    var codes = categoryCodes(lieu);
    var hasPub = codes.indexOf("decouverte") !== -1 || codes.indexOf("hebergement") !== -1;
    return codes.indexOf("privatisation") !== -1 && !hasPub;
  }

  function absUrl(u) {
    u = String(u || "").trim();
    if (!u) return "";
    if (u.indexOf("//") === 0) return "https:" + u;
    if (/^https?:\/\//i.test(u)) return u;
    return "https://coinsmarocain.com" + (u.charAt(0) === "/" ? u : "/" + u);
  }

  function isPrivatisation(lieu) {
    var codes = categoryCodes(lieu);
    return !!lieu.can_privatise || codes.indexOf("privatisation") !== -1;
  }

  function lodgingAddress(lieu) {
    var city = String(lieu.city || "Marrakech").trim() || "Marrakech";
    var addr = { "@type": "PostalAddress", addressLocality: city, addressCountry: "MA" };
    if (isPrivatisation(lieu)) {
      var zoneMap = {
        marrakech_centre: "Marrakech centre",
        palmeraie: "Palmeraie",
        agafay: "Agafay"
      };
      var zl = zoneMap[lieu.zone] || "";
      if (zl && city.toLowerCase().indexOf(zl.toLowerCase()) === -1) addr.addressRegion = zl;
      return addr;
    }
    var district = String(lieu.district || "").trim();
    if (district.toLowerCase() === "bab doukala") district = "Bab Doukkala";
    if (district && city.toLowerCase().indexOf(district.toLowerCase()) === -1) {
      addr.addressRegion = district;
    }
    var street = String(lieu.street || "").trim();
    if (street && categoryCodes(lieu).indexOf("decouverte") !== -1) {
      addr.streetAddress = street;
    }
    return addr;
  }

  function lodgingGeo(lieu) {
    if (isPrivatisation(lieu) || categoryCodes(lieu).indexOf("decouverte") === -1) return null;
    var lat = Number(lieu.lat || 0);
    var lng = Number(lieu.lng || 0);
    if (!lat || !lng) return null;
    return { "@type": "GeoCoordinates", latitude: lat, longitude: lng };
  }

  function priceRange(lieu) {
    var prices = [];
    (lieu.rooms || []).forEach(function (r) {
      var p = Number(r.price_per_night || 0);
      if (p > 0) prices.push(p);
    });
    if (!prices.length && Number(lieu.price_from || 0) > 0) prices.push(Number(lieu.price_from));
    if (!prices.length) return "";
    var lo = Math.min.apply(null, prices);
    var hi = Math.max.apply(null, prices);
    var cur = fxNorm((lieu && (lieu.currency || lieu.currency_ref)) || root.getAttribute("data-currency-ref"), FX_REF);
    return lo === hi ? cur + " " + Math.round(lo) : cur + " " + Math.round(lo) + "-" + Math.round(hi);
  }

  function photoUrls(lieu, limit) {
    var out = [];
    (lieu.photos || []).forEach(function (ph) {
      if (out.length >= (limit || 8)) return;
      var u = absUrl(seoPhotoUrl(ph, 1600) || ph.url_full || ph.url || ph.url_thumb || "");
      if (u && out.indexOf(u) === -1) out.push(u);
    });
    return out;
  }

  function aggregateRating(lieu) {
    var notes = [];
    (lieu.reviews || []).forEach(function (r) {
      var raw = r && (r.note != null ? r.note : r.rating != null ? r.rating : r.score);
      var n = Number(raw);
      if (n > 0 && n <= 5) notes.push(n);
    });
    if (!notes.length) return null;
    var sum = notes.reduce(function (a, b) { return a + b; }, 0);
    return {
      "@type": "AggregateRating",
      ratingValue: Math.round((sum / notes.length) * 100) / 100,
      reviewCount: notes.length,
      bestRating: 5,
      worstRating: 1
    };
  }

  function lodgingJsonLd(lieu) {
    var url = "https://coinsmarocain.com" + publicLieuPath(lieu);
    var desc = stripHtml(lieu.description_html || lieu.narrative_html || "") || seoDescription(lieu);
    var node = {
      "@type": "LodgingBusiness",
      "@id": url + "#lodging",
      name: lieu.name || "Lieu",
      url: url,
      description: desc.slice(0, 800),
      address: lodgingAddress(lieu)
    };
    var images = photoUrls(lieu, 8);
    if (images.length) node.image = images;
    var pr = priceRange(lieu);
    if (pr) node.priceRange = pr;
    var geo = lodgingGeo(lieu);
    if (geo) node.geo = geo;
    var rating = aggregateRating(lieu);
    if (rating) node.aggregateRating = rating;
    var feats = (lieu.amenities || [])
      .map(function (a) { return String(a || "").trim(); })
      .filter(Boolean)
      .slice(0, 16)
      .map(function (name) {
        return { "@type": "LocationFeatureSpecification", name: name };
      });
    if (feats.length) node.amenityFeature = feats;
    var rooms = (lieu.rooms || []).map(function (r) {
      var name = String(r.nom || r.name || "").replace(/\s+/g, " ").trim();
      if (!name) return null;
      var item = { "@type": "HotelRoom", name: name };
      var sleeps = Number(r.sleeps || 0);
      if (sleeps) item.occupancy = { "@type": "QuantitativeValue", value: sleeps, unitText: "occupants" };
      var rd = stripHtml(r.description || "");
      if (rd) item.description = rd.slice(0, 400);
      return item;
    }).filter(Boolean);
    if (rooms.length) {
      node.numberOfRooms = rooms.length;
      node.containsPlace = rooms;
    }
    var graph = [node];
    var thumb = images[0] || "";
    (lieu.videos || []).forEach(function (v) {
      var content = absUrl(v.url || "");
      if (!content) return;
      var vo = {
        "@type": "VideoObject",
        name: v.title || lieu.name || "Vidéo",
        description: (v.description || seoDescription(lieu) || v.title || "").slice(0, 300),
        contentUrl: content
      };
      var poster = absUrl(v.thumbnail || v.thumbnail_url || "") || thumb;
      if (poster) vo.thumbnailUrl = poster;
      if (v.duration) vo.duration = v.duration;
      if (v.upload_date || v.date_upload) vo.uploadDate = String(v.upload_date || v.date_upload).slice(0, 10);
      graph.push(vo);
    });
    return { "@context": "https://schema.org", "@graph": graph };
  }

  function upsertLodgingJsonLd(lieu) {
    var el = document.getElementById("cmLieuJsonLd");
    if (!el) {
      el = document.createElement("script");
      el.type = "application/ld+json";
      el.id = "cmLieuJsonLd";
      document.head.appendChild(el);
    }
    el.textContent = JSON.stringify(lodgingJsonLd(lieu));
  }

  function setMeta(lieu) {
    upsertLodgingJsonLd(lieu);
    document.title = seoTitle(lieu);
    var desc = seoDescription(lieu);
    var md = document.querySelector('meta[name="description"]');
    if (md) md.setAttribute("content", desc);
    var selfUrl = "https://coinsmarocain.com" + publicLieuPath(lieu);
    var canon = document.querySelector('link[rel="canonical"]');
    if (canon) {
      canon.setAttribute("href", selfUrl);
    }
    var robots = document.querySelector('meta[name="robots"]');
    if (robots) {
      robots.setAttribute("content", shouldNoindex(lieu) ? "noindex,follow" : "index,follow");
    }
    var ogTitle = document.querySelector('meta[property="og:title"]');
    if (!ogTitle) {
      ogTitle = document.createElement("meta");
      ogTitle.setAttribute("property", "og:title");
      document.head.appendChild(ogTitle);
    }
    ogTitle.setAttribute("content", seoTitle(lieu));
    var ogUrl = document.querySelector('meta[property="og:url"]');
    if (!ogUrl) {
      ogUrl = document.createElement("meta");
      ogUrl.setAttribute("property", "og:url");
      document.head.appendChild(ogUrl);
    }
    ogUrl.setAttribute(
      "content",
      "https://coinsmarocain.com" + publicLieuPath(lieu)
    );
    var photos = lieu.photos || [];
    var photo = photos.filter(function (p) { return String(p.id) === "53"; })[0] || photos[0];
    var ogSrc = seoPhotoUrl(photo, 1600) || (photo && (photo.url_full || photo.url)) || "";
    if (ogSrc) {
      var ogImg = document.querySelector('meta[property="og:image"]');
      if (ogImg) {
        ogImg.setAttribute("content", absUrl(ogSrc));
      }
    }
  }

  function videoBlock(v) {
    var u = v.url || "";
    var title = escapeHtml(v.title || "");
    var yt = u.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/))([\w-]{6,})/i);
    if (yt) {
      return (
        '<div class="cm-lieu-video"><iframe src="https://www.youtube-nocookie.com/embed/' +
        yt[1] +
        '?rel=0" title="' +
        title +
        '" allow="encrypted-media" allowfullscreen loading="lazy"></iframe><p class="cap">' +
        title +
        "</p></div>"
      );
    }
    return (
      '<div class="cm-lieu-video"><video controls playsinline preload="metadata" src="' +
      escapeHtml(u) +
      '"></video><p class="cap">' +
      title +
      "</p></div>"
    );
  }

  function openLightbox(urls, index) {
    var existing = document.getElementById("cmLieuLb");
    if (existing) existing.remove();
    var i = Math.max(0, Math.min(index || 0, urls.length - 1));
    var box = document.createElement("div");
    box.id = "cmLieuLb";
    box.className = "cm-lieu-lb";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.innerHTML =
      '<button type="button" class="cm-lieu-lb-close" aria-label="Fermer">&times;</button>' +
      (urls.length > 1
        ? '<button type="button" class="cm-lieu-lb-nav prev" aria-label="Précédente">‹</button>' +
          '<button type="button" class="cm-lieu-lb-nav next" aria-label="Suivante">›</button>'
        : "") +
      '<img alt="" src="' +
      escapeHtml(urls[i]) +
      '">' +
      '<p class="cm-lieu-lb-count">' +
      (i + 1) +
      " / " +
      urls.length +
      "</p>";
    document.body.appendChild(box);
    document.body.style.overflow = "hidden";

    function show(n) {
      i = (n + urls.length) % urls.length;
      box.querySelector("img").src = urls[i];
      var c = box.querySelector(".cm-lieu-lb-count");
      if (c) c.textContent = i + 1 + " / " + urls.length;
    }
    function close() {
      box.remove();
      document.body.style.overflow = "";
      document.removeEventListener("keydown", onKey);
    }
    function onKey(ev) {
      if (ev.key === "Escape") close();
      if (ev.key === "ArrowLeft") show(i - 1);
      if (ev.key === "ArrowRight") show(i + 1);
    }
    box.querySelector(".cm-lieu-lb-close").addEventListener("click", close);
    box.addEventListener("click", function (ev) {
      if (ev.target === box) close();
    });
    var prev = box.querySelector(".prev");
    var next = box.querySelector(".next");
    if (prev) prev.addEventListener("click", function () { show(i - 1); });
    if (next) next.addEventListener("click", function () { show(i + 1); });
    box.addEventListener(
      "wheel",
      function (ev) {
        ev.preventDefault();
        if (urls.length < 2) return;
        show(i + (ev.deltaY > 0 ? 1 : -1));
      },
      { passive: false }
    );
    document.addEventListener("keydown", onKey);
  }

  function galleryUrlsFromDom() {
    return Array.prototype.map
      .call(root.querySelectorAll("[data-gallery-i] img"), function (img) {
        return img.getAttribute("data-full") || img.currentSrc || img.src;
      })
      .filter(Boolean);
  }

  function bindGallery() {
    var imgs = root.querySelectorAll("[data-gallery-i]");
    if (!imgs.length) return;
    imgs.forEach(function (btn) {
      if (btn.getAttribute("data-bound") === "1") return;
      btn.setAttribute("data-bound", "1");
      btn.addEventListener("click", function () {
        var urls = galleryUrlsFromDom();
        var i = parseInt(btn.getAttribute("data-gallery-i"), 10) || 0;
        openLightbox(urls, i);
      });
    });
  }

  function isLocalMp4(url) {
    if (!url || /youtu\.?be|youtube\.com/i.test(url)) return false;
    return /\.mp4(\?|$)/i.test(url) || /\/assets\/video\//i.test(url);
  }

  function extractFramesFromMp4(url, count) {
    return new Promise(function (resolve) {
      var video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      video.crossOrigin = "anonymous";
      var done = false;
      var frames = [];
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        resolve(frames);
      }, 12000);

      function finish() {
        if (done) return;
        done = true;
        clearTimeout(timer);
        resolve(frames);
      }

      video.addEventListener("error", finish);
      video.addEventListener("loadedmetadata", function () {
        var dur = video.duration;
        if (!isFinite(dur) || dur <= 0.2) {
          finish();
          return;
        }
        var n = Math.max(1, Math.min(count || 4, 6));
        var times = [];
        for (var i = 0; i < n; i++) {
          times.push(Math.min(dur * 0.92, Math.max(0.15, ((i + 1) / (n + 1)) * dur)));
        }
        var canvas = document.createElement("canvas");
        var ctx = canvas.getContext("2d");
        var idx = 0;

        function grab() {
          if (idx >= times.length) {
            finish();
            return;
          }
          var seekTo = times[idx++];
          var onSeek = function () {
            video.removeEventListener("seeked", onSeek);
            try {
              var w = video.videoWidth || 1280;
              var h = video.videoHeight || 720;
              var maxW = 1200;
              if (w > maxW) {
                h = Math.round((h * maxW) / w);
                w = maxW;
              }
              canvas.width = w;
              canvas.height = h;
              ctx.drawImage(video, 0, 0, w, h);
              frames.push(canvas.toDataURL("image/jpeg", 0.82));
            } catch (e) {}
            grab();
          };
          video.addEventListener("seeked", onSeek);
          try {
            video.currentTime = seekTo;
          } catch (e) {
            finish();
          }
        }
        grab();
      });
      video.src = url;
      try {
        video.load();
      } catch (e) {
        finish();
      }
    });
  }

  function shotHtml(src, full, alt, idx, cls) {
    return (
      '<button type="button" class="' +
      (cls || "cm-lieu-shot") +
      '" data-gallery-i="' +
      idx +
      '"><img src="' +
      escapeHtml(src) +
      '" data-full="' +
      escapeHtml(full || src) +
      '" alt="' +
      escapeHtml(alt || "") +
      '" loading="' +
      (idx < 2 ? "eager" : "lazy") +
      '" decoding="async"></button>'
    );
  }

  function enrichGalleryFromVideos(videos, lieuName) {
    var grid = root.querySelector(".cm-lieu-split-gallery .grid");
    if (!grid) return;
    var mp4s = (videos || [])
      .map(function (v) {
        return v && v.url;
      })
      .filter(isLocalMp4);
    if (!mp4s.length) return;

    var existing = grid.querySelectorAll("[data-gallery-i]").length;
    var status = root.querySelector(".cm-lieu-gallery-status");
    if (status) status.hidden = false;

    var takeVideos = existing >= 6 ? 1 : Math.min(2, mp4s.length);
    var perVideo = existing === 0 ? 5 : existing < 4 ? 4 : 2;
    var chain = Promise.resolve([]);
    mp4s.slice(0, takeVideos).forEach(function (url) {
      chain = chain.then(function (acc) {
        return extractFramesFromMp4(url, perVideo).then(function (frames) {
          return acc.concat(frames);
        });
      });
    });

    chain.then(function (frames) {
      if (status) status.hidden = true;
      if (!frames.length) return;
      var start = grid.querySelectorAll("[data-gallery-i]").length;
      frames.forEach(function (dataUrl, i) {
        var idx = start + i;
        var cls = "cm-lieu-shot cm-lieu-shot--frame";
        if (idx === 0) cls += " is-hero";
        else if (idx % 3 === 0) cls += " is-tall";
        grid.insertAdjacentHTML(
          "beforeend",
          shotHtml(dataUrl, dataUrl, (lieuName || "Lieu") + " — extrait vidéo", idx, cls)
        );
      });
      bindGallery();
    });
  }

  var STYLE_EVT_LABELS = {
    moderne: "Moderne",
    traditionnel: "Traditionnel",
    nature_rural: "Nature / rural",
    desert: "Désert",
  };
  var BUDGET_EVT_LABELS = {
    tres_economique: "Très économique",
    economique: "Économique",
    moyen: "Moyen",
    eleve: "Élevé",
  };
  var SERVICE_EVT_LABELS = {
    transport: "Transport",
    bien_etre: "Bien-être",
    activites: "Activités",
    autre: "Autre",
  };

  function isNonEmptyText(v) {
    if (v == null) return false;
    if (typeof v === "number") return v > 0;
    if (Array.isArray(v)) return v.length > 0;
    return String(v).trim().length > 0;
  }

  function formatEuro(n) {
    var num = Number(n);
    if (!num) return "";
    return (
      Math.round(num)
        .toString()
        .replace(/\B(?=(\d{3})+(?!\d))/g, "\u00a0") + "\u00a0€"
    );
  }

  function textLinesHtml(raw) {
    return String(raw || "")
      .split(/\n+/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean)
      .map(function (line) {
        return "<li>" + escapeHtml(line) + "</li>";
      })
      .join("");
  }

  function eventBlockHtml(lieu) {
    var evt = lieu.evt || {};
    var style = evt.style_evenement || lieu.style_evenement || "";
    if (!style || style === "non_classe") return "";
    var extras = evt.extras || {};
    var extraKeys = [
      "menu_options",
      "divertissement_options",
      "decoration_options",
      "autres_services",
      "inclus_prix_base",
      "supplement_prix_base",
      "politique_annulation",
      "capacite_evenement_jour",
      "gestion_disponibilite_actuelle",
    ];
    var extrasFilled = extraKeys.some(function (k) {
      return isNonEmptyText(extras[k]);
    });
    if (!extrasFilled) return "";

    var labels = evt.extras_labels || {};
    var styleLabel = evt.style_evenement_label || STYLE_EVT_LABELS[style] || "";
    var budget = evt.budget_tier || lieu.budget_tier || "";
    var budgetLabel =
      evt.budget_tier_label || BUDGET_EVT_LABELS[budget] || "";
    var prix =
      evt.prix_privatisation_jour_soir ||
      lieu.prix_privatisation_jour_soir ||
      0;
    var pills = [];
    if (styleLabel) {
      pills.push("<span>" + escapeHtml(styleLabel) + "</span>");
    }
    if (budgetLabel) {
      pills.push("<span>Budget " + escapeHtml(budgetLabel.toLowerCase()) + "</span>");
    }
    if (extras.capacite_evenement_jour) {
      pills.push(
        "<span>Jusqu’à " +
          extras.capacite_evenement_jour +
          " pers. le jour</span>"
      );
    }
    var serviceLabels = labels.autres_services || [];
    if (!serviceLabels.length && extras.autres_services) {
      serviceLabels = extras.autres_services.map(function (c) {
        return SERVICE_EVT_LABELS[c] || c;
      });
    }
    serviceLabels.forEach(function (lab) {
      if (lab) pills.push("<span>" + escapeHtml(lab) + "</span>");
    });

    var rows = [];
    var prixLabel = formatEuro(prix);
    if (prixLabel) {
      rows.push(
        "<div><dt>Privatisation jour + soir</dt><dd>" +
          escapeHtml(prixLabel) +
          "</dd></div>"
      );
    }
    var inclus = textLinesHtml(extras.inclus_prix_base);
    if (inclus) {
      rows.push("<div><dt>Inclus</dt><dd><ul>" + inclus + "</ul></dd></div>");
    }
    var supp = textLinesHtml(extras.supplement_prix_base);
    if (supp) {
      rows.push("<div><dt>Suppléments</dt><dd><ul>" + supp + "</ul></dd></div>");
    }
    var menu = textLinesHtml(extras.menu_options);
    if (menu) {
      rows.push("<div><dt>Menu</dt><dd><ul>" + menu + "</ul></dd></div>");
    }
    var divert = textLinesHtml(extras.divertissement_options);
    if (divert) {
      rows.push(
        "<div><dt>Divertissement</dt><dd><ul>" + divert + "</ul></dd></div>"
      );
    }
    var deco = textLinesHtml(extras.decoration_options);
    if (deco) {
      rows.push("<div><dt>Décoration</dt><dd><ul>" + deco + "</ul></dd></div>");
    }
    if (extras.politique_annulation) {
      rows.push(
        "<div><dt>Annulation</dt><dd>" +
          escapeHtml(extras.politique_annulation) +
          "</dd></div>"
      );
    }
    var gestionLabel =
      labels.gestion_disponibilite_actuelle ||
      ({
        calendrier_papier: "Calendrier papier",
        whatsapp: "WhatsApp",
        autre_systeme: "Autre système",
        non_geree: "Non gérée",
      }[extras.gestion_disponibilite_actuelle] || "");
    if (gestionLabel && extras.gestion_disponibilite_actuelle !== "non_geree") {
      rows.push(
        "<div><dt>Disponibilité</dt><dd>Via " +
          escapeHtml(gestionLabel) +
          "</dd></div>"
      );
    }

    if (!pills.length && !rows.length) return "";

    return (
      '<section class="cm-lieu-evt" aria-labelledby="cmLieuEvtTitle">' +
      '<h2 id="cmLieuEvtTitle">Privatisation &amp; événements</h2>' +
      (pills.length
        ? '<div class="cm-lieu-evt-pills">' + pills.join("") + "</div>"
        : "") +
      (rows.length ? "<dl>" + rows.join("") + "</dl>" : "") +
      "</section>"
    );
  }

  function render(lieu) {
    if (MOSAIC_SLUGS[(lieu && lieu.slug) || slugFromPath()] || YSABELLA_ALIASES[(lieu && lieu.slug) || ""]) {
      renderMaquette(lieu);
      return;
    }
    setMeta(lieu);
    var photos = lieu.photos || [];
    var videos = lieu.videos || [];
    var placeBits = [];
    [lieu.district, lieu.street, lieu.city].forEach(function (bit) {
      bit = (bit || "").trim();
      if (!bit) return;
      if (placeBits.some(function (x) { return x.toLowerCase() === bit.toLowerCase(); })) return;
      placeBits.push(bit);
    });

    var heroSrc =
      (photos[0] && (photos[0].url_full || photos[0].url)) ||
      "/assets/img/hero.jpg";
    var lede = stripHtml(lieu.narrative_html).slice(0, 180);

    var actions = [];
    actions.push(
      '<a class="btn-primary" href="https://wa.me/212660159177?text=' +
        encodeURIComponent(
          "Bonjour Yasmine, je souhaite des infos sur " + (lieu.name || "ce lieu") + "."
        ) +
        '" target="_blank" rel="noopener noreferrer">Demander à Yasmine</a>'
    );
    if (lieu.name && /sacada/i.test(lieu.name)) {
      actions.push(
        '<a class="btn-ghost" href="/journee-piscine">Journée piscine</a>'
      );
    }
    /* Pas de lien Airbnb public — réservation via Coins / Yasmine uniquement.
       Airbnb sert seulement à la sync agenda partenaires (iCal) côté Odoo. */
    if (lieu.maps_url) {
      actions.push(
        '<a class="btn-ghost" href="' +
          escapeHtml(lieu.maps_url) +
          '" target="_blank" rel="noopener noreferrer">Ouvrir dans Maps</a>'
      );
    }

    var metaParts = [];
    if (lieu.pillar_label) {
      metaParts.push("<span><strong>Thème</strong> " + escapeHtml(lieu.pillar_label) + "</span>");
    }
    if (lieu.zone) {
      metaParts.push(
        "<span><strong>Zone</strong> " + escapeHtml(zoneLabel(lieu.zone)) + "</span>"
      );
    }
    if (lieu.capacity) {
      metaParts.push(
        "<span><strong>Capacité</strong> jusqu’à " + lieu.capacity + " pers.</span>"
      );
    }
    var occ = OCCASIONS_BY_SLUG[slugFromPath()] || [];
    if (occ.length) {
      metaParts.push(
        "<span><strong>Occasions</strong> " +
          occ
            .map(function (o) {
              return '<a href="' + o.href + '">' + escapeHtml(o.label) + "</a>";
            })
            .join(" · ") +
          "</span>"
      );
    }
    if (lieu.maps_url) {
      metaParts.push(
        '<a href="' + escapeHtml(lieu.maps_url) + '" target="_blank" rel="noopener noreferrer">Voir sur Google Maps</a>'
      );
    }

    /* Mobile : vidéo en hero si dispo. Desktop : photo hero. */
    var preferVideoHero =
      window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    var firstVideo = videos[0];
    var heroMediaHtml;
    if (preferVideoHero && firstVideo && firstVideo.url) {
      var heroYt = String(firstVideo.url).match(
        /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/))([\w-]{6,})/i
      );
      if (heroYt) {
        heroMediaHtml =
          '<div class="cm-lieu-hero-media is-video"><iframe src="https://www.youtube-nocookie.com/embed/' +
          heroYt[1] +
          '?rel=0&modestbranding=1" title="' +
          escapeHtml(firstVideo.title || lieu.name) +
          '" allow="encrypted-media; fullscreen" allowfullscreen loading="eager"></iframe></div>';
      } else {
        heroMediaHtml =
          '<div class="cm-lieu-hero-media is-video"><video controls playsinline preload="metadata" poster="' +
          escapeHtml(heroSrc) +
          '" src="' +
          escapeHtml(firstVideo.url) +
          '" aria-label="' +
          escapeHtml(firstVideo.title || lieu.name) +
          '"></video></div>';
      }
    } else {
      heroMediaHtml =
        '<div class="cm-lieu-hero-media"><img src="' +
        escapeHtml(heroSrc) +
        '" alt="' +
        escapeHtml(lieu.name) +
        '" fetchpriority="high"></div>';
    }

    var galleryShots = photos
      .map(function (ph, idx) {
        var cls = "cm-lieu-shot";
        if (idx === 0) cls += " is-hero";
        else if (idx % 5 === 2) cls += " is-tall";
        return shotHtml(
          seoPhotoUrl(ph, 720) || ph.url || ph.url_thumb,
          seoPhotoUrl(ph, 1600) || ph.url_full || ph.url || ph.url_thumb,
          photoAlt(ph, lieu.name),
          idx,
          cls
        );
      })
      .join("");

    var hasMp4 = videos.some(function (v) {
      return isLocalMp4(v && v.url);
    });
    var galleryEmptyHint =
      !photos.length && hasMp4
        ? '<p class="cm-lieu-gallery-status">Extraction des photos depuis la vidéo…</p>'
        : hasMp4
          ? '<p class="cm-lieu-gallery-status" hidden>Ajout d’extraits vidéo…</p>'
          : !photos.length
            ? '<p class="sub">Photos à venir.</p>'
            : "";

    /* Bloc vidéo séparé : mobile = avant les photos ; desktop = sous le texte.
       Si la 1re vidéo est déjà en hero (mobile), on ne la répète pas. */
    var videosForBlock =
      preferVideoHero && firstVideo && firstVideo.url ? videos.slice(1) : videos;
    var videosBlock = videosForBlock.length
      ? '<div class="cm-lieu-inline-videos" aria-labelledby="cmLieuVideosTitle">' +
        '<h2 id="cmLieuVideosTitle">En vidéo</h2>' +
        '<p class="sub">Coup de cœur et ambiance du lieu.</p>' +
        '<div class="cm-lieu-inline-videos-grid">' +
        videosForBlock.map(videoBlock).join("") +
        "</div></div>"
      : "";
    var splitHasVideos = !!videosBlock;

    root.innerHTML =
      '<section class="cm-lieu-hero">' +
      heroMediaHtml +
      '<div class="cm-lieu-hero-copy">' +
      '<p class="crumb"><a href="/carte">Carte</a><span>/</span>' +
      '<a href="/guide-marrakech">Guide</a><span>/</span>' +
      escapeHtml(lieu.name) +
      "</p>" +
      '<p class="eyebrow">Coins Marocain · Marrakech</p>' +
      "<h1>" +
      escapeHtml(pageH1(lieu)) +
      "</h1>" +
      (pageLede(lieu)
        ? '<p class="lede">' + escapeHtml(pageLede(lieu)) + "</p>"
        : lede
          ? '<p class="lede">' + escapeHtml(lede) + (lede.length >= 180 ? "…" : "") + "</p>"
          : "") +
      (placeBits.length
        ? '<p class="place">' + escapeHtml(placeBits.join(" — ")) + "</p>"
        : "") +
      '<div class="actions">' +
      actions.join("") +
      "</div></div></section>" +
      (metaParts.length
        ? '<div class="cm-lieu-meta">' + metaParts.join("") + "</div>"
        : "") +
      '<section class="cm-lieu-split' +
      (splitHasVideos ? " has-videos" : "") +
      '" aria-label="Présentation du lieu">' +
      videosBlock +
      '<div class="cm-lieu-split-text">' +
      (lieu.narrative_html
        ? '<div class="lead-html">' + lieu.narrative_html + "</div>"
        : "") +
      '<div class="desc-html">' +
      (lieu.description_html || "<p>Description à venir.</p>") +
      "</div>" +
      eventBlockHtml(lieu) +
      '<p class="cm-lieu-maillage">Continuer : <a href="/carte">carte en vidéo</a> · '
      '<a href="/villas-riads-marrakech">villas &amp; riads</a> · ' +
      '<a href="/evenements">événements</a> · ' +
      '<a href="/evenements/mariages">mariage</a> · ' +
      '<a href="/evenements/seminaires-entreprise">séminaire</a> · ' +
      '<a href="/evenements/groupes-amis-famille">groupe</a> · ' +
      '<a href="/guide-marrakech">escapades</a> · ' +
      '<a href="/contact">contact</a>.</p>' +
      "</div>" +
      '<aside class="cm-lieu-split-side">' +
      '<div class="cm-lieu-book" id="cmLieuBook" aria-labelledby="cmLieuBookTitle">' +
      '<h2 id="cmLieuBookTitle">Réserver</h2>' +
      '<p class="sub">Choisissez vos dates' +
      (lieu.capacity ? " · jusqu’à " + lieu.capacity + " pers." : "") +
      "</p>" +
      '<div class="cm-lieu-book-cal">' +
      '<div class="cm-lieu-book-cal-nav">' +
      '<button type="button" id="cmLieuBookPrev" aria-label="Mois précédent">‹</button>' +
      '<div class="cm-lieu-book-cal-title" id="cmLieuBookCalTitle"></div>' +
      '<button type="button" id="cmLieuBookNext" aria-label="Mois suivant">›</button>' +
      "</div>" +
      '<p class="cm-lieu-book-range" id="cmLieuBookRange"></p>' +
      '<div class="cm-lieu-book-grid" id="cmLieuBookGrid" role="grid"></div>' +
      "</div>" +
      '<label class="cm-lieu-book-field">Nombre de personnes' +
      '<input type="number" id="cmLieuBookGuests" min="1" max="' +
      (lieu.capacity || 500) +
      '" step="1" inputmode="numeric" placeholder="ex. 8">' +
      "</label>" +
      '<div class="cm-lieu-book-event" id="cmLieuBookEvent" hidden>' +
      '<span class="cm-lieu-book-label">Type d’événement</span>' +
      '<div class="cm-lieu-book-chips" id="cmLieuBookEventChips" role="group"></div>' +
      "</div>" +
      '<button type="button" class="cm-lieu-book-submit" id="cmLieuBookSubmit">Réserver</button>' +
      '<p class="cm-lieu-book-hint">Budget à partir de 500 DH · confirmation avec Yasmine</p>' +
      "</div>" +
      '<div class="cm-lieu-split-gallery" aria-labelledby="cmLieuGalleryTitle">' +
      '<h2 id="cmLieuGalleryTitle">' +
      escapeHtml(galleryH2Title(lieu)) +
      "</h2>" +
      '<p class="sub">Photos — cliquez pour agrandir.</p>' +
      galleryEmptyHint +
      '<div class="grid">' +
      galleryShots +
      "</div></div></aside></section>";

    bindGallery();
    mountBookWidget(lieu);
    enrichGalleryFromVideos(videos, lieu.name);

    if (document.body) {
      document.body.setAttribute(
        "data-wa-msg",
        "Bonjour Yasmine, je souhaite des infos sur " + (lieu.name || "ce lieu") + "."
      );
      var pillar = (lieu.pillar || lieu.theme || "").toString();
      var interestMap = {
        hebergement: "piscine",
        villas_riads: "piscine",
        bien_etre: "bien_etre",
        route_gourmande: "gastronomie",
        resto: "gastronomie",
        experiences: "desert",
        plein_air: "desert",
        evenements: "evenements",
      };
      if (interestMap[pillar]) {
        document.body.setAttribute("data-planner-interests", interestMap[pillar]);
      }
      if (pillar === "evenements") {
        document.body.setAttribute("data-planner-event", "1");
      } else {
        document.body.removeAttribute("data-planner-event");
      }
    }
  }

  function loadPlanner(cb) {
    if (window.CoinsPlanner) {
      cb();
      return;
    }
    if (!document.querySelector('link[href*="cm-planner.css"]')) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/assets/cm-planner.css?v=cm149";
      document.head.appendChild(link);
    }
    var existing = document.querySelector('script[src*="cm-planner.js"]');
    if (existing) {
      existing.addEventListener("load", cb);
      return;
    }
    var s = document.createElement("script");
    s.src = "/assets/cm-planner.js?v=cm149";
    s.async = true;
    s.onload = cb;
    document.head.appendChild(s);
  }

  function mountBookWidget(lieu) {
    var box = document.getElementById("cmLieuBook");
    if (!box || box.getAttribute("data-bound") === "1") return;
    box.setAttribute("data-bound", "1");

    var months = [
      "janvier", "février", "mars", "avril", "mai", "juin",
      "juillet", "août", "septembre", "octobre", "novembre", "décembre",
    ];
    var dow = ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"];
    var eventTypes = [
      { v: "mariage", l: "Mariage" },
      { v: "evjf", l: "EVJF / EVG" },
      { v: "anniversaire", l: "Anniversaire" },
      { v: "soiree", l: "Soirée" },
      { v: "team_building", l: "Team building" },
      { v: "gala", l: "Gala" },
      { v: "privatisation", l: "Privatisation" },
      { v: "autre", l: "Autre" },
    ];

    var book = {
      viewY: new Date().getFullYear(),
      viewM: new Date().getMonth(),
      start: null,
      end: null,
      eventType: "",
    };

    var titleEl = document.getElementById("cmLieuBookCalTitle");
    var rangeEl = document.getElementById("cmLieuBookRange");
    var gridEl = document.getElementById("cmLieuBookGrid");
    var guestsEl = document.getElementById("cmLieuBookGuests");
    var eventWrap = document.getElementById("cmLieuBookEvent");
    var eventChips = document.getElementById("cmLieuBookEventChips");
    var submitBtn = document.getElementById("cmLieuBookSubmit");

    var isEvent =
      (lieu.pillar || lieu.theme || "") === "evenements" ||
      /evenement/i.test(lieu.pillar_label || "");
    if (isEvent && eventWrap && eventChips) {
      eventWrap.hidden = false;
      eventTypes.forEach(function (it) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cm-lieu-book-chip";
        btn.setAttribute("data-event", it.v);
        btn.textContent = it.l;
        btn.addEventListener("click", function () {
          book.eventType = book.eventType === it.v ? "" : it.v;
          eventChips.querySelectorAll(".cm-lieu-book-chip").forEach(function (b) {
            b.classList.toggle("on", b.getAttribute("data-event") === book.eventType);
          });
        });
        eventChips.appendChild(btn);
      });
    }

    function pad(n) {
      return n < 10 ? "0" + n : String(n);
    }
    function ymd(d) {
      return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
    }
    function sameDay(a, b) {
      return a && b && ymd(a) === ymd(b);
    }
    function fmt(d) {
      return pad(d.getDate()) + "/" + pad(d.getMonth() + 1);
    }
    function today() {
      var t = new Date();
      return new Date(t.getFullYear(), t.getMonth(), t.getDate());
    }

    function syncRange() {
      if (!rangeEl) return;
      if (book.start && book.end) {
        rangeEl.textContent = "Du " + fmt(book.start) + " au " + fmt(book.end);
      } else if (book.start) {
        rangeEl.textContent = "Arrivée " + fmt(book.start) + " — choisissez le départ";
      } else {
        rangeEl.textContent = "Sélectionnez l’arrivée puis le départ";
      }
    }

    function renderCal() {
      if (!gridEl || !titleEl) return;
      titleEl.textContent = months[book.viewM] + " " + book.viewY;
      gridEl.innerHTML = "";
      dow.forEach(function (d) {
        var el = document.createElement("div");
        el.className = "cm-lieu-book-dow";
        el.textContent = d;
        gridEl.appendChild(el);
      });
      var first = new Date(book.viewY, book.viewM, 1);
      var startDow = (first.getDay() + 6) % 7;
      var daysInMonth = new Date(book.viewY, book.viewM + 1, 0).getDate();
      var i;
      for (i = 0; i < startDow; i++) {
        var empty = document.createElement("div");
        empty.className = "cm-lieu-book-day out";
        gridEl.appendChild(empty);
      }
      var t0 = today();
      for (i = 1; i <= daysInMonth; i++) {
        (function (day) {
          var d = new Date(book.viewY, book.viewM, day);
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "cm-lieu-book-day";
          btn.textContent = String(day);
          if (d < t0) {
            btn.disabled = true;
            btn.classList.add("past");
          }
          if (sameDay(d, book.start) || sameDay(d, book.end)) btn.classList.add("on");
          if (
            book.start &&
            book.end &&
            d > book.start &&
            d < book.end
          ) {
            btn.classList.add("in");
          }
          btn.addEventListener("click", function () {
            if (!book.start || (book.start && book.end)) {
              book.start = d;
              book.end = null;
            } else if (d < book.start) {
              book.end = book.start;
              book.start = d;
            } else if (sameDay(d, book.start)) {
              book.start = null;
              book.end = null;
            } else {
              book.end = d;
            }
            renderCal();
            syncRange();
          });
          gridEl.appendChild(btn);
        })(i);
      }
      syncRange();
    }

    document.getElementById("cmLieuBookPrev").addEventListener("click", function () {
      book.viewM -= 1;
      if (book.viewM < 0) {
        book.viewM = 11;
        book.viewY -= 1;
      }
      renderCal();
    });
    document.getElementById("cmLieuBookNext").addEventListener("click", function () {
      book.viewM += 1;
      if (book.viewM > 11) {
        book.viewM = 0;
        book.viewY += 1;
      }
      renderCal();
    });

    submitBtn.addEventListener("click", function () {
      var guests = (guestsEl && guestsEl.value) || "";
      loadPlanner(function () {
        if (!window.CoinsPlanner) return;
        window.CoinsPlanner.open({
          start: book.start ? ymd(book.start) : null,
          end: book.end ? ymd(book.end) : null,
          guests: guests,
          eventType: book.eventType || undefined,
          lieuName: lieu.name || "",
          budget: "500_1500",
          focusContact: true,
          interests: isEvent
            ? ["evenements"]
            : undefined,
        });
      });
    });

    renderCal();
  }

  function renderError(msg) {
    root.innerHTML =
      '<div class="cm-lieu-error"><h1>Fiche introuvable</h1><p>' +
      escapeHtml(msg) +
      '</p><p><a href="/carte">Retour à la carte</a></p></div>';
  }

  var MOSAIC_SLUGS = {
    "la-casa-ysabella": true,
    "riad-la-casa-ysabella-marrakech": true,
    "riad-medina-marrakech-la-casa-ysabella": true,
    ysabella: true,
    "casa-ysabella": true,
    "la-casa-isabella": true,
    "casa-isabella": true,
    "chateau-nougat": true,
    "riad-asrari": true,
    "riad-asrari-medina-marrakech": true,
  };

  function isNougatLieu(lieu) {
    var s = String((lieu && lieu.slug) || slugFromPath() || "").toLowerCase();
    return s === "chateau-nougat";
  }

  var NOUGAT_VIDEO_V = "cm189";
  var NOUGAT_INTRO_REEL =
    "/assets/video/chateau-nougat-intro-reel.mp4?v=" + NOUGAT_VIDEO_V;
  var NOUGAT_ROOM_CLIPS = [
    "/assets/video/chateau-nougat-chambre-1.mp4?v=" + NOUGAT_VIDEO_V,
    "/assets/video/chateau-nougat-chambre-2.mp4?v=" + NOUGAT_VIDEO_V,
    "/assets/video/chateau-nougat-chambre-3.mp4?v=" + NOUGAT_VIDEO_V,
    "/assets/video/chateau-nougat-chambre-4.mp4?v=" + NOUGAT_VIDEO_V,
    "/assets/video/chateau-nougat-chambre-5.mp4?v=" + NOUGAT_VIDEO_V,
    "/assets/video/chateau-nougat-chambre-6.mp4?v=" + NOUGAT_VIDEO_V,
  ];
  var NOUGAT_MOTION = [
    { url: NOUGAT_INTRO_REEL, title: "Intro Château Nougat" },
    { url: NOUGAT_ROOM_CLIPS[0], title: "Chambre — Ken Burns" },
    { url: NOUGAT_ROOM_CLIPS[5], title: "Lounge — Ken Burns" },
    { url: NOUGAT_ROOM_CLIPS[2], title: "Espace nuit — Ken Burns" },
  ];

  function nougatVideos(lieuVideos) {
    var list = (lieuVideos || []).filter(function (v) { return v && v.url; });
    if (list.length) return list;
    return NOUGAT_MOTION.slice();
  }
  var MOSAIC_CATS = [
    ["chambres", "Chambres"],
    ["aires_communes", "Aires communes"],
    ["restauration", "Restauration"],
    ["exterieur_piscine", "Extérieur / Piscine"],
    ["bien_etre", "Bien-être / Spa"],
  ];
  var YSABELLA_CATS = {
    50: ["aires_communes"],
    51: ["aires_communes"],
    52: ["restauration"],
    53: ["aires_communes"],
    54: ["aires_communes"],
    55: ["aires_communes"],
    56: ["aires_communes"],
    57: ["restauration", "aires_communes"],
    58: ["restauration"],
    59: ["restauration"],
    60: ["restauration"],
    61: ["restauration"],
    62: ["restauration", "aires_communes"],
    63: ["restauration"],
    64: ["aires_communes"],
    27: ["chambres"],
    28: ["chambres"],
    29: ["chambres"],
    32: ["chambres"],
    33: ["chambres"],
    35: ["chambres"],
    36: ["chambres"],
    37: ["chambres"],
    38: ["chambres"],
    42: ["chambres"],
    43: ["chambres"],
    46: ["chambres"],
  };

  function photoById(photos, id) {
    for (var i = 0; i < photos.length; i++) {
      if (String(photos[i].id) === String(id)) return photos[i];
    }
    return null;
  }

  function photoSrc(ph, key) {
    if (!ph) return "";
    var w = key === "url_thumb" ? 360 : key === "url" ? 720 : 1600;
    return seoPhotoUrl(ph, w) || ph.url_full || ph[key] || ph.url || ph.url_thumb || "";
  }

  function photoCodes(ph, slug) {
    var codes = [];
    var raw = ph.category_codes || ph.categories || [];
    raw.forEach(function (item) {
      var code = item && item.code ? item.code : String(item || "");
      if (code && codes.indexOf(code) === -1) codes.push(code);
    });
    if (ph.room_id && codes.indexOf("chambres") === -1) codes.unshift("chambres");
    if (!codes.length && slug === "la-casa-ysabella") {
      var mapped = YSABELLA_CATS[ph.id] || YSABELLA_CATS[String(ph.id)] || [];
      mapped.forEach(function (c) {
        if (codes.indexOf(c) === -1) codes.push(c);
      });
    }
    return codes;
  }

  function pickMosaicHero(photos, slug) {
    var main = photos[0] || {};
    var roomPh = {};
    var terrace = {};
    var i;
    for (i = 0; i < photos.length; i++) {
      if (photos[i].is_signature) {
        main = photos[i];
        break;
      }
    }
    if (slug === "la-casa-ysabella" && !main.is_signature) {
      main = photoById(photos, 53) || main;
      roomPh = photoById(photos, 27) || {};
      terrace = photoById(photos, 62) || {};
    }
    /* Nougat : éviter le cover rooftop fisheye — chambre + lounge + intérieur. */
    if (slug === "chateau-nougat") {
      /* 147 cover suite vitrée · 151 chambre floral · 148 piscine */
      main = photoById(photos, 147) || main;
      roomPh = photoById(photos, 151) || roomPh;
      terrace = photoById(photos, 148) || terrace;
    }
    if (!roomPh.url) {
      for (i = 0; i < photos.length; i++) {
        if (photos[i] === main) continue;
        if (photos[i].room_id || photoCodes(photos[i], slug).indexOf("chambres") !== -1) {
          roomPh = photos[i];
          break;
        }
      }
    }
    if (!terrace.url) {
      for (i = 0; i < photos.length; i++) {
        if (photos[i] === main || photos[i] === roomPh) continue;
        var c = photoCodes(photos[i], slug);
        if (c.indexOf("aires_communes") !== -1 || c.indexOf("exterieur_piscine") !== -1) {
          terrace = photos[i];
          break;
        }
      }
    }
    if (!terrace.url) {
      for (i = 0; i < photos.length; i++) {
        if (photos[i] !== main && photos[i] !== roomPh) {
          terrace = photos[i];
          break;
        }
      }
    }
    return { main: main, room: roomPh, terrace: terrace };
  }

  function renderMaquette(lieu) {
    setMeta(lieu);
    var slug = lieu.slug || slugFromPath();
    var photos = (lieu.photos || []).filter(function (p) { return p.url || p.url_full; });
    var rooms = lieu.rooms || [];
    var hero = pickMosaicHero(photos, slug);
    var name = lieu.name || "Lieu";
    var price = Number(lieu.price_from || 0);
    var currencyRef = fxNorm(lieu.currency || lieu.currency_ref || root.getAttribute("data-currency-ref") || FX_REF);
    /* Privatisation Nougat : afficher le tarif jour si présent (EUR), pas seulement le BAR chambre. */
    if (slug === "chateau-nougat" && Number(lieu.tarif_privatisation_jour || 0) > 0) {
      price = Number(lieu.tarif_privatisation_jour);
      currencyRef = "EUR";
    }
    root.setAttribute("data-currency-ref", currencyRef);
    var priceKind = "from";
    var priceLabel = price ? fxFormat(price, currencyRef, "from", false) : "Tarif sur demande";
    if (slug === "chateau-nougat" && Number(lieu.tarif_privatisation_jour || 0) > 0) {
      priceKind = "day";
      priceLabel = fxFormat(price, currencyRef, "day", false);
    }
    var priceFromAttrs = price
      ? ' data-price-ref="' + Math.round(price) + '" data-currency-ref="' + escapeHtml(currencyRef) + '" data-price-kind="' + priceKind + '"'
      : "";
    var waRes =
      "https://wa.me/212660159177?text=" +
      encodeURIComponent("Bonjour Yasmine, je souhaite réserver " + name + ".");
    var waDispo =
      "https://wa.me/212660159177?text=" +
      encodeURIComponent("Bonjour Yasmine, je souhaite les disponibilités de " + name + ".");
    var moreN = Math.max(
      0,
      photos.length -
        [hero.main, hero.room, hero.terrace].filter(function (p) { return p && p.url; }).length
    );
    var videos = nougatVideos(lieu.videos);
    if (slug !== "chateau-nougat") {
      videos = (lieu.videos || []).filter(function (v) { return v && v.url; });
    }
    var firstVid = videos[0];
    var heroPoster = escapeHtml(photoSrc(hero.main) || "/assets/img/hero.jpg");
    var videoTile = firstVid && firstVid.url
      ? '<div class="cm-fiche-hero-tile is-video" aria-label="Reel d’introduction">' +
        '<video autoplay muted loop playsinline poster="' +
        heroPoster +
        '" src="' +
        escapeHtml(firstVid.url) +
        '" aria-label="' +
        escapeHtml(firstVid.title || name + " — intro") +
        '"></video></div>'
      : '<div class="cm-fiche-hero-tile is-video-placeholder" role="img" aria-label="Vidéo d’introduction à venir">' +
        '<span class="cm-fiche-play" aria-hidden="true"></span>' +
        '<span class="cm-fiche-video-label">Vidéo d’intro — à venir</span>' +
        '<p class="cm-fiche-video-hint">Pas encore de vidéo pour ce lieu. L’emplacement reste réservé, ce n’est pas une lecture.</p></div>';
    var motionHtml = videos.length
      ? '<section class="cm-fiche-section cm-fiche-motion" id="videos">' +
        "<h2>Le lieu en mouvement</h2>" +
        '<p class="cm-fiche-motion-sub">Les photos de la maison, en Ken Burns — clips de 8 secondes.</p>' +
        '<div class="cm-fiche-motion-grid">' +
        videos
          .map(function (v) {
            return (
              '<figure class="cm-fiche-motion-clip"><video controls playsinline preload="metadata" src="' +
              escapeHtml(v.url) +
              '"></video><figcaption>' +
              escapeHtml(v.title || "Clip") +
              "</figcaption></figure>"
            );
          })
          .join("") +
        "</div></section>"
      : "";
    var roomTile = hero.room && photoSrc(hero.room)
      ? '<button type="button" class="cm-fiche-hero-tile" data-full="' +
        escapeHtml(photoSrc(hero.room)) +
        '"><img src="' +
        escapeHtml(seoPhotoUrl(hero.room, 720) || hero.room.url || hero.room.url_thumb || photoSrc(hero.room)) +
        '" alt="' +
        escapeHtml(photoAlt(hero.room, "Chambre")) +
        '"' +
        cropAttr(hero.room) +
        "></button>"
      : "";
    var terraceTile = hero.terrace && photoSrc(hero.terrace)
      ? '<a class="cm-fiche-hero-tile is-more" href="#galerie"><img src="' +
        escapeHtml(seoPhotoUrl(hero.terrace, 720) || hero.terrace.url || hero.terrace.url_thumb || photoSrc(hero.terrace)) +
        '" alt="' +
        escapeHtml(photoAlt(hero.terrace, "Terrasse")) +
        '"' +
        cropAttr(hero.terrace) +
        '><span class="cm-fiche-more-badge">+' +
        moreN +
        " photos</span></a>"
      : "";
    var roomCards = rooms
      .map(function (r, roomIdx) {
        var titre = String(r.nom || r.name || "").replace(/\s+/g, " ").trim();
        if (titre && titre === titre.toUpperCase()) {
          titre = titre.charAt(0) + titre.slice(1).toLowerCase();
        }
        var prix = Number(r.price_per_night || 0);
        var roomCur = fxNorm(r.currency || currencyRef);
        var rph = null;
        var ri;
        for (ri = 0; ri < photos.length; ri++) {
          if (r.id && photos[ri].room_id && Number(photos[ri].room_id) === Number(r.id)) {
            rph = photos[ri];
            break;
          }
        }
        /* Fallback : photos catégorie chambres (Nougat & co. sans room_id). */
        if (!rph) {
          var chambrePool = photos.filter(function (ph) {
            return photoCodes(ph, slug).indexOf("chambres") !== -1;
          });
          if (chambrePool.length) {
            rph = chambrePool[roomIdx % chambrePool.length];
          }
        }
        var photoHtml;
        var nougatClip =
          slug === "chateau-nougat"
            ? NOUGAT_ROOM_CLIPS[roomIdx % NOUGAT_ROOM_CLIPS.length]
            : "";
        if (nougatClip) {
          photoHtml =
            '<div class="cm-fiche-room-photo"><video muted loop playsinline preload="metadata" poster="' +
            escapeHtml(
              (rph && (seoPhotoUrl(rph, 720) || rph.url || rph.url_thumb)) ||
                photoSrc(hero.main) ||
                ""
            ) +
            '" src="' +
            escapeHtml(nougatClip) +
            '" data-full="' +
            escapeHtml((rph && photoSrc(rph)) || nougatClip) +
            '" aria-label="' +
            escapeHtml(titre || "Chambre") +
            '"></video></div>';
        } else if (rph) {
          photoHtml =
            '<div class="cm-fiche-room-photo"><img src="' +
            escapeHtml(seoPhotoUrl(rph, 720) || rph.url || rph.url_thumb) +
            '" data-full="' +
            escapeHtml(photoSrc(rph)) +
            '" alt="' +
            escapeHtml(photoAlt(rph, titre)) +
            '" width="480" height="480"' +
            cropAttr(rph) +
            "></div>";
        } else {
          photoHtml =
            '<div class="cm-fiche-room-photo is-missing"><p>Pas de photo clairement identifiable pour cette chambre.</p></div>';
        }
        return (
          "<article" +
          roomCatalogAttrs(r.id) +
          ">" +
          photoHtml +
          "<h3>" +
          escapeHtml(titre) +
          "</h3>" +
          '<p class="cm-fiche-room-price"' +
          (prix
            ? ' data-price-ref="' +
              Math.round(prix) +
              '" data-currency-ref="' +
              escapeHtml(roomCur) +
              '" data-price-kind="room"'
            : "") +
          ">" +
          escapeHtml(prix ? fxFormat(prix, roomCur, "room", false) : "Sur devis") +
          '</p><p class="cm-fiche-room-meta">' +
          escapeHtml(String(r.sleeps || 0)) +
          " pers.</p>" +
          roomDescMarkup(stripHtml(r.description || ""), r.id) +
          "</article>"
        );
      })
      .join("");
    var sections = "";
    MOSAIC_CATS.forEach(function (pair) {
      var group = photos.filter(function (ph) {
        return photoCodes(ph, slug).indexOf(pair[0]) !== -1;
      });
      if (!group.length) return;
      sections +=
        '<div class="cm-fiche-gal-section" id="galerie-' +
        pair[0] +
        '"><h3>' +
        escapeHtml(gallerySectionHeading(pair[0], lieu, pair[1])) +
        '</h3><div class="cm-fiche-seo-photos">' +
        group
          .map(function (ph) {
            var alt = photoAlt(ph, name);
            return (
              '<img src="' +
              escapeHtml(seoPhotoUrl(ph, 720) || ph.url || ph.url_thumb) +
              '" data-full="' +
              escapeHtml(photoSrc(ph)) +
              '" alt="' +
              escapeHtml(alt) +
              '" title="' +
              escapeHtml(alt) +
              '" loading="lazy"' +
              cropAttr(ph) +
              ">"
            );
          })
          .join("") +
        "</div></div>";
    });
    var desc = lieu.description_html || lieu.narrative_html || "";
    var banner =
      slug === "la-casa-ysabella"
        ? '<p class="cm-fiche-newmark cm-fiche-newmark--published">Fiche publiée — réservation directe via Coins Marocain.</p>'
        : "";
    root.className = "cm-lieu cm-fiche";
    root.setAttribute("data-prerendered", "1");
    root.setAttribute("data-slug", slug);
    root.innerHTML =
      banner +
      '<section class="cm-fiche-hero cm-fiche-hero--mosaic" aria-label="Galerie">' +
      '<div class="cm-fiche-hero-main"><img src="' +
      escapeHtml(photoSrc(hero.main) || "/assets/img/hero.jpg") +
      '" alt="' +
      escapeHtml(photoAlt(hero.main, name + " — patio et fontaine")) +
      '" fetchpriority="high"' +
      cropAttr(hero.main) +
      "></div>" +
      videoTile +
      '<div class="cm-fiche-hero-stack">' +
      roomTile +
      terraceTile +
      "</div></section>" +
      '<div class="cm-fiche-layout"><div class="cm-fiche-main">' +
      '<p class="cm-fiche-eyebrow">Coins Marocain · Marrakech</p><h1>' +
      escapeHtml(pageH1(lieu)) +
      "</h1>" +
      (pageLede(lieu)
        ? '<p class="cm-fiche-lede">' + escapeHtml(pageLede(lieu)) + "</p>"
        : "") +
      '<p class="cm-fiche-place">' +
      escapeHtml(
        (function () {
          var bits = [];
          [lieu.district, lieu.city || "Marrakech"].forEach(function (bit) {
            bit = String(bit || "").trim();
            if (!bit) return;
            if (bits.some(function (x) { return x.toLowerCase() === bit.toLowerCase(); })) return;
            bits.push(bit);
          });
          return bits.join(" — ");
        })()
      ) +
      "</p>" +
      '<div class="cm-fiche-desc">' +
      (desc.indexOf("<p") !== -1 ? desc : "<p>" + escapeHtml(stripHtml(desc)) + "</p>") +
      "</div>" +
      motionHtml +
      (roomCards
        ? '<section class="cm-fiche-section" id="chambres"><h2>' +
          escapeHtml(roomsH2Title(lieu)) +
          '</h2><div class="cm-fiche-rooms">' +
          roomCards +
          "</div></section>"
        : "") +
      '</div><aside class="cm-fiche-book" id="cmFicheBook"><p class="cm-fiche-price"' +
      priceFromAttrs +
      ">" +
      escapeHtml(priceLabel) +
      "</p>" +
      fxSelectorHtml(currencyRef) +
      '<form class="cm-fiche-book-form" id="cmFicheBookForm" data-place="' +
      escapeHtml(name) +
      '" data-capacity="' +
      escapeHtml(String(lieu.capacity || 22)) +
      '"><div class="cm-fiche-book-dates"><label>Arrivée<input type="date" id="cmBookIn" name="arrivee" autocomplete="off"></label><label>Départ<input type="date" id="cmBookOut" name="depart" autocomplete="off"></label></div><label>Voyageurs<input type="number" id="cmBookGuests" name="voyageurs" min="1" max="' +
      escapeHtml(String(lieu.capacity || 22)) +
      '" value="2"></label><p class="cm-fiche-book-note" id="cmBookNote">Yasmine confirme les dates — pas de paiement en ligne.</p></form><a class="cm-fiche-btn primary" id="cmBookWaRes" href="' +
      escapeHtml(waRes) +
      '" target="_blank" rel="noopener">Réserver via WhatsApp</a>' +
      '<a class="cm-fiche-btn ghost" id="cmBookWaDispo" href="' +
      escapeHtml(waDispo) +
      '" target="_blank" rel="noopener">Demander disponibilité</a>' +
      '<p class="cm-fiche-hint">Les dates et le nombre de voyageurs partent dans le message WhatsApp.</p></aside></div>' +
      '<section class="cm-fiche-section cm-fiche-gallery" id="galerie"><h2>' +
      escapeHtml(galleryH2Title(lieu)) +
      '</h2><p class="cm-fiche-gallery-sub">' +
      escapeHtml(galleryH2Subtitle(lieu, photos.length)) +
      "</p>" +
      (sections || "") +
      "</section>";
    bindPrerenderedFiche();
  }

  var slug = slugFromPath();
  if (!slug) {
    renderError("Aucun lieu précisé dans l’URL.");
    return;
  }


  function bindPrerenderedFiche() {
    var imgs = root.querySelectorAll(
      ".cm-fiche-seo-photos img, .cm-fiche-hero-main img, .cm-fiche-thumb img, .cm-fiche-room-photo img, .cm-fiche-room-photo video"
    );
    var urls = [];
    imgs.forEach(function (img) {
      var u = img.getAttribute("data-full") || img.getAttribute("src");
      if (u && urls.indexOf(u) === -1) urls.push(u);
    });
    root.querySelectorAll(".cm-fiche-seo-photos img, .cm-fiche-thumb:not(.is-video)").forEach(function (el) {
      el.addEventListener("click", function () {
        var full = el.getAttribute("data-full") || (el.tagName === "IMG" ? el.getAttribute("src") : "");
        var i = Math.max(0, urls.indexOf(full));
        if (typeof openLightbox === "function") openLightbox(urls, i);
      });
    });
    root.querySelectorAll(".cm-fiche-hero-tile:not(.is-video):not(.is-video-placeholder):not(.is-more)").forEach(function (el) {
      el.addEventListener("click", function () {
        var img = el.querySelector("img");
        var full = el.getAttribute("data-full") || (img && (img.getAttribute("data-full") || img.getAttribute("src"))) || "";
        var i = Math.max(0, urls.indexOf(full));
        if (typeof openLightbox === "function") openLightbox(urls, i);
      });
    });

    function ensureHeroKenBurns() {
      var main = root.querySelector(".cm-fiche-hero-main");
      var vidBtn = root.querySelector(".cm-fiche-hero-tile.is-video");
      var u = vidBtn && vidBtn.getAttribute("data-video");
      if (!main || !u || /youtu/i.test(u)) return;
      if (main.querySelector("video[src]")) return;
      var poster = "";
      var img = main.querySelector("img");
      if (img) poster = img.getAttribute("src") || "";
      main.innerHTML =
        '<video autoplay muted loop playsinline poster="' +
        escapeHtml(poster) +
        '" src="' +
        escapeHtml(u) +
        '"></video>';
    }
    ensureHeroKenBurns();
    function injectMotionFromApi() {
      var slug = root.getAttribute("data-slug") || "";
      if (slug.indexOf("asrari") >= 0) return;
      if (root.querySelector(".cm-fiche-motion")) return;
      if (!slug) return;
      fetch("/coins/api/carte/lieu/" + slug, { headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          var videos = ((data && data.lieu) || {}).videos || [];
          videos = videos.filter(function (v) { return v && v.url; });
          if (!videos.length || root.querySelector(".cm-fiche-motion")) return;
          var grid = videos
            .map(function (v) {
              return (
                '<figure class="cm-fiche-motion-clip"><video controls playsinline preload="metadata" src="' +
                escapeHtml(v.url) +
                '"></video><figcaption>' +
                escapeHtml(v.title || "Clip") +
                "</figcaption></figure>"
              );
            })
            .join("");
          var sec = document.createElement("section");
          sec.className = "cm-fiche-section cm-fiche-motion";
          sec.id = "videos";
          sec.innerHTML =
            "<h2>Le riad en mouvement</h2>" +
            '<p class="cm-fiche-motion-sub">Les photos de la maison, en Ken Burns — clips de 8 secondes.</p>' +
            '<div class="cm-fiche-motion-grid">' +
            grid +
            "</div>";
          var desc = root.querySelector(".cm-fiche-desc");
          if (desc && desc.parentNode) desc.parentNode.insertBefore(sec, desc.nextSibling);
          else {
            var mainCol = root.querySelector(".cm-fiche-main");
            if (mainCol) mainCol.insertBefore(sec, mainCol.firstChild);
          }
        })
        .catch(function () {});
    }
    function bindRoomClipAutoplay() {
      var vids = root.querySelectorAll(".cm-fiche-room-photo video[src]");
      if (!vids.length) return;
      vids.forEach(function (v) {
        v.muted = true;
        v.setAttribute("playsinline", "");
        v.setAttribute("loop", "");
      });
      if (!window.IntersectionObserver) {
        vids.forEach(function (v) {
          var p = v.play();
          if (p && p.catch) p.catch(function () {});
        });
        return;
      }
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (en) {
            var el = en.target;
            if (en.isIntersecting) {
              var p = el.play();
              if (p && p.catch) p.catch(function () {});
            } else {
              el.pause();
            }
          });
        },
        { threshold: 0.4 }
      );
      vids.forEach(function (v) {
        io.observe(v);
      });
    }
    bindRoomClipAutoplay();
    injectMotionFromApi();

    var vidBtn = root.querySelector(".cm-fiche-thumb.is-video, .cm-fiche-hero-tile.is-video");
    if (vidBtn) {
      vidBtn.addEventListener("click", function () {
        var u = vidBtn.getAttribute("data-video") || "";
        if (!u) return;
        var main = root.querySelector(".cm-fiche-hero-main");
        if (!main) return;
        if (/youtu/i.test(u)) {
          var yt = u.match(/(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/))([\w-]{6,})/i);
          if (yt) {
            main.innerHTML =
              '<iframe src="https://www.youtube-nocookie.com/embed/' +
              yt[1] +
              '?rel=0&autoplay=1" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>';
            return;
          }
        }
        main.innerHTML = '<video controls autoplay playsinline src="' + escapeHtml(u) + '"></video>';
      });
    }
    var priv = document.getElementById("cmFichePrivatiser");
    var panel = document.getElementById("cmFichePrivPanel");
    if (priv && panel) {
      priv.addEventListener("click", function () {
        panel.hidden = !panel.hidden;
        if (!panel.hidden) panel.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
    bindBookForm();
    bindRoomReadMore();
    bindFicheCurrency();
    bindCatalogViewContent();
  }

  function catalogRoomId(raw) {
    var n = String(raw || "")
      .replace(/^cm-room-/i, "")
      .replace(/^room-/i, "")
      .trim();
    if (!/^\d+$/.test(n)) return "";
    return "cm-room-" + n;
  }

  function roomCatalogAttrs(roomId) {
    var cid = catalogRoomId(roomId);
    if (!cid) return ' class="cm-fiche-room"';
    var n = cid.slice("cm-room-".length);
    return (
      ' class="cm-fiche-room" id="room-' +
      n +
      '" data-cm-content-id="' +
      cid +
      '"'
    );
  }

  function euroValue(n) {
    var v = Number(n);
    if (!isFinite(v) || v <= 0) return null;
    return Math.round(v * 100) / 100;
  }

  function catalogRoomsFromDom() {
    var rooms = [];
    root.querySelectorAll(".cm-fiche-room").forEach(function (card) {
      var cid = (card.getAttribute("data-cm-content-id") || "").trim();
      if (!cid) {
        var desc = card.querySelector("[id^='cm-room-desc-']");
        var more = card.querySelector("[id^='cm-room-more-']");
        var raw = "";
        if (card.id && /^room-\d+$/.test(card.id)) raw = card.id;
        else if (desc && desc.id) raw = desc.id.replace(/^cm-room-desc-/, "");
        else if (more && more.id) raw = more.id.replace(/^cm-room-more-/, "");
        cid = catalogRoomId(raw);
      }
      if (!cid) return;
      var n = cid.slice("cm-room-".length);
      if (!card.id) card.id = "room-" + n;
      if (!card.getAttribute("data-cm-content-id")) {
        card.setAttribute("data-cm-content-id", cid);
      }
      var priceEl = card.querySelector(".cm-fiche-room-price");
      var currency = (
        (priceEl && priceEl.getAttribute("data-currency-ref")) ||
        "EUR"
      ).toUpperCase();
      var value = priceEl ? euroValue(priceEl.getAttribute("data-price-ref")) : null;
      if (currency !== "EUR") value = null;
      var nameEl = card.querySelector("h3");
      rooms.push({
        id: cid,
        value: value,
        name: nameEl
          ? String(nameEl.textContent || "").replace(/\s+/g, " ").trim()
          : "",
      });
    });
    return rooms;
  }

  function fireMetaViewContent(payload) {
    var data = {
      content_ids: payload.content_ids,
      content_type: "product",
    };
    if (payload.content_name) data.content_name = payload.content_name;
    if (payload.value != null) {
      data.value = payload.value;
      data.currency = "EUR";
    }
    if (payload.contents) data.contents = payload.contents;
    if (window.CoinsCookies && typeof window.CoinsCookies.track === "function") {
      return window.CoinsCookies.track("ViewContent", data);
    }
    if (typeof window.fbq === "function") {
      window.fbq("track", "ViewContent", data);
      return true;
    }
    return false;
  }

  function hashCatalogRoomId() {
    var h = (location.hash || "").replace(/^#/, "");
    var m = h.match(/^room-(\d+)$/);
    return m ? catalogRoomId(m[1]) : "";
  }

  function fireFicheCatalogViewContent() {
    var rooms = catalogRoomsFromDom();
    if (!rooms.length) return;
    var wanted = hashCatalogRoomId();
    var picked = wanted
      ? rooms.filter(function (r) {
          return r.id === wanted;
        })
      : rooms;
    if (!picked.length) picked = rooms;
    if (wanted && picked.length === 1) {
      var r = picked[0];
      var one = { content_ids: [r.id], content_name: r.name };
      if (r.value != null) {
        one.value = r.value;
        one.contents = [{ id: r.id, quantity: 1, item_price: r.value }];
      }
      fireMetaViewContent(one);
      return;
    }
    var ids = picked.map(function (x) {
      return x.id;
    });
    var values = picked
      .map(function (x) {
        return x.value;
      })
      .filter(function (v) {
        return v != null;
      });
    var many = { content_ids: ids };
    if (values.length) {
      many.value = Math.min.apply(null, values);
      many.contents = picked
        .filter(function (x) {
          return x.value != null;
        })
        .map(function (x) {
          return { id: x.id, quantity: 1, item_price: x.value };
        });
    }
    fireMetaViewContent(many);
  }

  function bindCatalogViewContent() {
    catalogRoomsFromDom();
    var wanted = hashCatalogRoomId();
    if (wanted) {
      var el = document.getElementById("room-" + wanted.slice("cm-room-".length));
      if (el && typeof el.scrollIntoView === "function") {
        try {
          el.scrollIntoView({ block: "start" });
        } catch (e) {}
      }
    }
    fireFicheCatalogViewContent();
    if (!window.__cmCatalogHashBound) {
      window.__cmCatalogHashBound = true;
      window.addEventListener("hashchange", fireFicheCatalogViewContent);
      window.addEventListener("cm-meta-ready", fireFicheCatalogViewContent);
    }
  }

  function bindRoomReadMore() {
    root.querySelectorAll(".cm-fiche-room").forEach(function (card) {
      var toggle = card.querySelector(".cm-fiche-room-toggle");
      var more = card.querySelector(".cm-fiche-room-more");
      if (!toggle || !more) return;
      function sync() {
        var on = !!toggle.checked;
        card.classList.toggle("is-expanded", on);
        more.setAttribute("aria-expanded", on ? "true" : "false");
      }
      toggle.addEventListener("change", sync);
      more.addEventListener("keydown", function (ev) {
        if (ev.key !== "Enter" && ev.key !== " ") return;
        ev.preventDefault();
        toggle.checked = !toggle.checked;
        sync();
      });
      if (!more.hasAttribute("tabindex")) more.setAttribute("tabindex", "0");
      sync();
    });
  }

  function fmtFr(iso) {
    if (!iso) return "";
    var p = String(iso).split("-");
    if (p.length !== 3) return iso;
    return p[2] + "/" + p[1] + "/" + p[0];
  }

  function nightsBetween(a, b) {
    if (!a || !b) return 0;
    var da = new Date(a + "T00:00:00");
    var db = new Date(b + "T00:00:00");
    return Math.round((db - da) / 86400000);
  }

  function rangeBlocked(blocked, inn, out) {
    if (!blocked || !blocked.length || !inn || !out) return false;
    var a = new Date(inn + "T00:00:00");
    var b = new Date(out + "T00:00:00");
    return blocked.some(function (d) {
      var s = new Date((d.date_debut || d.start) + "T00:00:00");
      var e = new Date((d.date_fin || d.end) + "T00:00:00");
      return a < e && b > s;
    });
  }

  function bindBookForm() {
    var form = document.getElementById("cmFicheBookForm");
    if (!form) return;
    var inn = document.getElementById("cmBookIn");
    var out = document.getElementById("cmBookOut");
    var guests = document.getElementById("cmBookGuests");
    var note = document.getElementById("cmBookNote");
    var waRes = document.getElementById("cmBookWaRes");
    var waDispo = document.getElementById("cmBookWaDispo");
    var waMob = document.getElementById("cmBookWaMobile");
    var place = form.getAttribute("data-place") || "ce lieu";
    var today = new Date();
    var yyyy = today.getFullYear();
    var mm = String(today.getMonth() + 1).padStart(2, "0");
    var dd = String(today.getDate()).padStart(2, "0");
    var min = yyyy + "-" + mm + "-" + dd;
    if (inn && !inn.min) inn.min = min;
    if (out && !out.min) out.min = min;
    var blocked = [];

    function sync() {
      var a = inn && inn.value;
      var b = out && out.value;
      var g = guests && guests.value ? guests.value : "2";
      if (a && out) out.min = a;
      if (a && b && nightsBetween(a, b) < 1 && out) {
        var nx = new Date(a + "T00:00:00");
        nx.setDate(nx.getDate() + 1);
        out.value = nx.toISOString().slice(0, 10);
        b = out.value;
      }
      var busy = rangeBlocked(blocked, a, b);
      if (inn) inn.classList.toggle("is-blocked", busy);
      if (out) out.classList.toggle("is-blocked", busy);
      if (note) {
        note.classList.toggle("is-warn", busy);
        if (busy) {
          note.textContent = "Ces dates apparaissent déjà prises dans le calendrier Odoo. Yasmine confirmera.";
        } else {
          note.textContent = "Yasmine confirme les dates — pas de paiement en ligne.";
        }
      }
      var bits = "Bonjour Yasmine, je souhaite réserver " + place;
      if (a && b) bits += " du " + fmtFr(a) + " au " + fmtFr(b);
      bits += " pour " + g + " voyageur" + (Number(g) > 1 ? "s" : "") + ".";
      var href = "https://wa.me/212660159177?text=" + encodeURIComponent(bits);
      var dispo =
        "https://wa.me/212660159177?text=" +
        encodeURIComponent(
          "Bonjour Yasmine, je souhaite les disponibilités de " +
            place +
            (a && b ? " du " + fmtFr(a) + " au " + fmtFr(b) : "") +
            " pour " +
            g +
            " voyageurs."
        );
      if (waRes) waRes.href = href;
      if (waDispo) waDispo.href = dispo;
      if (waMob) waMob.href = href;
    }

    [inn, out, guests].forEach(function (el) {
      if (el) el.addEventListener("change", sync);
    });
    sync();

    fetch("/api/proprietes.json")
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        var items = (data && (data.proprietes || data.items)) || (Array.isArray(data) ? data : []);
        var hit = items.filter(function (p) {
          return String(p.nom || p.name || "").toLowerCase().indexOf("ysabella") !== -1;
        })[0];
        if (hit && hit.disponibilites && hit.disponibilites.length) {
          /* Catalogue expose les plages LIBRES. L’inverse sert à griser. */
          blocked = [];
        }
        sync();
      })
      .catch(function () { sync(); });
  }

  function loadLieu(thenRender) {
    fetch("/coins/api/carte/lieu/" + encodeURIComponent(slug))
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok, j: j };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.j || !res.j.ok || !res.j.lieu) {
          renderError("Ce lieu n’est pas (encore) publié.");
          return;
        }
        thenRender(res.j.lieu);
      })
      .catch(function () {
        renderError("Impossible de charger la fiche pour le moment.");
      });
  }

  /* Ysabella : toujours la maquette 3 colonnes, même si un cache
     sert encore l’ancienne coquille SPA ou la 1re prerender. */
  if (MOSAIC_SLUGS[slug]) {
    if (root.querySelector(".cm-fiche-hero--mosaic")) {
      bindPrerenderedFiche();
      return;
    }
    loadLieu(renderMaquette);
    return;
  }

  if (root.getAttribute("data-prerendered") === "1" || root.classList.contains("cm-fiche")) {
    bindPrerenderedFiche();
    return;
  }

  loadLieu(render);
})();
