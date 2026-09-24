/* Page Carte — Google Maps / Leaflet + badges + Stories mobile */
(function () {
  var mapEl = document.getElementById("cmCarteMap");
  if (!mapEl) return;

  var isEn = /^\/en(\/|$)/.test(location.pathname || "/");
  var statusEl = document.getElementById("cmCarteStatus");
  var filterRoot = document.getElementById("cmCarteFilters");
  var zoneRoot = document.getElementById("cmCarteZones");
  var modeRoot = document.querySelector(".cm-carte-mode");
  var feedEl = document.getElementById("cmCarteFeed");
  var storiesEl = document.getElementById("cmCarteStories");
  var rgRoot = document.getElementById("cmCarteRgFilters");
  var beRoot = document.getElementById("cmCarteBeFilters");

  var STORY_MS = 4500;
  var state = {
    map: null,
    engine: null, // "leaflet" | "google"
    pins: [],
    markers: [],
    info: null,
    mode: "theme",
    filter: "all",
    zone: "all",
    sort: "featured",
    search: {
      applied: false,
      guests: 0,
      traits: { privatisation: false, piscine: false, restaurant: false },
      start: null,
      end: null,
    },
    rg: { cuisine: [], cadre: [], alcool: [], animations: [] },
    be: { type_lieu: [], services: [], mixte: [] },
    center: { lat: 31.6295, lng: -7.9811 },
    googleTried: false,
    favorited: {}, // property_id -> true
    carnetToken: "",
    hoverPinId: null,
    videoObs: null,
    hoverTimer: null,
    hoverPinned: false,
    stories: {
      open: false,
      index: 0,
      stack: [],
      tracked: {},
      touchX: null,
      startAt: 0,
      raf: 0,
    },
  };

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("is-error", !!isError);
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ensureFicheNavStyle() {
    if (document.getElementById("cmFicheNavStyle")) return;
    var s = document.createElement("style");
    s.id = "cmFicheNavStyle";
    s.textContent =
      "#cmCarteMap .leaflet-tile-pane{z-index:2!important}" +
      "#cmCarteMap .leaflet-overlay-pane,#cmCarteMap .leaflet-marker-pane{z-index:6!important;pointer-events:auto!important}" +
      ".cm-map-pin{background:transparent!important;border:0!important}" +
      ".cm-map-pin-hit{display:block;width:28px;height:28px;border-radius:50%;background:#b5732f;border:2px solid #8a4f22;box-shadow:0 1px 6px rgba(38,34,32,.4);cursor:pointer}" +
      ".cm-map-pin-hit:hover{transform:scale(1.12);background:#c98438}" +
      ".cm-story-card,.cm-dir-card,.cm-carte-hover-card{cursor:pointer}" +
      ".cm-dir-video,.cm-dir-poster,.cm-carte-hover-card video,.cm-story-card video,.cm-story-card iframe,.cm-dir-photo iframe{pointer-events:none!important}" +
      ".cm-dir-photo{position:relative}" +
      ".cm-dir-photo-hit{position:absolute;inset:0;z-index:2}" +
      ".cm-dir-heart{z-index:4!important}" +
      ".cm-dir-cta{display:block;text-align:center;text-decoration:none}";
    document.head.appendChild(s);
  }
  ensureFicheNavStyle();

  function findPinById(id) {
    if (id == null || id === "") return null;
    return (
      state.pins.find(function (p) {
        return String(p.id) === String(id);
      }) || null
    );
  }

  function placeFicheUrl(pin) {
    if (!pin) return "";
    var url = String(pin.detail_url || pin.fiche_url || pin.portal_url || "").trim();
    if (url.indexOf("/lieu/") !== -1 && url.indexOf("/lieux/") === -1) {
      url = url.replace("/lieu/", "/lieux/");
    }
    if (url === "/partenaires" || url.indexOf("/partenaires") === 0) url = "";
    if (url && url.indexOf("/lieux/") !== -1) return url;
    var slug = String(pin.slug || "").replace(/^\/+|\/+$/g, "");
    if (slug && !/^\d+$/.test(slug) && slug.indexOf("m_") !== 0) {
      return (isEn ? "/en/lieux/" : "/lieux/") + slug;
    }
    if (url && url.charAt(0) === "/") return url;
    return "";
  }

  function isMobileStories() {
    return window.matchMedia && window.matchMedia("(max-width: 768px)").matches;
  }

  function badgeHtml(badge, extraClass) {
    if (!badge || !badge.label) return "";
    var t = badge.type || "tendance";
    return (
      '<span class="cm-badge cm-badge--' +
      escapeHtml(t) +
      (extraClass ? " " + extraClass : "") +
      '">' +
      escapeHtml(badge.label) +
      "</span>"
    );
  }

  function trackVideoView(videoId) {
    if (!videoId) return;
    var key = String(videoId);
    if (state.stories.tracked[key]) return;
    state.stories.tracked[key] = true;
    fetch("/coins/api/carte/video/view", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ video_id: videoId }),
    }).catch(function () {});
  }

  function getCookie(name) {
    var m = document.cookie.match(
      new RegExp("(?:^|; )" + name.replace(/([.$?*|{}()[\]\\/+^])/g, "\\$1") + "=([^;]*)")
    );
    return m ? decodeURIComponent(m[1]) : "";
  }

  function carnetToken() {
    if (state.carnetToken) return state.carnetToken;
    state.carnetToken =
      getCookie("cm_carnet_token") ||
      (window.localStorage && localStorage.getItem("cm_carnet_token")) ||
      "";
    return state.carnetToken;
  }

  function carnetLoginUrl(propertyId) {
    var q =
      "/carnet#retrouver?favori=" +
      encodeURIComponent(propertyId || "") +
      "&next=" +
      encodeURIComponent("/carte");
    return q;
  }

  function favBtnHtml(propertyId, extraClass) {
    var on = !!state.favorited[propertyId];
    return (
      '<button type="button" class="cm-fav' +
      (on ? " on" : "") +
      (extraClass ? " " + extraClass : "") +
      '" data-fav-id="' +
      propertyId +
      '" aria-label="' +
      (on ? "Retirer des favoris" : "Enregistrer") +
      '" aria-pressed="' +
      (on ? "true" : "false") +
      '">' +
      (on ? "♥" : "♡") +
      "</button>"
    );
  }

  function loadFavoris() {
    var token = carnetToken();
    if (!token) return Promise.resolve();
    return fetch("/coins/api/carnet/favoris", {
      headers: { "X-Carnet-Token": token },
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (j) {
        if (!j || !j.ok) return;
        state.favorited = {};
        (j.property_ids || []).forEach(function (id) {
          state.favorited[id] = true;
        });
      })
      .catch(function () {});
  }

  function toggleFavori(propertyId) {
    var token = carnetToken();
    if (!token) {
      window.location.href = carnetLoginUrl(propertyId);
      return;
    }
    fetch("/coins/api/carnet/favoris/toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Carnet-Token": token,
      },
      body: JSON.stringify({ property_id: propertyId, token: token }),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { status: r.status, j: j };
        });
      })
      .then(function (res) {
        if (res.status === 401 || (res.j && res.j.error === "auth_required")) {
          window.location.href = res.j.login_url || carnetLoginUrl(propertyId);
          return;
        }
        if (!res.j || !res.j.ok) return;
        if (res.j.favorited) state.favorited[propertyId] = true;
        else delete state.favorited[propertyId];
        syncFavButtons(propertyId);
      })
      .catch(function () {});
  }

  function syncFavButtons(propertyId) {
    var on = !!state.favorited[propertyId];
    document.querySelectorAll('.cm-fav[data-fav-id="' + propertyId + '"]').forEach(function (btn) {
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      btn.setAttribute("aria-label", on ? "Retirer des favoris" : "Enregistrer");
      btn.textContent = on ? "♥" : "♡";
    });
  }

  function ytIdFromUrl(url) {
    var m = String(url || "").match(
      /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|shorts\/|embed\/))([\w-]{6,})/i
    );
    return m ? m[1] : "";
  }

  function guessSnippetUrl(url) {
    var u = String(url || "");
    if (!u) return "";
    if (/-snippet\.mp4(\?|$)/i.test(u)) return u;
    if (/\.mp4(\?|$)/i.test(u)) return u.replace(/\.mp4(\?|$)/i, "-snippet.mp4$1");
    return u;
  }

  function bindVideoFallback(root) {
    if (!root) return;
    root.querySelectorAll("video[data-fallback]").forEach(function (v) {
      if (v.getAttribute("data-fb-bound") === "1") return;
      v.setAttribute("data-fb-bound", "1");
      v.addEventListener("error", function () {
        var fb = v.getAttribute("data-fallback");
        if (!fb || v.getAttribute("data-fb-used") === "1") return;
        v.setAttribute("data-fb-used", "1");
        v.src = fb;
        try {
          v.load();
        } catch (e) {}
        var p = v.play();
        if (p && p.catch) p.catch(function () {});
      });
    });
  }

  function videoEmbedHtml(url, title, opts) {
    opts = opts || {};
    var full = !!opts.full;
    var safeTitle = escapeHtml(title);
    var u = url || "";
    var poster = opts.poster || "";
    var fallback = opts.fallback || "";
    var style = full
      ? "width:100%;height:100%;border:0;position:absolute;inset:0"
      : "width:100%;height:160px;border:0;border-radius:6px";
    var yt = ytIdFromUrl(u);
    var vim = u.match(/vimeo\.com\/(\d+)/i);
    if (yt) {
      return (
        '<iframe src="https://www.youtube-nocookie.com/embed/' +
        yt +
        '?autoplay=1&mute=1&playsinline=1" title="' +
        safeTitle +
        '" allow="autoplay; encrypted-media" allowfullscreen style="' +
        style +
        '"></iframe>'
      );
    }
    if (vim) {
      return (
        '<iframe src="https://player.vimeo.com/video/' +
        vim[1] +
        '?autoplay=1&muted=1" title="' +
        safeTitle +
        '" allow="autoplay" allowfullscreen style="' +
        style +
        '"></iframe>'
      );
    }
    return (
      '<video autoplay muted loop playsinline controls preload="metadata"' +
      (full ? ' class="cm-stories-video"' : "") +
      (poster ? ' poster="' + escapeHtml(poster) + '"' : "") +
      (fallback ? ' data-fallback="' + escapeHtml(fallback) + '"' : "") +
      ' src="' +
      escapeHtml(u) +
      '"' +
      (full ? ' style="' + style + '"' : "") +
      "></video>"
    );
  }

  function pinCard(pin) {
    var snap = snippetUrl(pin);
    var full = pin.video_url || snap;
    return (
      '<div class="cm-pin-card">' +
      videoEmbedHtml(snap || full, pin.video_title, {
        poster: posterUrl(pin),
        fallback: full && full !== snap ? full : "",
      }) +
      badgeHtml(pin.badge, "cm-badge--card") +
      '<p class="pill">' +
      escapeHtml(pin.pillar_label || "") +
      (pin.zone ? " · " + escapeHtml(String(pin.zone).replace(/_/g, " ")) : "") +
      "</p>" +
      "<h3>" +
      escapeHtml(pin.name) +
      "</h3>" +
      '<a href="' +
      escapeHtml(placeFicheUrl(pin) || "/carte") +
      '">Voir la fiche →</a>' +
      "</div>"
    );
  }

  function pinCategoryCodes(p) {
    if (p.category_codes && p.category_codes.length) return p.category_codes;
    if (p.categories && p.categories.length) {
      return p.categories.map(function (c) {
        return c.code;
      });
    }
    if (p.pillar === "villas_riads") return ["hebergement", "decouverte"];
    if (p.pillar) return [p.pillar, "decouverte"];
    return ["decouverte"];
  }

  function partnerListingToPin(l) {
    var catMap = {
      resto: { pillar: "route_gourmande", label: "Route gourmande", code: "route_gourmande" },
      hebergement: { pillar: "villas_riads", label: "Hébergement", code: "hebergement" },
      "bien-etre": { pillar: "bien_etre", label: "Bien-être", code: "bien_etre" },
      experiences: { pillar: "experiences", label: "Expériences", code: "experiences" },
      evenements: { pillar: "evenements", label: "Événements", code: "evenements" },
      autre: { pillar: "experiences", label: "Expériences", code: "experiences" },
    };
    var m = catMap[l.category] || catMap.autre;
    return {
      id: l.id,
      name: l.name,
      slug: String(l.id || ""),
      lat: l.lat,
      lng: l.lng,
      zone: String(l.region || "").toLowerCase().replace(/\s+/g, "_"),
      pillar: m.pillar,
      pillar_label: m.label,
      categories: [{ code: m.code, label: m.label }],
      category_codes: [m.code, "decouverte"],
      district: l.region || "",
      city: "Marrakech",
      video_id: 0,
      video_url: l.video_url || "",
      snippet_url: guessSnippetUrl(l.video_url || ""),
      video_title: l.name,
      source: "partenaire",
      creator_name: "",
      badge: l.featured ? { type: "nouveau", label: "Nouveau" } : null,
      photo_url: l.video_poster || (l.photos_carte && l.photos_carte[0]) || (l.photos && l.photos[0]) || "",
      detail_url: l.detail_url || l.fiche_url || l.portal_url || "",
      description: l.description || "",
      address: l.address || "",
      services: l.services || [],
      packages: l.packages || [],
      featured: !!l.featured,
      capacity: Number(l.capacity || 0),
    };
  }

  function openRequestedPin() {
    var id = "";
    try {
      id = new URLSearchParams(location.search || "").get("pin") || "";
    } catch (e) {
      id = "";
    }
    if (!id) return;
    var pin = state.pins.filter(function (p) {
      return String(p.id) === String(id);
    })[0];
    if (!pin) return;
    var marker = state.markers.filter(function (m) {
      return m && m._cmPin && String(m._cmPin.id) === String(id);
    })[0];
    onPinActivate(pin, marker || state.markers[0] || null);
  }

  function appendPartnerPins(pins, listings) {
    var have = {};
    pins.forEach(function (p) {
      have[String(p.id)] = true;
    });
    (listings || []).forEach(function (l) {
      if (!l || !l.lat || !l.lng || !l.video_url) return;
      var id = String(l.id || "");
      if (!id || have[id]) return;
      /* Démos marketplace (m_riad_ames…) : pas de fiche lieu. */
      if (id.indexOf("m_") === 0) return;
      if (l.status && l.status !== "published") return;
      var pin = partnerListingToPin(l);
      if (!placeFicheUrl(pin)) return;
      have[id] = true;
      pins.push(pin);
    });
  }

  function pinMatchesTheme(p, filter) {
    if (filter === "all") return true;
    var codes = pinCategoryCodes(p);
    var pillar = p.pillar || "";
    if (filter === "hebergement" || filter === "villas_riads") {
      return codes.indexOf("hebergement") !== -1 || pillar === "villas_riads";
    }
    if (filter === "bien_etre") {
      return codes.indexOf("bien_etre") !== -1 || pillar === "bien_etre";
    }
    if (filter === "evenements") {
      return codes.indexOf("evenements") !== -1 || pillar === "evenements";
    }
    if (filter === "route_gourmande") {
      return pillar === "route_gourmande" || codes.indexOf("route_gourmande") !== -1;
    }
    if (filter === "plein_air") {
      return (
        pillar === "plein_air" ||
        pillar === "experiences" ||
        codes.indexOf("experiences") !== -1
      );
    }
    if (filter === "experiences") {
      return pillar === "experiences" || codes.indexOf("experiences") !== -1;
    }
    if (codes.indexOf(filter) !== -1) return true;
    return pillar === filter;
  }

  function pinRg(p) {
    return p.rg || {};
  }

  function pinMatchesRgFilters(p) {
    var rg = pinRg(p);
    var dims = ["cuisine", "cadre", "alcool", "animations"];
    for (var i = 0; i < dims.length; i++) {
      var dim = dims[i];
      var selected = state.rg[dim] || [];
      if (!selected.length) continue;
      var raw = rg[dim];
      var values = Array.isArray(raw) ? raw : raw ? [raw] : [];
      var hit = selected.some(function (v) {
        return values.indexOf(v) !== -1;
      });
      if (!hit) return false;
    }
    return true;
  }

  function pinBe(p) {
    return p.be || {};
  }

  function pinMatchesBeFilters(p) {
    var be = pinBe(p);
    var dims = ["type_lieu", "services", "mixte"];
    for (var i = 0; i < dims.length; i++) {
      var dim = dims[i];
      var selected = state.be[dim] || [];
      if (!selected.length) continue;
      var raw = be[dim];
      var values = Array.isArray(raw) ? raw : raw ? [raw] : [];
      var hit = selected.some(function (v) {
        return values.indexOf(v) !== -1;
      });
      if (!hit) return false;
    }
    return true;
  }

  function visiblePins() {
    return state.pins.filter(function (p) {
      if (state.mode === "zone") {
        if (!(state.zone === "all" || p.zone === state.zone)) return false;
      } else {
        if (!pinMatchesTheme(p, state.filter)) return false;
        if (state.filter === "route_gourmande" && !pinMatchesRgFilters(p)) {
          return false;
        }
        if (state.filter === "bien_etre" && !pinMatchesBeFilters(p)) {
          return false;
        }
      }
      return pinMatchesSearch(p);
    });
  }

  function pinBlob(p) {
    var services = (p.services || [])
      .map(function (s) {
        return typeof s === "string" ? s : s && s.name;
      })
      .join(" ");
    return [
      p.name,
      p.description,
      p.pillar,
      p.pillar_label,
      services,
    ]
      .join(" ")
      .toLowerCase();
  }

  function pinHasPrivatisation(p) {
    var codes = pinCategoryCodes(p);
    if (codes.indexOf("privatisation") !== -1) return true;
    if (p.rg && p.rg.privatisation_possible) return true;
    if (p.pillar === "evenements" || p.pillar === "villas_riads") return true;
    return /privatis/.test(pinBlob(p));
  }

  function pinHasPiscine(p) {
    if (p.daypass_piscine) return true;
    return /piscine|\bpool\b/.test(pinBlob(p));
  }

  function pinHasRestaurant(p) {
    var codes = pinCategoryCodes(p);
    if (p.pillar === "route_gourmande" || codes.indexOf("route_gourmande") !== -1) {
      return true;
    }
    var meals = p.meals || {};
    if ((meals.lunch && meals.lunch.available) || (meals.dinner && meals.dinner.available)) {
      return true;
    }
    return /restaurant|resto|table d|cuisine/.test(pinBlob(p));
  }

  function pinCapacity(p) {
    return Number(
      p.capacity ||
        (p.rg && (p.rg.capacite_groupe_max || p.rg.capacite_couverts)) ||
        (p.be && p.be.capacite_simultanee) ||
        0
    );
  }

  function ymdDate(d) {
    if (!d) return "";
    if (typeof d === "string") return d.slice(0, 10);
    var m = d.getMonth() + 1;
    var day = d.getDate();
    return (
      d.getFullYear() +
      "-" +
      (m < 10 ? "0" : "") +
      m +
      "-" +
      (day < 10 ? "0" : "") +
      day
    );
  }

  function pinFitsDates(p, start, end) {
    if (!start) return true;
    var dispos = p.disponibilites;
    if (!dispos || !dispos.length) return true;
    var s = ymdDate(start);
    var e = ymdDate(end || start);
    return dispos.some(function (d) {
      return s <= d.date_fin && e >= d.date_debut;
    });
  }

  function pinMatchesSearch(p) {
    var q = state.search;
    if (!q || !q.applied) return true;
    if (q.guests && pinCapacity(p) && pinCapacity(p) < q.guests) return false;
    if (q.traits.privatisation && !pinHasPrivatisation(p)) return false;
    if (q.traits.piscine && !pinHasPiscine(p)) return false;
    if (q.traits.restaurant && !pinHasRestaurant(p)) return false;
    if (!pinFitsDates(p, q.start, q.end)) return false;
    return true;
  }

  function featuredVisible() {
    var feat = visiblePins().filter(isFeaturedPin);
    if (feat.length >= 2) return feat;
    var rest = visiblePins().filter(function (p) {
      return feat.indexOf(p) < 0;
    });
    return feat.concat(rest).slice(0, 4);
  }

  function otherVisible() {
    /* Répertoire = tous les lieux du filtre, vedettes comprises. */
    return visiblePins();
  }

  function mergeProprietes(data) {
    var props = (data && data.proprietes) || [];
    var byId = {};
    props.forEach(function (row) {
      if (!row || row.id == null) return;
      byId[String(row.id)] = row;
    });
    state.pins.forEach(function (pin) {
      var m = byId[String(pin.id)];
      if (!m) return;
      pin.capacity = pin.capacity || m.capacite || 0;
      pin.daypass_piscine = pin.daypass_piscine || !!m.daypass_piscine;
      pin.disponibilites = m.disponibilites || pin.disponibilites || [];
      pin.meals = m.meals || pin.meals;
    });
  }

  function openPlannerFromToolbar(e) {
    if (e) e.preventDefault();
    function go() {
      if (window.CoinsPlanner) window.CoinsPlanner.open();
    }
    if (window.CoinsPlanner) {
      go();
      return;
    }
    var existing = document.querySelector('script[src*="cm-planner.js"]');
    if (existing) {
      existing.addEventListener("load", go);
      return;
    }
    if (!document.querySelector('link[href*="cm-planner.css"]')) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/assets/cm-planner.css?v=cm123";
      document.head.appendChild(link);
    }
    var s = document.createElement("script");
    s.src = "/assets/cm-planner.js?v=cm123";
    s.async = true;
    s.onload = go;
    document.head.appendChild(s);
  }

  function ensureToolbarReserve(inner) {
    if (!inner || inner.querySelector(".cm-carte-toolbar-reserve")) return;
    var wrap = document.createElement("div");
    wrap.className = "cm-carte-toolbar-reserve";
    var a = document.createElement("a");
    a.href = "#planifier";
    a.className = "cm-devis-cta cm-planner-cta";
    a.setAttribute("role", "button");
    a.textContent = isEn ? "Book / plan" : "Réserver";
    a.addEventListener("click", openPlannerFromToolbar);
    wrap.appendChild(a);
    inner.appendChild(wrap);
  }

  function ensureMapFocusExit(inner) {
    if (!inner || inner.querySelector(".cm-carte-mapfocus-exit")) return;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "cm-carte-mapfocus-exit";
    btn.textContent = isEn ? "Exit map" : "Quitter le plein écran";
    btn.hidden = true;
    btn.addEventListener("click", function () {
      setMapFocus(false);
    });
    inner.insertBefore(btn, inner.firstChild);
  }

  function setMapFocus(on) {
    document.body.classList.toggle("cm-carte-mapfocus", !!on);
    var exitBtn = document.querySelector(".cm-carte-mapfocus-exit");
    if (exitBtn) exitBtn.hidden = !on;
    var wrap = document.getElementById("cmCarteMapWrap");
    setTimeout(function () {
      try {
        if (state.engine === "google" && state.map && google.maps.event) {
          google.maps.event.trigger(state.map, "resize");
        } else if (state.engine === "leaflet" && state.map) {
          state.map.invalidateSize();
        }
      } catch (e) {}
      if (on && wrap) wrap.scrollIntoView({ block: "nearest" });
    }, 80);
  }

  function wrapToolbarInner() {
    var toolbar = document.querySelector(".cm-carte-toolbar");
    if (!toolbar) return null;
    var existing = toolbar.querySelector(":scope > .cm-carte-toolbar-inner");
    if (existing) {
      ensureToolbarReserve(existing);
      ensureMapFocusExit(existing);
      return existing;
    }
    var inner = document.createElement("div");
    inner.className = "cm-carte-toolbar-inner";
    var filtersWrap = document.createElement("div");
    filtersWrap.className = "cm-carte-toolbar-filters";
    var nodes = Array.prototype.slice.call(toolbar.childNodes);
    nodes.forEach(function (node) {
      if (
        node.nodeType === 1 &&
        (node.id === "cmCarteRgFilters" ||
          node.id === "cmCarteBeFilters" ||
          (node.classList && node.classList.contains("cm-carte-rg-filters")))
      ) {
        return;
      }
      filtersWrap.appendChild(node);
    });
    inner.appendChild(filtersWrap);
    toolbar.insertBefore(inner, toolbar.firstChild);
    ensureToolbarReserve(inner);
    ensureMapFocusExit(inner);
    return inner;
  }

  function toolbarMount() {
    var toolbar = document.querySelector(".cm-carte-toolbar");
    if (!toolbar) return null;
    var first = toolbar.firstElementChild;
    if (
      first &&
      first.classList &&
      first.classList.contains("cm-carte-toolbar-inner")
    ) {
      return first;
    }
    return wrapToolbarInner() || toolbar;
  }

  function ensureRgRoot() {
    if (rgRoot) return rgRoot;
    var toolbar = document.querySelector(".cm-carte-toolbar");
    if (!toolbar) return null;
    rgRoot = document.getElementById("cmCarteRgFilters");
    if (!rgRoot) {
      rgRoot = document.createElement("div");
      rgRoot.id = "cmCarteRgFilters";
      rgRoot.className = "cm-carte-rg-filters";
      rgRoot.hidden = true;
      toolbar.appendChild(rgRoot);
    } else if (rgRoot.parentElement !== toolbar) {
      toolbar.appendChild(rgRoot);
    }
    return rgRoot;
  }

  function setupRgFilters(themeKey) {
    var root = ensureRgRoot();
    if (!root) return;
    var show = themeKey === "route_gourmande" || state.filter === "route_gourmande";
    root.hidden = !show;
    if (!show) {
      state.rg = { cuisine: [], cadre: [], alcool: [], animations: [] };
      root.querySelectorAll("button.on").forEach(function (b) {
        b.classList.remove("on");
      });
      return;
    }
    if (root.getAttribute("data-built") === "1") {
      markEmptyRgChips();
      return;
    }
    var isEn = /^\/en(\/|$)/.test(location.pathname || "/");
    var packs = (window.CM_CARTE_RG_FILTERS || {})[isEn ? "en" : "fr"] || [];
    root.innerHTML = packs
      .map(function (group) {
        var opts = group.options || [];
        var sizeClass =
          opts.length <= 3
            ? "cm-carte-rg-group--short"
            : "cm-carte-rg-group--wide";
        var chips = opts
          .map(function (opt) {
            return (
              '<button type="button" data-rg-dim="' +
              escapeHtml(group.dim) +
              '" data-rg-value="' +
              escapeHtml(opt.value) +
              '">' +
              escapeHtml(opt.label) +
              "</button>"
            );
          })
          .join("");
        return (
          '<div class="cm-carte-rg-group ' +
          sizeClass +
          '" data-rg-group="' +
          escapeHtml(group.dim) +
          '">' +
          '<span class="cm-carte-rg-label">' +
          escapeHtml(group.label) +
          "</span>" +
          '<div class="cm-carte-filters cm-carte-rg-chips" role="group" aria-label="' +
          escapeHtml(group.label) +
          '">' +
          chips +
          "</div></div>"
        );
      })
      .join("");
    root.setAttribute("data-built", "1");
    root.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-rg-dim]");
      if (!btn) return;
      var dim = btn.getAttribute("data-rg-dim");
      var val = btn.getAttribute("data-rg-value");
      if (!dim || !val || !state.rg[dim]) return;
      var idx = state.rg[dim].indexOf(val);
      if (idx === -1) state.rg[dim].push(val);
      else state.rg[dim].splice(idx, 1);
      btn.classList.toggle("on", idx === -1);
      refresh();
    });
    markEmptyRgChips();
  }

  function markEmptyRgChips() {
    var root = ensureRgRoot();
    if (!root || root.hidden) return;
    var themePins = state.pins.filter(function (p) {
      return pinMatchesTheme(p, "route_gourmande");
    });
    root.querySelectorAll("button[data-rg-dim]").forEach(function (btn) {
      var dim = btn.getAttribute("data-rg-dim");
      var val = btn.getAttribute("data-rg-value");
      var has = themePins.some(function (p) {
        var rg = pinRg(p);
        var raw = rg[dim];
        var values = Array.isArray(raw) ? raw : raw ? [raw] : [];
        return values.indexOf(val) !== -1;
      });
      btn.classList.toggle("is-empty", !has);
    });
  }

  function ensureBeRoot() {
    if (beRoot) return beRoot;
    var toolbar = document.querySelector(".cm-carte-toolbar");
    if (!toolbar) return null;
    beRoot = document.getElementById("cmCarteBeFilters");
    if (!beRoot) {
      beRoot = document.createElement("div");
      beRoot.id = "cmCarteBeFilters";
      beRoot.className = "cm-carte-rg-filters cm-carte-be-filters";
      beRoot.hidden = true;
      toolbar.appendChild(beRoot);
    } else if (beRoot.parentElement !== toolbar) {
      toolbar.appendChild(beRoot);
    }
    return beRoot;
  }

  function setupBeFilters(themeKey) {
    var root = ensureBeRoot();
    if (!root) return;
    var show = themeKey === "bien_etre" || state.filter === "bien_etre";
    root.hidden = !show;
    if (!show) {
      state.be = { type_lieu: [], services: [], mixte: [] };
      root.querySelectorAll("button.on").forEach(function (b) {
        b.classList.remove("on");
      });
      return;
    }
    if (root.getAttribute("data-built") === "1") {
      markEmptyBeChips();
      return;
    }
    var isEn = /^\/en(\/|$)/.test(location.pathname || "/");
    var packs = (window.CM_CARTE_BE_FILTERS || {})[isEn ? "en" : "fr"] || [];
    root.innerHTML = packs
      .map(function (group) {
        var opts = group.options || [];
        var sizeClass =
          opts.length <= 3
            ? "cm-carte-rg-group--short"
            : "cm-carte-rg-group--wide";
        var chips = opts
          .map(function (opt) {
            return (
              '<button type="button" data-be-dim="' +
              escapeHtml(group.dim) +
              '" data-be-value="' +
              escapeHtml(opt.value) +
              '">' +
              escapeHtml(opt.label) +
              "</button>"
            );
          })
          .join("");
        return (
          '<div class="cm-carte-rg-group ' +
          sizeClass +
          '" data-be-group="' +
          escapeHtml(group.dim) +
          '">' +
          '<span class="cm-carte-rg-label">' +
          escapeHtml(group.label) +
          "</span>" +
          '<div class="cm-carte-filters cm-carte-rg-chips" role="group" aria-label="' +
          escapeHtml(group.label) +
          '">' +
          chips +
          "</div></div>"
        );
      })
      .join("");
    root.setAttribute("data-built", "1");
    root.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-be-dim]");
      if (!btn) return;
      var dim = btn.getAttribute("data-be-dim");
      var val = btn.getAttribute("data-be-value");
      if (!dim || !val || !state.be[dim]) return;
      var idx = state.be[dim].indexOf(val);
      if (idx === -1) state.be[dim].push(val);
      else state.be[dim].splice(idx, 1);
      btn.classList.toggle("on", idx === -1);
      refresh();
    });
    markEmptyBeChips();
  }

  function markEmptyBeChips() {
    var root = ensureBeRoot();
    if (!root || root.hidden) return;
    var themePins = state.pins.filter(function (p) {
      return pinMatchesTheme(p, "bien_etre");
    });
    root.querySelectorAll("button[data-be-dim]").forEach(function (btn) {
      var dim = btn.getAttribute("data-be-dim");
      var val = btn.getAttribute("data-be-value");
      var has = themePins.some(function (p) {
        var be = pinBe(p);
        var raw = be[dim];
        var values = Array.isArray(raw) ? raw : raw ? [raw] : [];
        return values.indexOf(val) !== -1;
      });
      btn.classList.toggle("is-empty", !has);
    });
  }

  function markEmptyChips() {
    if (!filterRoot) return;
    var counts = {};
    state.pins.forEach(function (p) {
      [
        "hebergement",
        "bien_etre",
        "route_gourmande",
        "plein_air",
        "experiences",
        "evenements",
        "decouverte",
        "privatisation",
      ].forEach(function (key) {
        if (pinMatchesTheme(p, key)) counts[key] = (counts[key] || 0) + 1;
      });
      if (p.pillar === "villas_riads") {
        counts.hebergement = (counts.hebergement || 0) + 1;
      }
    });
    filterRoot.querySelectorAll("button[data-filter]").forEach(function (btn) {
      var key = btn.getAttribute("data-filter");
      if (key === "all") {
        btn.classList.remove("is-empty");
        return;
      }
      btn.classList.toggle("is-empty", !counts[key]);
    });
  }

  function resolveThemeKey() {
    var fromBody = (document.body.getAttribute("data-carte-theme") || "").trim();
    var params = new URLSearchParams(location.search || "");
    var q = (params.get("theme") || "").trim();
    var path = (location.pathname || "").replace(/\/+$/, "");
    var m =
      path.match(/\/carte\/([^/]+)$/) || path.match(/\/en\/map\/([^/]+)$/);
    var raw = fromBody || q || (m && m[1]) || "";
    var slugs = window.CM_CARTE_THEME_SLUGS || {};
    return slugs[raw] || slugs[raw.replace(/-/g, "_")] || null;
  }

  function experiencesHref() {
    return /^\/en(\/|$)/.test(location.pathname || "/")
      ? "/en/map/experiences"
      : "/carte/experiences";
  }

  /** Legacy plein-air URLs → page Expériences. Le filtre carte experiences reste sur /carte. */
  function redirectExperiencesIfNeeded(themeKey) {
    var path = (location.pathname || "").replace(/\/+$/, "");
    if (path === "/carte/plein-air" || path === "/en/map/outdoors") {
      location.replace(experiencesHref());
      return true;
    }
    return false;
  }

  function applyThemeSeo(themeKey) {
    var themes = window.CM_CARTE_THEMES || {};
    var conf = themes[themeKey];
    if (!conf) return;
    var isEn = /^\/en(\/|$)/.test(location.pathname || "/");
    var pack = isEn ? conf.en : conf.fr;
    if (!pack) return;
    if (pack.title) document.title = pack.title;
    var metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc && pack.description) metaDesc.setAttribute("content", pack.description);
    var ogTitle = document.querySelector('meta[property="og:title"]');
    if (ogTitle && pack.title) ogTitle.setAttribute("content", pack.title);
    var ogDesc = document.querySelector('meta[property="og:description"]');
    if (ogDesc && pack.description) ogDesc.setAttribute("content", pack.description);
    var h1 = document.getElementById("cmCarteH1");
    if (h1 && pack.h1) h1.textContent = pack.h1;
    var lead = document.getElementById("cmCarteLead");
    if (lead && pack.lead) lead.textContent = pack.lead;
    var eyebrow = document.getElementById("cmCarteEyebrow");
    if (eyebrow) {
      eyebrow.textContent = isEn ? "Map · Marrakech" : "Carte · Marrakech";
    }
  }

  /* ——— Stories (mobile) ——— */
  function ensureStoriesRoot() {
    if (storiesEl) return storiesEl;
    storiesEl = document.createElement("div");
    storiesEl.id = "cmCarteStories";
    storiesEl.className = "cm-stories";
    storiesEl.hidden = true;
    storiesEl.setAttribute("aria-hidden", "true");
    document.body.appendChild(storiesEl);
    return storiesEl;
  }

  function closeStories() {
    var root = ensureStoriesRoot();
    state.stories.open = false;
    state.stories.stack = [];
    root.hidden = true;
    root.setAttribute("aria-hidden", "true");
    root.innerHTML = "";
    document.body.classList.remove("cm-stories-open");
  }

  function renderStoriesFrame() {
    var root = ensureStoriesRoot();
    var stack = state.stories.stack;
    var idx = state.stories.index;
    if (!stack.length) {
      closeStories();
      return;
    }
    if (idx < 0) idx = 0;
    if (idx >= stack.length) idx = stack.length - 1;
    state.stories.index = idx;
    var pin = stack[idx];
    var dashes = stack
      .map(function (_, i) {
        return '<i class="' + (i === idx ? "on" : i < idx ? "done" : "") + '"></i>';
      })
      .join("");

    root.innerHTML =
      '<div class="cm-stories-frame">' +
      '<div class="cm-stories-progress">' +
      dashes +
      "</div>" +
      '<button type="button" class="cm-stories-close" aria-label="Fermer">×</button>' +
      '<div class="cm-stories-media">' +
      videoEmbedHtml(snippetUrl(pin) || pin.video_url, pin.video_title, {
        full: true,
        poster: posterUrl(pin),
        fallback: pin.video_url || "",
      }) +
      "</div>" +
      '<button type="button" class="cm-stories-tap cm-stories-tap--prev" aria-label="Précédent"></button>' +
      '<button type="button" class="cm-stories-tap cm-stories-tap--next" aria-label="Suivant"></button>' +
      '<div class="cm-stories-info">' +
      badgeHtml(pin.badge, "cm-badge--stories") +
      '<p class="cm-stories-meta">' +
      escapeHtml(pin.pillar_label || "") +
      (pin.zone ? " · " + escapeHtml(String(pin.zone).replace(/_/g, " ")) : "") +
      "</p>" +
      "<h2>" +
      escapeHtml(pin.name) +
      "</h2>" +
      '<a class="cm-stories-cta" href="' +
      escapeHtml(placeFicheUrl(pin) || "/carte") +
      '">Voir la fiche</a>' +
      "</div>" +
      "</div>";

    root.hidden = false;
    root.setAttribute("aria-hidden", "false");
    document.body.classList.add("cm-stories-open");
    trackVideoView(pin.video_id);

    bindVideoFallback(root);
    var vid = root.querySelector("video");
    if (vid) {
      var play = vid.play();
      if (play && play.catch) play.catch(function () {});
    }
  }

  function storiesNext() {
    if (state.stories.index >= state.stories.stack.length - 1) {
      closeStories();
      return;
    }
    state.stories.index += 1;
    renderStoriesFrame();
  }

  function storiesPrev() {
    if (state.stories.index <= 0) return;
    state.stories.index -= 1;
    renderStoriesFrame();
  }

  function openStories(startPin) {
    var stack = visiblePins();
    if (!stack.length) return;
    var index = 0;
    if (startPin) {
      for (var i = 0; i < stack.length; i++) {
        if (stack[i].id === startPin.id) {
          index = i;
          break;
        }
      }
    }
    state.stories.open = true;
    state.stories.stack = stack;
    state.stories.index = index;
    renderStoriesFrame();
  }

  function bindStoriesUi() {
    var root = ensureStoriesRoot();
    root.addEventListener("click", function (ev) {
      if (ev.target.closest(".cm-stories-close")) {
        closeStories();
        return;
      }
      if (ev.target.closest(".cm-stories-tap--prev")) {
        storiesPrev();
        return;
      }
      if (ev.target.closest(".cm-stories-tap--next")) {
        storiesNext();
        return;
      }
    });
    root.addEventListener(
      "touchstart",
      function (ev) {
        if (!state.stories.open || !ev.changedTouches.length) return;
        state.stories.touchX = ev.changedTouches[0].clientX;
      },
      { passive: true }
    );
    root.addEventListener(
      "touchend",
      function (ev) {
        if (!state.stories.open || state.stories.touchX == null || !ev.changedTouches.length)
          return;
        var dx = ev.changedTouches[0].clientX - state.stories.touchX;
        state.stories.touchX = null;
        if (Math.abs(dx) < 48) return;
        if (dx < 0) storiesNext();
        else storiesPrev();
      },
      { passive: true }
    );
    document.addEventListener("keydown", function (ev) {
      if (!state.stories.open) return;
      if (ev.key === "Escape") closeStories();
      if (ev.key === "ArrowRight") storiesNext();
      if (ev.key === "ArrowLeft") storiesPrev();
    });
  }

  function goToPlaceFiche(pin) {
    var url = placeFicheUrl(pin);
    if (!url && pin && pin.detail_url) url = pin.detail_url;
    if (!url) return;
    trackVideoView(pin && pin.video_id);
    try {
      window.location.assign(url);
    } catch (e) {
      window.location.href = url;
    }
  }

  function onPinActivate(pin, marker) {
    hideHoverSnippet();
    goToPlaceFiche(pin);
  }

  function snippetUrl(pin) {
    var s = pin.snippet_url || "";
    if (s && /-snippet\.mp4(\?|$)/i.test(s)) return s;
    return guessSnippetUrl(pin.video_url || s);
  }

  function ensureHoverEl() {
    var wrap = document.getElementById("cmCarteMapWrap");
    var el = document.getElementById("cmCarteHover");
    if (el) return el;
    el = document.createElement("div");
    el.id = "cmCarteHover";
    el.className = "cm-carte-hover";
    el.hidden = true;
    el.setAttribute("aria-hidden", "true");
    (wrap || document.body).appendChild(el);
    el.addEventListener("mouseenter", function () {
      state.hoverPinned = true;
    });
    el.addEventListener("mouseleave", function () {
      state.hoverPinned = false;
      hideHoverSnippet();
    });
    el.addEventListener("click", function (ev) {
      ev.preventDefault();
      ev.stopPropagation();
      var pin = findPinById(state.hoverPinId);
      if (pin) goToPlaceFiche(pin);
    });
    el.style.cursor = "pointer";
    return el;
  }

  function hideHoverSnippet() {
    if (state.hoverTimer) {
      clearTimeout(state.hoverTimer);
      state.hoverTimer = null;
    }
    var el = document.getElementById("cmCarteHover");
    if (!el) return;
    el.hidden = true;
    el.setAttribute("aria-hidden", "true");
    el.innerHTML = "";
    state.hoverPinId = null;
  }

  function showHoverSnippet(pin, clientX, clientY) {
    if (isMobileStories()) return;
    if (state.stories && state.stories.open) return;
    if (state.hoverPinId === pin.id) return;
    state.hoverPinId = pin.id;
    var el = ensureHoverEl();
    var wrap = document.getElementById("cmCarteMapWrap");
    var rect = (wrap || mapEl).getBoundingClientRect();
    var src = snippetUrl(pin);
    el.innerHTML =
      '<a class="cm-carte-hover-card" href="' +
      escapeHtml(placeFicheUrl(pin)) +
      '" data-open-fiche="1" data-pin-id="' +
      escapeHtml(String(pin.id)) +
      '">' +
      '<video muted playsinline loop autoplay preload="metadata" src="' +
      escapeHtml(src) +
      '"></video>' +
      badgeHtml(pin.badge, "cm-badge--hover") +
      '<p class="cm-carte-hover-name">' +
      escapeHtml(pin.name) +
      "</p>" +
      '<p class="cm-carte-hover-hint">Cliquez pour ouvrir la fiche</p>' +
      "</a>";
    el.hidden = false;
    el.setAttribute("aria-hidden", "false");
    var left = clientX - rect.left + 16;
    var top = clientY - rect.top - 12;
    var cardW = 200;
    var cardH = 160;
    if (left + cardW > rect.width - 8) left = clientX - rect.left - cardW - 16;
    if (top + cardH > rect.height - 8) top = clientY - rect.top - cardH - 8;
    if (left < 8) left = 8;
    if (top < 8) top = 8;
    el.style.left = left + "px";
    el.style.top = top + "px";
    var v = el.querySelector("video");
    if (v) {
      var p = v.play();
      if (p && p.catch) p.catch(function () {});
    }
  }

  function scheduleHover(pin, clientX, clientY) {
    if (isMobileStories()) return;
    if (state.hoverTimer) clearTimeout(state.hoverTimer);
    state.hoverTimer = setTimeout(function () {
      showHoverSnippet(pin, clientX, clientY);
    }, 180);
  }

  function clearMarkers() {
    hideHoverSnippet();
    if (state.engine === "leaflet" && state.map) {
      state.markers.forEach(function (m) {
        state.map.removeLayer(m);
      });
    } else if (state.engine === "google") {
      state.markers.forEach(function (m) {
        m.setMap(null);
      });
    }
    state.markers = [];
  }

  function playPopupVideo(root) {
    if (!root) return;
    bindVideoFallback(root);
    var v = root.querySelector(".cm-pin-card video");
    if (!v) return;
    function tryPlay() {
      var p = v.play();
      if (p && p.catch) p.catch(function () {});
    }
    tryPlay();
    if (v.readyState < 3) {
      v.addEventListener("canplay", tryPlay, { once: true });
      v.addEventListener("loadeddata", tryPlay, { once: true });
    }
  }

  function openPinPopup(pin, marker) {
    if (state.engine === "leaflet") {
      if (state.map) state.map.closePopup();
      marker
        .bindPopup(pinCard(pin), { maxWidth: 300, className: "cm-leaflet-popup" })
        .openPopup();
      marker.once("popupopen", function (ev) {
        var el = (ev && ev.popup && ev.popup.getElement && ev.popup.getElement()) || mapEl;
        playPopupVideo(el);
      });
      return;
    }
    if (!state.info) state.info = new google.maps.InfoWindow();
    state.info.setContent(pinCard(pin));
    state.info.open({ map: state.map, anchor: marker });
    google.maps.event.addListenerOnce(state.info, "domready", function () {
      playPopupVideo(document);
    });
  }

  function bindPinHover(pin, marker) {
    if (state.engine === "leaflet") {
      marker.on("mouseover", function (ev) {
        var oe = ev.originalEvent || {};
        scheduleHover(pin, oe.clientX || 0, oe.clientY || 0);
      });
      marker.on("mouseout", function () {
        if (state.hoverTimer) clearTimeout(state.hoverTimer);
        state.hoverTimer = setTimeout(function () {
          if (!state.hoverPinned) hideHoverSnippet();
        }, 220);
      });
      return;
    }
    marker.addListener("mouseover", function (ev) {
      var dom = ev.domEvent || {};
      scheduleHover(pin, dom.clientX || 0, dom.clientY || 0);
    });
    marker.addListener("mouseout", function () {
      if (state.hoverTimer) clearTimeout(state.hoverTimer);
      state.hoverTimer = setTimeout(function () {
        if (!state.hoverPinned) hideHoverSnippet();
      }, 220);
    });
  }

  function bindMapFicheClick() {
    if (!state.map || state._mapFicheBound === state.engine) return;
    state._mapFicheBound = state.engine;
    if (state.engine === "leaflet") {
      state.map.on("click", function (ev) {
        var t = ev && ev.originalEvent && ev.originalEvent.target;
        var hit =
          t && t.closest
            ? t.closest(".cm-map-pin-hit, .cm-map-pin")
            : null;
        if (hit) {
          var hid =
            hit.getAttribute("data-pin-id") ||
            (hit.querySelector && hit.querySelector("[data-pin-id]")
              ? hit.querySelector("[data-pin-id]").getAttribute("data-pin-id")
              : "");
          var pinHit = findPinById(hid);
          if (pinHit) onPinActivate(pinHit, null);
          return;
        }
        if (!ev.containerPoint) return;
        var best = null;
        var bestD = 26;
        state.markers.forEach(function (m) {
          if (!m || !m.getLatLng) return;
          var pt = state.map.latLngToContainerPoint(m.getLatLng());
          var d = Math.hypot(pt.x - ev.containerPoint.x, pt.y - ev.containerPoint.y);
          if (d < bestD) {
            bestD = d;
            best = m._cmPin;
          }
        });
        if (best) onPinActivate(best, null);
      });
      return;
    }
    if (state.engine === "google" && window.google && google.maps) {
      state.map.addListener("click", function () {
        /* Les pins Google ont leur propre listener click. */
      });
    }
  }

  function renderMarkers() {
    if (!state.map) return;
    clearMarkers();
    var visible = visiblePins().filter(function (pin) {
      return Number(pin.lat) && Number(pin.lng);
    });
    if (!visible.length) {
      setStatus("Aucun lieu vidéo pour ce filtre — essayez « Tous ».");
      return;
    }
    setStatus(visible.length + " lieu" + (visible.length > 1 ? "x" : "") + " en vidéo");

    if (state.engine === "leaflet") {
      var group = [];
      visible.forEach(function (pin) {
        var url = placeFicheUrl(pin);
        var icon = L.divIcon({
          className: "cm-map-pin",
          html:
            '<a class="cm-map-pin-hit" href="' +
            escapeHtml(url) +
            '" data-open-fiche="1" data-pin-id="' +
            escapeHtml(String(pin.id)) +
            '" title="' +
            escapeHtml(pin.name) +
            '" aria-label="' +
            escapeHtml(pin.name) +
            '"></a>',
          iconSize: [28, 28],
          iconAnchor: [14, 14],
        });
        var marker = L.marker([pin.lat, pin.lng], {
          icon: icon,
          keyboard: true,
          title: pin.name,
          riseOnHover: true,
        });
        marker.on("click", function (ev) {
          if (ev && ev.originalEvent) {
            ev.originalEvent.preventDefault();
            if (ev.originalEvent.stopPropagation) ev.originalEvent.stopPropagation();
          }
          onPinActivate(pin, marker);
        });
        bindPinHover(pin, marker);
        marker._cmPin = pin;
        marker.addTo(state.map);
        state.markers.push(marker);
        group.push(marker);
      });
      bindMapFicheClick();
      fitMapToPins(visible, "leaflet");
      return;
    }

    var gBounds = new google.maps.LatLngBounds();
    visible.forEach(function (pin) {
      var pos = { lat: pin.lat, lng: pin.lng };
      var marker = new google.maps.Marker({
        position: pos,
        map: state.map,
        title: pin.name,
        optimized: false,
        clickable: true,
        cursor: "pointer",
        zIndex: 1000,
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 12,
          fillColor: "#b5732f",
          fillOpacity: 1,
          strokeColor: "#8a4f22",
          strokeWeight: 2,
        },
      });
      marker.addListener("click", function () {
        onPinActivate(pin, marker);
      });
      bindPinHover(pin, marker);
      marker._cmPin = pin;
      state.markers.push(marker);
      gBounds.extend(pos);
    });
    bindMapFicheClick();
    fitMapToPins(visible, "google", gBounds);
  }

  /** Zoom Marrakech ~40 km : évite la vue régionale trop large (Essaouira–Atlas). */
  function fitMapToPins(visible, engine, gBounds) {
    if (!visible || !visible.length || !state.map) return;
    var minZ = 10;
    var maxZ = 12;
    if (engine === "leaflet") {
      if (visible.length === 1) {
        state.map.setView([visible[0].lat, visible[0].lng], 12);
      } else {
        var bounds = L.latLngBounds(
          visible.map(function (p) {
            return [p.lat, p.lng];
          })
        );
        if (bounds.isValid()) {
          state.map.fitBounds(bounds.pad(0.22), { maxZoom: maxZ, animate: false });
        }
      }
      setTimeout(function () {
        if (!state.map || state.engine !== "leaflet") return;
        state.map.invalidateSize({ animate: false });
        var z = state.map.getZoom();
        if (z < minZ) {
          state.map.setView(
            [
              visible.reduce(function (s, p) {
                return s + p.lat;
              }, 0) / visible.length,
              visible.reduce(function (s, p) {
                return s + p.lng;
              }, 0) / visible.length,
            ],
            minZ,
            { animate: false }
          );
        }
      }, 180);
      return;
    }
    if (engine === "google") {
      if (visible.length === 1) {
        state.map.setCenter({ lat: visible[0].lat, lng: visible[0].lng });
        state.map.setZoom(12);
      } else if (gBounds) {
        state.map.fitBounds(gBounds, { padding: 56, maxZoom: maxZ });
      }
      if (window.google && google.maps) {
        google.maps.event.addListenerOnce(state.map, "idle", function () {
          var z = state.map.getZoom();
          if (z == null) return;
          if (z < minZ) {
            var c = gBounds ? gBounds.getCenter() : state.map.getCenter();
            state.map.setCenter(c);
            state.map.setZoom(minZ);
          } else if (z > maxZ && visible.length > 1) {
            state.map.setZoom(maxZ);
          }
        });
      }
    }
  }

  function zoneLabel(zone) {
    var z = String(zone || "").toLowerCase();
    if (z === "marrakech_centre") return "Centre";
    if (z === "palmeraie") return "Palmeraie";
    if (z === "agafay") return "Agafay";
    if (z === "autre") return "Environs";
    return z ? z.replace(/_/g, " ") : "Marrakech";
  }

  function categoryLabel(pin, compact) {
    var cats = pin.categories || [];
    var prefer = state.filter && state.filter !== "all" ? state.filter : "";
    var priority = prefer
      ? [prefer, "hebergement", "bien_etre", "route_gourmande", "experiences", "evenements", "privatisation"]
      : ["hebergement", "bien_etre", "route_gourmande", "experiences", "evenements", "privatisation"];
    var cat = "";
    var i;
    var p;
    for (p = 0; p < priority.length; p++) {
      for (i = 0; i < cats.length; i++) {
        if ((cats[i].code || "").trim() === priority[p]) {
          cat = (cats[i].label || cats[i].code || "").trim();
          break;
        }
      }
      if (cat) break;
    }
    if (!cat) {
      for (i = 0; i < cats.length; i++) {
        var code = (cats[i].code || "").trim();
        if (code && code !== "decouverte") {
          cat = (cats[i].label || code).trim();
          break;
        }
      }
    }
    if (!cat) cat = (pin.pillar_label || "").trim();
    if (!cat) cat = "Lieu";
    if (compact) return cat.toUpperCase();
    return (cat + " · " + zoneLabel(pin.zone)).toUpperCase();
  }

  function posterUrl(pin) {
    var local = pin.photo_url || "";
    var url = "";
    if (local && !/\/api\/coins-marocain\/photos\//.test(local)) {
      url = local;
    } else {
      var u = pin.snippet_url || pin.video_url || "";
      var m = String(u).match(/\/([^\/?#]+)\.mp4/i);
      if (m) {
        var base = m[1].replace(/-snippet$/i, "");
        url = "/assets/img/evenements/" + base + "-poster.jpg";
      } else {
        url = local || "/assets/img/forfaits-hero.jpg";
      }
    }
    if (url && !/[?&]v=/.test(url) && /\/assets\/img\/evenements\//.test(url)) {
      url += (url.indexOf("?") >= 0 ? "&" : "?") + "v=cm156";
    }
    return url;
  }

  function storyMediaHtml(pin) {
    var poster = posterUrl(pin);
    if (/youtu\.be|youtube\.com|vimeo\.com/i.test(pin.video_url || "")) {
      return (
        '<img class="cm-story-media" alt="" src="' +
        escapeHtml(poster) +
        '" loading="lazy" decoding="async">'
      );
    }
    var src = snippetUrl(pin);
    if (!src) {
      return (
        '<img class="cm-story-media" alt="" src="' +
        escapeHtml(poster) +
        '" loading="lazy" decoding="async">'
      );
    }
    /* Poster seul au chargement ; data-src armé au survol (connexions lentes Maroc). */
    return (
      '<img class="cm-story-media cm-story-poster" alt="" src="' +
      escapeHtml(poster) +
      '" loading="lazy" decoding="async">' +
      '<video class="cm-story-media cm-story-video" muted playsinline loop preload="none" poster="' +
      escapeHtml(poster) +
      '" data-src="' +
      escapeHtml(src) +
      '" hidden></video>'
    );
  }

  function isFeaturedPin(pin) {
    if (!pin) return false;
    if (pin.featured) return true;
    if (pin.badge && (pin.badge.type === "tendance" || pin.badge.type === "radio" || pin.badge.type === "nouveau")) {
      return true;
    }
    var v = pin.niveau_visibilite;
    return v === "vedette" || v === "featured" || v === "haute";
  }

  function storyFeatureBadge(pin, compact) {
    if (!isFeaturedPin(pin)) return "";
    var label = "Cette semaine";
    if (pin.badge && pin.badge.type === "radio") label = "Coup de cœur";
    else if (pin.badge && pin.badge.type === "tendance") label = "Cette semaine";
    return (
      '<span class="cm-badge cm-badge--' +
      escapeHtml((pin.badge && pin.badge.type) || "tendance") +
      ' cm-badge--story' +
      (compact ? " cm-badge--story-mini" : "") +
      '">' +
      escapeHtml(label) +
      "</span>"
    );
  }

  function storyCardHtml(pin, extraClass) {
    var compact = !!(extraClass && extraClass.indexOf("cm-story-card--mini") !== -1);
    var fiche = placeFicheUrl(pin) || (isEn ? "/en/villas-riads" : "/carte/hebergement");
    return (
      '<a class="cm-story-card cm-carte-feed-card' +
      (extraClass ? " " + extraClass : "") +
      '" href="' +
      escapeHtml(fiche) +
      '" data-pin-id="' +
      pin.id +
      '" data-open-fiche="1">' +
      storyMediaHtml(pin) +
      '<div class="cm-story-gradient"></div>' +
      storyFeatureBadge(pin, compact) +
      '<span class="cm-story-cat">' +
      escapeHtml(categoryLabel(pin, compact)) +
      "</span>" +
      '<span class="cm-story-play" aria-hidden="true"><span class="tri"></span></span>' +
      '<h3 class="cm-story-name">' +
      escapeHtml(pin.name) +
      "</h3></a>"
    );
  }

  function armLazyVideo(vid) {
    if (!vid || vid.getAttribute("src")) return;
    var src = vid.getAttribute("data-src");
    if (!src) return;
    vid.setAttribute("src", src);
    try {
      vid.load();
    } catch (e) {}
  }

  function cardVideoEls(card) {
    return {
      vid: card.querySelector("video.cm-story-video, video.cm-dir-video"),
      poster: card.querySelector("img.cm-story-poster, img.cm-dir-poster"),
    };
  }

  function playRemoteCardVideo(card) {
    /* YouTube/Vimeo iframe vole le clic — on reste sur poster/mp4. */
    return;
  }

  function playCardVideo(card, opts) {
    if (!card) return;
    opts = opts || {};
    if (opts.sticky) card.setAttribute("data-user-play", "1");
    var els = cardVideoEls(card);
    if (!els.vid) {
      playRemoteCardVideo(card);
      return;
    }
    armLazyVideo(els.vid);
    if (els.poster) els.poster.hidden = true;
    els.vid.hidden = false;
    function tryPlay() {
      var p = els.vid.play();
      if (p && p.catch) p.catch(function () {});
    }
    tryPlay();
    if (els.vid.readyState < 3) {
      els.vid.addEventListener("canplay", tryPlay, { once: true });
      els.vid.addEventListener("loadeddata", tryPlay, { once: true });
    }
  }

  function pauseCardVideo(card) {
    if (!card || card.getAttribute("data-user-play") === "1") return;
    var els = cardVideoEls(card);
    if (!els.vid) return;
    els.vid.pause();
    try {
      els.vid.currentTime = 0;
    } catch (e) {}
    els.vid.hidden = true;
    if (els.poster) els.poster.hidden = false;
  }

  function bindCardFicheNav(root) {
    if (!root) return;
    root.querySelectorAll(".cm-story-card[data-open-fiche], .cm-dir-card[data-dir-pin]").forEach(function (card) {
      if (card.getAttribute("data-fiche-bound") === "1") return;
      card.setAttribute("data-fiche-bound", "1");
      card.addEventListener(
        "click",
        function (ev) {
          if (ev.target.closest("[data-dir-heart], [data-dir-map]")) return;
          ev.preventDefault();
          ev.stopPropagation();
          var id = card.getAttribute("data-pin-id") || card.getAttribute("data-dir-pin");
          var pin = findPinById(id);
          var href = card.getAttribute("href") || "";
          if (!href) {
            var a = card.querySelector("a[data-dir-fiche], a.cm-dir-photo-hit");
            if (a) href = a.getAttribute("href") || "";
          }
          goToPlaceFiche(pin || { detail_url: href });
        },
        true
      );
    });
  }

  function bindPreviewVideos(root) {
    if (!root) return;
    bindCardFicheNav(root);
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var cards = root.querySelectorAll(".cm-story-card, .cm-dir-card");
    cards.forEach(function (card) {
      if (card.getAttribute("data-hover-bound") || !cardVideoEls(card).vid) return;
      card.setAttribute("data-hover-bound", "1");
      card.addEventListener("mouseenter", function () {
        playCardVideo(card);
      });
      card.addEventListener("mouseleave", function () {
        if (card.getAttribute("data-inview") !== "1") pauseCardVideo(card);
      });
    });
    if (reduce) return;
    if (!state.videoObs) {
      state.videoObs = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (entry) {
            var card = entry.target;
            if (entry.isIntersecting && entry.intersectionRatio >= 0.35) {
              card.setAttribute("data-inview", "1");
              playCardVideo(card);
            } else {
              card.setAttribute("data-inview", "0");
              pauseCardVideo(card);
            }
          });
        },
        { threshold: [0, 0.35, 0.6], rootMargin: "40px 0px" }
      );
    }
    cards.forEach(function (card) {
      if (cardVideoEls(card).vid) state.videoObs.observe(card);
    });
  }

  function bindHeroVideoHover(root) {
    bindPreviewVideos(root);
  }

  /** Range les blocs SEO « pad » dans le fold — indexables, hors du premier viewport. */
  function foldSeoPads() {
    var body = document.querySelector("#seo-dense .cm-seo-fold-body, .cm-seo-fold .cm-seo-fold-body");
    if (!body) return;
    ["seo-pad", "seo-pad2", "seo-extra"].forEach(function (id) {
      var el = document.getElementById(id);
      if (!el || body.contains(el)) return;
      el.removeAttribute("style");
      el.classList.add("cm-seo-fold-extra");
      body.appendChild(el);
    });
  }

  function carteBookHtml() {
    return (
      '<aside class="cm-carte-book" id="cmCarteBook" aria-labelledby="cmCarteBookTitle">' +
      '<h2 id="cmCarteBookTitle" class="cm-carte-book-title">' +
      (isEn ? "Search" : "Rechercher") +
      "</h2>" +
      '<div class="cm-carte-book-bar">' +
      '<button type="button" class="cm-carte-book-seg cm-carte-book-dates" id="cmCarteBookDatesBtn" aria-expanded="false" aria-controls="cmCarteBookCal">' +
      '<span class="cm-carte-book-kicker">' +
      (isEn ? "Availability" : "Disponibilité") +
      "</span>" +
      '<span class="cm-carte-book-range" id="cmCarteBookRange">' +
      (isEn ? "Check-in — Check-out" : "Arrivée — Départ") +
      "</span>" +
      "</button>" +
      '<label class="cm-carte-book-seg">' +
      '<span class="cm-carte-book-kicker">' +
      (isEn ? "Travelers" : "Voyageurs") +
      "</span>" +
      '<input type="number" id="cmCarteBookGuests" min="1" max="500" step="1" inputmode="numeric" placeholder="' +
      (isEn ? "e.g. 8" : "ex. 8") +
      '">' +
      "</label>" +
      '<div class="cm-carte-book-seg cm-carte-book-traits" role="group" aria-label="' +
      (isEn ? "Particularities" : "Particularités") +
      '">' +
      '<span class="cm-carte-book-kicker">' +
      (isEn ? "Looking for" : "Particularités") +
      "</span>" +
      '<div class="cm-carte-book-trait-row">' +
      '<button type="button" class="cm-carte-book-trait" data-trait="privatisation">' +
      (isEn ? "Buyout" : "Privatisation") +
      "</button>" +
      '<button type="button" class="cm-carte-book-trait" data-trait="piscine">' +
      (isEn ? "Pool" : "Piscine") +
      "</button>" +
      '<button type="button" class="cm-carte-book-trait" data-trait="restaurant">' +
      (isEn ? "Restaurant" : "Restaurant") +
      "</button>" +
      "</div></div>" +
      '<button type="button" class="cm-carte-book-submit" id="cmCarteBookSubmit">' +
      (isEn ? "Search" : "Rechercher") +
      "</button>" +
      "</div>" +
      '<div class="cm-carte-book-cal" id="cmCarteBookCal" hidden>' +
      '<div class="cm-carte-book-cal-nav">' +
      '<button type="button" id="cmCarteBookPrev" aria-label="' +
      (isEn ? "Previous month" : "Mois précédent") +
      '">‹</button>' +
      '<div class="cm-carte-book-cal-title" id="cmCarteBookCalTitle"></div>' +
      '<button type="button" id="cmCarteBookNext" aria-label="' +
      (isEn ? "Next month" : "Mois suivant") +
      '">›</button>' +
      "</div>" +
      '<div class="cm-carte-book-grid" id="cmCarteBookGrid" role="grid"></div>' +
      "</div>" +
      '<p class="cm-carte-book-hint" id="cmCarteBookHint">' +
      (isEn
        ? "Travelers, dates and pool / restaurant / buyout — then we propose matching places."
        : "Voyageurs, dates et particularités — puis on vous propose les lieux.") +
      "</p>" +
      "</aside>"
    );
  }

  function syncBookPlaces(selectedId) {
    var sel = document.getElementById("cmCarteBookPlace");
    if (!sel) return;
    var cur = selectedId != null ? String(selectedId) : sel.value;
    var pins = visiblePins()
      .slice()
      .sort(function (a, b) {
        return String(a.name || "").localeCompare(String(b.name || ""), "fr");
      });
    sel.innerHTML =
      '<option value="">' +
      (isEn ? "— Choose a place —" : "— Choisir un lieu —") +
      "</option>" +
      pins
        .map(function (p) {
          return (
            '<option value="' +
            escapeHtml(String(p.id)) +
            '">' +
            escapeHtml(p.name) +
            "</option>"
          );
        })
        .join("");
    if (cur && pins.some(function (p) {
      return String(p.id) === String(cur);
    })) {
      sel.value = String(cur);
    }
  }

  function selectBookPlace(pinOrId, opts) {
    opts = opts || {};
    var id = pinOrId && typeof pinOrId === "object" ? pinOrId.id : pinOrId;
    if (id == null) return;
    syncBookPlaces(id);
    var sel = document.getElementById("cmCarteBookPlace");
    if (sel) {
      sel.value = String(id);
      /* Met à jour le calendrier (jours barrés / fenêtre dispo) */
      try {
        sel.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (e) {
        var ev = document.createEvent("Event");
        ev.initEvent("change", true, true);
        sel.dispatchEvent(ev);
      }
    }
    var book = document.getElementById("cmCarteBook");
    if (book) {
      book.classList.add("is-place-set");
      if (opts.flash) {
        book.classList.add("is-flash");
        setTimeout(function () {
          book.classList.remove("is-flash");
        }, 900);
      }
    }
    if (opts.scroll && book) {
      book.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function mountCarteBook() {
    var box = document.getElementById("cmCarteBook");
    if (!box) return;
    if (box.getAttribute("data-bound") === "1") {
      syncBookPlaces();
      return;
    }
    box.setAttribute("data-bound", "1");

    var months = isEn
      ? [
          "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December",
        ]
      : [
          "janvier", "février", "mars", "avril", "mai", "juin",
          "juillet", "août", "septembre", "octobre", "novembre", "décembre",
        ];
    var dow = isEn
      ? ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
      : ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"];

    var book = {
      viewY: new Date().getFullYear(),
      viewM: new Date().getMonth(),
      start: null,
      end: null,
      disposByPlace: {},
      disposLoaded: false,
    };

    var titleEl = document.getElementById("cmCarteBookCalTitle");
    var rangeEl = document.getElementById("cmCarteBookRange");
    var gridEl = document.getElementById("cmCarteBookGrid");
    var guestsEl = document.getElementById("cmCarteBookGuests");
    var placeEl = document.getElementById("cmCarteBookPlace");
    var submitBtn = document.getElementById("cmCarteBookSubmit");
    var prevBtn = document.getElementById("cmCarteBookPrev");
    var nextBtn = document.getElementById("cmCarteBookNext");
    syncBookPlaces();

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
    function selectedPlaceId() {
      return placeEl && placeEl.value ? String(placeEl.value) : "";
    }
    function placeDispos() {
      var id = selectedPlaceId();
      if (!id) return null;
      var list = book.disposByPlace[id];
      if (!list || !list.length) return null;
      return list;
    }
    function dayInDispo(d) {
      var dispos = placeDispos();
      if (!dispos) return true; /* pas de fenêtre connue → jours futurs OK */
      var key = ymd(d);
      for (var i = 0; i < dispos.length; i++) {
        if (key >= dispos[i].date_debut && key <= dispos[i].date_fin) return true;
      }
      return false;
    }
    function pruneSelectionToDispo() {
      if (book.start && !dayInDispo(book.start)) {
        book.start = null;
        book.end = null;
      }
      if (book.end && !dayInDispo(book.end)) {
        book.end = null;
      }
    }
    function loadPlaceDispos() {
      if (book.disposLoaded) return Promise.resolve();
      return fetch("/api/coins-marocain/proprietes.json", { credentials: "omit" })
        .then(function (r) {
          return r.ok ? r.json() : null;
        })
        .then(function (data) {
          book.disposLoaded = true;
          var props = (data && data.proprietes) || [];
          props.forEach(function (p) {
            if (!p || p.id == null) return;
            book.disposByPlace[String(p.id)] = (p.disponibilites || []).map(function (d) {
              return {
                date_debut: d.date_debut,
                date_fin: d.date_fin,
              };
            });
          });
          pruneSelectionToDispo();
          renderCal();
        })
        .catch(function () {
          book.disposLoaded = true;
        });
    }

    function setCalOpen(open) {
      var cal = document.getElementById("cmCarteBookCal");
      var datesBtn = document.getElementById("cmCarteBookDatesBtn");
      if (!cal) return;
      cal.hidden = !open;
      box.classList.toggle("is-cal-open", !!open);
      if (datesBtn) datesBtn.setAttribute("aria-expanded", open ? "true" : "false");
    }

    function syncRange() {
      if (!rangeEl) return;
      var dispos = placeDispos();
      if (book.start && book.end) {
        rangeEl.textContent = isEn
          ? fmt(book.start) + " — " + fmt(book.end)
          : fmt(book.start) + " — " + fmt(book.end);
      } else if (book.start) {
        rangeEl.textContent = isEn
          ? fmt(book.start) + " — check-out"
          : fmt(book.start) + " — départ";
      } else if (dispos && selectedPlaceId()) {
        var d0 = dispos[0];
        rangeEl.textContent = isEn
          ? d0.date_debut.slice(8, 10) + "/" + d0.date_debut.slice(5, 7) +
            " — " + d0.date_fin.slice(8, 10) + "/" + d0.date_fin.slice(5, 7)
          : d0.date_debut.slice(8, 10) + "/" + d0.date_debut.slice(5, 7) +
            " — " + d0.date_fin.slice(8, 10) + "/" + d0.date_fin.slice(5, 7);
      } else {
        rangeEl.textContent = isEn ? "Check-in — Check-out" : "Arrivée — Départ";
      }
    }

    function renderCal() {
      if (!gridEl || !titleEl) return;
      titleEl.textContent = months[book.viewM] + " " + book.viewY;
      gridEl.innerHTML = "";
      dow.forEach(function (d) {
        var el = document.createElement("div");
        el.className = "cm-carte-book-dow";
        el.textContent = d;
        gridEl.appendChild(el);
      });
      var first = new Date(book.viewY, book.viewM, 1);
      var startDow = (first.getDay() + 6) % 7;
      var daysInMonth = new Date(book.viewY, book.viewM + 1, 0).getDate();
      var i;
      for (i = 0; i < startDow; i++) {
        var empty = document.createElement("div");
        empty.className = "cm-carte-book-day out";
        gridEl.appendChild(empty);
      }
      var t0 = today();
      for (i = 1; i <= daysInMonth; i++) {
        (function (day) {
          var d = new Date(book.viewY, book.viewM, day);
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "cm-carte-book-day";
          btn.textContent = String(day);
          var past = d < t0;
          var closed = !past && !dayInDispo(d);
          if (past) {
            btn.disabled = true;
            btn.classList.add("past");
          } else if (closed) {
            btn.disabled = true;
            btn.classList.add("unavailable");
            btn.title = isEn ? "Unavailable" : "Indisponible";
          }
          if (!past && !closed) {
            if (sameDay(d, book.start) || sameDay(d, book.end)) btn.classList.add("on");
            if (book.start && book.end && d > book.start && d < book.end) {
              btn.classList.add("in");
            }
          }
          btn.addEventListener("click", function () {
            if (btn.disabled) return;
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
            if (book.start && book.end) setCalOpen(false);
          });
          gridEl.appendChild(btn);
        })(i);
      }
      syncRange();
    }

    if (placeEl) {
      placeEl.addEventListener("change", function () {
        pruneSelectionToDispo();
        /* Afficher août si fenêtre connue pour le lieu */
        var dispos = placeDispos();
        if (dispos && dispos[0] && dispos[0].date_debut) {
          var parts = dispos[0].date_debut.split("-");
          if (parts.length === 3) {
            book.viewY = parseInt(parts[0], 10);
            book.viewM = parseInt(parts[1], 10) - 1;
          }
        }
        renderCal();
      });
    }
    loadPlaceDispos();

    if (prevBtn) {
      prevBtn.addEventListener("click", function () {
        book.viewM -= 1;
        if (book.viewM < 0) {
          book.viewM = 11;
          book.viewY -= 1;
        }
        renderCal();
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        book.viewM += 1;
        if (book.viewM > 11) {
          book.viewM = 0;
          book.viewY += 1;
        }
        renderCal();
      });
    }
    var datesBtn = document.getElementById("cmCarteBookDatesBtn");
    if (datesBtn) {
      datesBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        setCalOpen(box.classList.contains("is-cal-open") ? false : true);
      });
    }
    if (!state.bookOutsideBound) {
      state.bookOutsideBound = true;
      document.addEventListener("click", function (ev) {
        var live = document.getElementById("cmCarteBook");
        if (!live || !live.classList.contains("is-cal-open")) return;
        if (live.contains(ev.target)) return;
        live.classList.remove("is-cal-open");
        var cal = document.getElementById("cmCarteBookCal");
        if (cal) cal.hidden = true;
        var btn = document.getElementById("cmCarteBookDatesBtn");
        if (btn) btn.setAttribute("aria-expanded", "false");
      });
    }

    box.querySelectorAll("[data-trait]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        btn.classList.toggle("on");
      });
    });

    if (submitBtn) {
      submitBtn.addEventListener("click", function () {
        var traits = { privatisation: false, piscine: false, restaurant: false };
        box.querySelectorAll("[data-trait]").forEach(function (btn) {
          var key = btn.getAttribute("data-trait");
          if (key && traits.hasOwnProperty(key)) {
            traits[key] = btn.classList.contains("on");
          }
        });
        state.search = {
          applied: true,
          guests: parseInt((guestsEl && guestsEl.value) || "0", 10) || 0,
          traits: traits,
          start: book.start,
          end: book.end,
        };
        var hint = document.getElementById("cmCarteBookHint");
        if (hint) {
          hint.textContent = isEn
            ? "Matching places below — vedettes first, then the rest."
            : "Lieux proposés ci-dessous — vedettes en haut, les autres ensuite.";
        }
        refresh();
        var dir = document.getElementById("pres-de-vous");
        if (dir) dir.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }

    renderCal();
  }

  function renderHeroVideos() {
    var row = document.querySelector(".cm-hero-videos");
    if (!row) return;
    var picks = featuredVisible().slice(0, 4);
    if (!picks.length) {
      row.innerHTML =
        '<p class="cm-hero-empty">' +
        (isEn
          ? "No featured places for this search — see proposed listings below."
          : "Pas de vedette pour cette recherche — les propositions sont dans le répertoire.") +
        "</p>";
      return;
    }
    row.innerHTML = picks
      .map(function (pin) {
        return (
          '<div role="listitem">' +
          storyCardHtml(pin, "cm-story-card--mini") +
          "</div>"
        );
      })
      .join("");
    bindHeroVideoHover(row);
  }

  function renderHeroFeatured() {
    var el = document.getElementById("cmCarteHeroVisual");
    if (!el) return;
    if (!document.getElementById("cmCarteBook")) {
      el.innerHTML =
        '<div class="cm-hero-media-row">' +
        carteBookHtml() +
        '<p class="cm-hero-kicker">' +
        (isEn ? "Featured listings" : "Annonces vedettes") +
        "</p>" +
        '<div class="cm-hero-videos" role="list"></div>' +
        "</div>";
      el.removeAttribute("aria-hidden");
      mountCarteBook();
    }
    renderHeroVideos();
  }

  function pinPrice(pin) {
    var row = (pin.packages && pin.packages[0]) || (pin.services && pin.services[0]);
    if (row && row.price) {
      return { price: row.price, unit: row.unit || row.name || "" };
    }
    return {
      price: isEn ? "From 500 MAD" : "Dès 500 DH",
      unit: isEn ? "confirm with Yasmine" : "confirmation Yasmine",
    };
  }

  function pinPriceNum(pin) {
    var m = String(pinPrice(pin).price).replace(",", ".").match(/(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : 99999;
  }

  function pinScore(pin) {
    var views = Number((pin.stats && pin.stats.views) || pin.views || 0);
    var featured = isFeaturedPin(pin);
    var raw = 7.8 + (featured ? 1.0 : 0) + Math.min(1.0, views / 2000);
    var score = Math.round(raw * 10) / 10;
    var reviews = Math.max(Math.round(views / 20), featured ? 28 : 12);
    var label = score >= 9
      ? (isEn ? "Exceptional" : "Exceptionnel")
      : score >= 8.5
        ? (isEn ? "Superb" : "Superbe")
        : score >= 8
          ? (isEn ? "Very good" : "Très bien")
          : (isEn ? "Good" : "Bien");
    return { score: score.toFixed(1), reviews: reviews, label: label };
  }

  function pinLoc(pin) {
    var addr = String(pin.address || "");
    var parts = addr.split(",").map(function (p) { return p.trim(); }).filter(Boolean);
    if (parts.length) return parts[0];
    return pin.district || zoneLabel(pin.zone) || pin.city || "Marrakech";
  }

  function pinFacts(pin) {
    var cat = categoryLabel(pin, true) || "Lieu";
    cat = cat.charAt(0) + cat.slice(1).toLowerCase();
    var bits = [cat];
    (pin.services || []).slice(0, 3).forEach(function (s) {
      var name = typeof s === "string" ? s : s && s.name;
      if (name) bits.push(name);
    });
    return bits.join(" • ");
  }

  function ensureDirSort() {
    var head = document.querySelector(".cm-carte-feed-head");
    if (!head || document.getElementById("cmDirSort")) return;
    var label = document.createElement("label");
    label.className = "cm-dir-sort";
    label.innerHTML =
      (isEn ? "Sort by " : "Trier par ") +
      '<select id="cmDirSort">' +
      '<option value="featured">' + (isEn ? "Our top picks" : "Nos coups de cœur") + "</option>" +
      '<option value="price">' + (isEn ? "Lowest price" : "Prix (plus bas)") + "</option>" +
      '<option value="score">' + (isEn ? "Guest rating" : "Note") + "</option>" +
      "</select>";
    head.appendChild(label);
    document.getElementById("cmDirSort").addEventListener("change", function (ev) {
      state.sort = ev.target.value || "featured";
      renderFeed();
    });
  }

  function dirMediaHtml(pin) {
    var poster = posterUrl(pin);
    var remote = /youtu\.be|youtube\.com|vimeo\.com/i.test(pin.video_url || "");
    var src = remote ? "" : snippetUrl(pin);
    var featured = isFeaturedPin(pin);
    var fiche = placeFicheUrl(pin) || "#";
    var badge = featured
      ? '<span class="cm-badge cm-badge--tendance cm-badge--story-mini">' +
        (isEn ? "Featured" : "Mis en avant") +
        "</span>"
      : "";
    var heart =
      '<button type="button" class="cm-dir-heart" data-dir-heart="1" aria-label="' +
      (isEn ? "Save" : "Enregistrer") +
      '">♡</button>';
    var hit =
      '<a class="cm-dir-photo-hit" href="' +
      escapeHtml(fiche) +
      '" data-dir-fiche="1" aria-label="' +
      escapeHtml(pin.name) +
      '"></a>';
    if (!src) {
      return (
        '<div class="cm-dir-photo" style="background-image:url(\'' +
        escapeHtml(poster) +
        "')\">" +
        hit +
        badge +
        heart +
        "</div>"
      );
    }
    return (
      '<div class="cm-dir-photo">' +
      hit +
      '<img class="cm-dir-poster" alt="" src="' +
      escapeHtml(poster) +
      '" loading="lazy" decoding="async">' +
      '<video class="cm-dir-video" muted playsinline loop preload="none" poster="' +
      escapeHtml(poster) +
      '" data-src="' +
      escapeHtml(src) +
      '" hidden></video>' +
      badge +
      heart +
      "</div>"
    );
  }

  function dirCardHtml(pin) {
    var p = pinPrice(pin);
    var s = pinScore(pin);
    var loc = pinLoc(pin);
    var fiche = placeFicheUrl(pin) || (isEn ? "/en/villas-riads" : "/carte/hebergement");
    return (
      '<article class="cm-dir-card" data-dir-pin="' +
      escapeHtml(String(pin.id)) +
      '" data-open-fiche="1" data-pin-id="' +
      escapeHtml(String(pin.id)) +
      '">' +
      dirMediaHtml(pin) +
      '<div class="cm-dir-body">' +
      "<h3>" +
      escapeHtml(pin.name) +
      "</h3>" +
      '<div class="cm-dir-loc">' +
      "<span>" +
      escapeHtml(loc) +
      "</span>" +
      '<button type="button" class="cm-dir-maplink" data-dir-map="1">' +
      (isEn ? "Show on map" : "Afficher sur la carte") +
      "</button>" +
      '<span class="cm-dir-dist">· ' +
      escapeHtml(zoneLabel(pin.zone) || "Marrakech") +
      "</span></div>" +
      '<div class="cm-dir-facts">' +
      escapeHtml(pinFacts(pin)) +
      "</div>" +
      (pin.description
        ? '<p class="cm-dir-desc">' + escapeHtml(pin.description) + "</p>"
        : "") +
      '<div class="cm-dir-perk">' +
      (isEn ? "Filmed on site" : "Vidéo filmée sur place") +
      "</div></div>" +
      '<div class="cm-dir-side">' +
      '<div class="cm-dir-score">' +
      '<div class="cm-dir-score-text"><strong>' +
      escapeHtml(s.label) +
      "</strong><span>" +
      s.reviews +
      (isEn ? " reviews" : " avis") +
      "</span></div>" +
      '<div class="cm-dir-score-box">' +
      s.score +
      "</div></div>" +
      '<div class="cm-dir-deal">' +
      '<div class="cm-dir-stay">' +
      escapeHtml(p.unit) +
      "</div>" +
      '<div class="cm-dir-price">' +
      escapeHtml(p.price) +
      "</div>" +
      '<div class="cm-dir-taxes">' +
      (isEn ? "Taxes and fees extra" : "Taxes et frais en sus") +
      "</div>" +
      '<a class="cm-dir-cta" data-dir-fiche="1" href="' +
      escapeHtml(fiche) +
      '">' +
      (isEn ? "See the place" : "Voir la fiche") +
      "</a>" +
      '<a class="cm-dir-link" data-dir-fiche="1" href="' +
      escapeHtml(fiche) +
      '">' +
      (isEn ? "Property details" : "Détails du lieu") +
      "</a></div></div></article>"
    );
  }

  function renderFeed() {
    if (!feedEl) return;
    ensureDirSort();
    var title = document.getElementById("cmCarteFeedTitle");
    var visible = otherVisible().slice().sort(function (a, b) {
      if (state.sort === "price") return pinPriceNum(a) - pinPriceNum(b);
      if (state.sort === "score") return parseFloat(pinScore(b).score) - parseFloat(pinScore(a).score);
      return String(a.name || "").localeCompare(String(b.name || ""), "fr");
    });
    var searched = !!(state.search && state.search.applied);
    if (title) {
      if (!visible.length) {
        title.textContent = searched
          ? (isEn ? "No other matching places" : "Aucun autre lieu pour cette recherche")
          : (isEn ? "Directory" : "Répertoire");
      } else {
        title.textContent = searched
          ? (isEn
            ? "Proposed places · " + visible.length
            : "Lieux proposés · " + visible.length)
          : (isEn
            ? "Directory · " + visible.length
            : "Répertoire · " + visible.length);
      }
    }
    if (!visible.length) {
      feedEl.innerHTML =
        '<p class="cm-carte-feed-empty">' +
        (searched
          ? (isEn
            ? "Try fewer filters, or another theme."
            : "Élargissez les particularités, ou changez de thème.")
          : (isEn
            ? "No other filmed places for this filter."
            : "Aucun autre lieu en vidéo pour ce filtre.")) +
        "</p>";
      return;
    }
    feedEl.innerHTML = visible.map(dirCardHtml).join("");
    bindPreviewVideos(feedEl);
  }

  function refresh() {
    markEmptyChips();
    renderMarkers();
    renderHeroVideos();
    renderFeed();
  }

  function switchMode(mode) {
    if (!modeRoot) return;
    state.mode = mode === "zone" ? "zone" : "theme";
    modeRoot.querySelectorAll("button").forEach(function (b) {
      b.classList.toggle("on", b.getAttribute("data-mode") === state.mode);
    });
    if (filterRoot) filterRoot.hidden = state.mode !== "theme";
    if (zoneRoot) zoneRoot.hidden = state.mode !== "zone";
    refresh();
  }

  function destroyMap() {
    clearMarkers();
    if (state.engine === "leaflet" && state.map) {
      state.map.remove();
    }
    state.map = null;
    state.engine = null;
    state.info = null;
    state._mapFicheBound = null;
    mapEl.innerHTML = "";
  }

  function initLeaflet() {
    if (!window.L) throw new Error("leaflet_missing");
    destroyMap();
    var wrap = document.getElementById("cmCarteMapWrap");
    state.engine = "leaflet";
    state.map = L.map(mapEl, {
      zoomControl: true,
      scrollWheelZoom: false,
      wheelPxPerZoomLevel: 180,
      zoomSnap: 0.5,
      zoomDelta: 0.5,
      attributionControl: true,
    }).setView([state.center.lat, state.center.lng], 11);

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(state.map);

    function enableWheelZoom() {
      if (!state.map || state.map.scrollWheelZoom.enabled()) return;
      state.map.scrollWheelZoom.enable();
      if (wrap) wrap.classList.add("is-map-active");
    }
    function disableWheelZoom() {
      if (!state.map) return;
      state.map.scrollWheelZoom.disable();
      if (wrap) wrap.classList.remove("is-map-active");
    }
    state.map.on("click", enableWheelZoom);
    state.map.on("focus", enableWheelZoom);
    document.addEventListener(
      "click",
      function (ev) {
        if (!mapEl.contains(ev.target)) disableWheelZoom();
      },
      true
    );
    mapEl.addEventListener(
      "wheel",
      function (ev) {
        if (!state.map) return;
        if (state.map.scrollWheelZoom.enabled()) return;
        if (ev.ctrlKey || ev.metaKey) enableWheelZoom();
      },
      { passive: true }
    );

    function fixSize() {
      if (state.map) state.map.invalidateSize({ animate: false });
    }
    setTimeout(fixSize, 0);
    setTimeout(fixSize, 120);
    setTimeout(fixSize, 400);
    window.addEventListener("resize", fixSize);
    if (window.ResizeObserver && wrap) {
      var ro = new ResizeObserver(function () {
        fixSize();
      });
      ro.observe(wrap);
    }
    renderMarkers();
  }

  function loadLeaflet() {
    return new Promise(function (resolve, reject) {
      if (window.L) {
        resolve();
        return;
      }
      var s = document.createElement("script");
      s.src = "/assets/vendor/leaflet/leaflet.js?v=cm86";
      s.onload = function () {
        resolve();
      };
      s.onerror = function () {
        reject(new Error("leaflet_load"));
      };
      document.head.appendChild(s);
    });
  }

  function ensureLeafletMap() {
    return loadLeaflet().then(function () {
      initLeaflet();
    });
  }

  window.gm_authFailure = function () {
    if (state.engine === "leaflet") return;
    setStatus("Carte OpenStreetMap (Google Maps indisponible sur ce domaine).", false);
    ensureLeafletMap().catch(function () {
      setStatus("Impossible d’afficher la carte pour le moment.", true);
    });
  };

  function tryGoogle(key) {
    return new Promise(function (resolve) {
      if (!key || state.googleTried) {
        resolve(false);
        return;
      }
      state.googleTried = true;
      var settled = false;
      var timer = setTimeout(function () {
        if (settled) return;
        settled = true;
        resolve(false);
      }, 4500);

      window.initCmCarteMap = function () {
        if (settled) return;
        if (state.engine === "leaflet") {
          settled = true;
          clearTimeout(timer);
          resolve(false);
          return;
        }
        try {
          destroyMap();
          state.engine = "google";
          state.map = new google.maps.Map(mapEl, {
            center: state.center,
            zoom: 11,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: false,
            zoomControl: true,
          });
          renderMarkers();
          settled = true;
          clearTimeout(timer);
          setTimeout(function () {
            if (!mapEl.querySelector(".gm-style") && state.engine === "google") {
              ensureLeafletMap().then(function () {
                resolve(false);
              });
            } else {
              resolve(true);
            }
          }, 900);
        } catch (e) {
          settled = true;
          clearTimeout(timer);
          resolve(false);
        }
      };

      var s = document.createElement("script");
      s.src =
        "https://maps.googleapis.com/maps/api/js?key=" +
        encodeURIComponent(key) +
        "&callback=initCmCarteMap&language=fr&v=weekly";
      s.async = true;
      s.defer = true;
      s.onerror = function () {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(false);
      };
      document.head.appendChild(s);
    });
  }

  if (modeRoot) {
    modeRoot.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-mode]");
      if (!btn) return;
      switchMode(btn.getAttribute("data-mode") || "theme");
    });
  }

  /* Filtre zone : uniquement la barre sticky (évite le doublon « Par zone » en tête). */
  var byZoneBtn = document.getElementById("cmCarteByZone");
  if (byZoneBtn) {
    byZoneBtn.hidden = true;
    byZoneBtn.setAttribute("aria-hidden", "true");
    byZoneBtn.style.display = "none";
  }

  document.addEventListener("click", function (ev) {
    var heart = ev.target.closest("[data-dir-heart]");
    if (heart) {
      ev.preventDefault();
      ev.stopPropagation();
      heart.classList.toggle("on");
      heart.textContent = heart.classList.contains("on") ? "♥" : "♡";
      return;
    }
    var dir = ev.target.closest("[data-dir-pin]");
    if (dir) {
      if (ev.target.closest("[data-dir-heart]")) return;
      if (ev.target.closest("[data-dir-map]")) {
        ev.preventDefault();
        var mapId = dir.getAttribute("data-dir-pin");
        var mapPin = findPinById(mapId);
        if (!mapPin) return;
        var wrap = document.getElementById("cmCarteMapWrap");
        if (wrap) wrap.scrollIntoView({ behavior: "smooth", block: "center" });
        var marker = state.markers.filter(function (m) {
          return m && m._cmPin && String(m._cmPin.id) === String(mapId);
        })[0];
        if (marker && state.map) {
          if (state.engine === "leaflet") state.map.setView(marker.getLatLng(), Math.max(state.map.getZoom(), 13));
          else if (marker.getPosition) state.map.panTo(marker.getPosition());
        }
        return;
      }
      ev.preventDefault();
      var dirPin = findPinById(dir.getAttribute("data-dir-pin"));
      var hrefEl = ev.target.closest("a[href]") || dir.querySelector("a[data-dir-fiche]");
      goToPlaceFiche(dirPin || { detail_url: hrefEl && hrefEl.getAttribute("href") });
      return;
    }
    var ficheCard = ev.target.closest("[data-open-fiche][data-pin-id], a.cm-map-pin-hit");
    if (ficheCard) {
      ev.preventDefault();
      var pin = findPinById(ficheCard.getAttribute("data-pin-id"));
      goToPlaceFiche(pin || { detail_url: ficheCard.getAttribute("href") });
      return;
    }
    var pick = ev.target.closest("a[data-select-place][data-pin-id]");
    if (!pick) return;
    ev.preventDefault();
    var pinPick = findPinById(pick.getAttribute("data-pin-id"));
    if (pinPick) goToPlaceFiche(pinPick);
  });

  var exploreBtn = document.getElementById("cmCarteExplore");
  if (exploreBtn) {
    exploreBtn.addEventListener("click", function (e) {
      e.preventDefault();
      setMapFocus(true);
    });
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.body.classList.contains("cm-carte-mapfocus")) {
      setMapFocus(false);
    }
  });

  if (filterRoot) {
    filterRoot.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-filter]");
      if (!btn) return;
      var nextFilter = btn.getAttribute("data-filter") || "all";
      /* Filtre pins Odoo — sous-menu « Activités et expériences » → /carte/experiences */
      state.filter = nextFilter;
      filterRoot.querySelectorAll("button").forEach(function (b) {
        b.classList.toggle("on", b === btn);
      });
      setupRgFilters(state.filter);
      setupBeFilters(state.filter);
      refresh();
    });
  }

  if (zoneRoot) {
    zoneRoot.addEventListener("click", function (ev) {
      var btn = ev.target.closest("button[data-zone]");
      if (!btn) return;
      state.zone = btn.getAttribute("data-zone") || "all";
      zoneRoot.querySelectorAll("button").forEach(function (b) {
        b.classList.toggle("on", b === btn);
      });
      refresh();
    });
  }

  /* Feed mobile : laisser le href aller à la fiche lieu (plus d’interception Stories). */

  bindStoriesUi();

  wrapToolbarInner();

  foldSeoPads();

  var themeKey = resolveThemeKey();
  if (redirectExperiencesIfNeeded(themeKey)) return;
  if (themeKey) {
    state.filter = themeKey;
    state.mode = "theme";
    applyThemeSeo(themeKey);
    if (filterRoot) {
      filterRoot.querySelectorAll("button[data-filter]").forEach(function (b) {
        b.classList.toggle("on", b.getAttribute("data-filter") === themeKey);
      });
    }
    if (modeRoot) {
      modeRoot.querySelectorAll("button[data-mode]").forEach(function (b) {
        b.classList.toggle("on", b.getAttribute("data-mode") === "theme");
      });
    }
  }
  setupRgFilters(themeKey || state.filter);
  setupBeFilters(themeKey || state.filter);

  setStatus("Chargement de la carte…");
  Promise.all([
    fetch("/coins/api/carte/config").then(function (r) {
      return r.json();
    }),
    fetch("/coins/api/carte/pins").then(function (r) {
      return r.json();
    }),
    fetch("/partner-api/public/listings")
      .then(function (r) {
        return r.json();
      })
      .catch(function () {
        return { listings: [] };
      }),
    fetch("/api/coins-marocain/proprietes.json")
      .then(function (r) {
        return r.ok ? r.json() : { proprietes: [] };
      })
      .catch(function () {
        return { proprietes: [] };
      }),
  ])
    .then(function (pair) {
      var cfg = pair[0] || {};
      var pinsRes = pair[1] || {};
      var partnerRes = pair[2] || {};
      var propsRes = pair[3] || {};
      if (cfg.center) state.center = cfg.center;
      state.pins = (pinsRes.pins || []).filter(function (p) {
        var city = (p.city || "").toLowerCase();
        return city.indexOf("essaouira") === -1;
      });
      appendPartnerPins(state.pins, partnerRes.listings || []);
      mergeProprietes(propsRes);
      markEmptyChips();
      markEmptyRgChips();
      markEmptyBeChips();
      renderFeed();
      renderHeroFeatured();

      function statusCount() {
        setStatus(
          (visiblePins().length || 0) +
            " lieu" +
            (visiblePins().length > 1 ? "x" : "") +
            " en vidéo"
        );
        openRequestedPin();
      }
      if (cfg.google_maps_key) {
        return tryGoogle(cfg.google_maps_key).then(function (ok) {
          if (ok) {
            statusCount();
            return;
          }
          return ensureLeafletMap().then(statusCount);
        });
      }
      return ensureLeafletMap().then(statusCount);
    })
    .catch(function () {
      setStatus("Impossible de charger la carte pour le moment.", true);
      renderFeed();
    });

  var form = document.getElementById("cmCarteSignup");
  var formStatus = document.getElementById("cmCarteSignupStatus");
  var submitBtn = document.getElementById("cmCarteSignupSubmit");
  var placeNameInput = document.getElementById("cmCartePlaceName");
  var previewName = document.getElementById("cmCartePreviewName");
  var photoInput = document.getElementById("cmCartePhoto");
  var previewMedia = document.getElementById("cmCartePreviewMedia");
  var previewObjectUrl = null;
  var previewAside = document.querySelector(".cm-carte-preview");

  (function enhanceSignupFields() {
    if (!form) return;
    var ph = {
      place_name: isEn ? "e.g. Riad Ines" : "ex. Riad Ines",
      contact_name: isEn ? "Your name" : "Votre nom",
      email: "contact@exemple.com",
      phone: "+212 6 …",
      description: isEn
        ? "Ambiance, capacity, strengths — a few sentences."
        : "Ambiance, capacité, atouts — quelques phrases suffisent.",
    };
    Object.keys(ph).forEach(function (name) {
      var el = form.querySelector('[name="' + name + '"]');
      if (el && !el.getAttribute("placeholder")) el.setAttribute("placeholder", ph[name]);
    });
    var cat = form.querySelector('select[name="category"]');
    if (cat) {
      var theme = resolveThemeKey();
      var map = {
        hebergement: "hebergement",
        bien_etre: "bien_etre",
        route_gourmande: "resto",
        experiences: "experiences",
        evenements: "evenements",
      };
      if (theme && map[theme] && !cat.value) cat.value = map[theme];
      /* First real option visible (not empty dash) when theme page */
      if (theme && map[theme]) {
        var dash = cat.querySelector('option[value=""]');
        if (dash) dash.textContent = isEn ? "Theme" : "Thème";
      }
    }
    if (previewAside) previewAside.classList.add("is-empty-preview");
  })();

  function clearPreviewPhoto() {
    if (previewObjectUrl) {
      try {
        URL.revokeObjectURL(previewObjectUrl);
      } catch (e) {}
      previewObjectUrl = null;
    }
    if (!previewMedia) return;
    previewMedia.classList.add("cm-story-media--placeholder");
    previewMedia.classList.remove("cm-story-media--has-photo");
    var img = previewMedia.querySelector("img.cm-preview-photo");
    if (img) img.remove();
    var add = previewMedia.querySelector(".cm-preview-add");
    if (add) add.hidden = false;
    if (previewAside) previewAside.classList.add("is-empty-preview");
  }

  function setPreviewPhoto(file) {
    if (!previewMedia || !file) return;
    if (!/^image\//i.test(file.type || "") && !/\.(jpe?g|png|webp)$/i.test(file.name || "")) {
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      if (formStatus) {
        formStatus.textContent = "Photo trop lourde — maximum 5 Mo.";
        formStatus.className = "cm-carte-form-status err";
      }
      if (photoInput) photoInput.value = "";
      return;
    }
    clearPreviewPhoto();
    previewObjectUrl = URL.createObjectURL(file);
    var img = document.createElement("img");
    img.className = "cm-preview-photo";
    img.alt = "";
    img.src = previewObjectUrl;
    previewMedia.classList.remove("cm-story-media--placeholder");
    previewMedia.classList.add("cm-story-media--has-photo");
    var add = previewMedia.querySelector(".cm-preview-add");
    if (add) add.hidden = true;
    previewMedia.insertBefore(img, previewMedia.firstChild);
    if (previewAside) previewAside.classList.remove("is-empty-preview");
  }

  if (placeNameInput && previewName) {
    var syncPreviewName = function () {
      var v = (placeNameInput.value || "").trim();
      previewName.textContent = v || "Nom du lieu";
    };
    placeNameInput.addEventListener("input", syncPreviewName);
    syncPreviewName();
  }

  if (photoInput) {
    photoInput.addEventListener("change", function () {
      var f = photoInput.files && photoInput.files[0];
      if (f) setPreviewPhoto(f);
      else clearPreviewPhoto();
    });
  }
  if (previewMedia && photoInput) {
    var openPicker = function (ev) {
      if (ev) ev.preventDefault();
      photoInput.click();
    };
    previewMedia.addEventListener("click", openPicker);
    previewMedia.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter" || ev.key === " ") openPicker(ev);
    });
  }

  if (form) {
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (formStatus) {
        formStatus.textContent = "";
        formStatus.className = "cm-carte-form-status";
      }
      var placeName = (form.place_name.value || "").trim();
      var category = (form.category.value || "").trim();
      var email = (form.email.value || "").trim();
      var phone = (form.phone.value || "").trim();
      if (!placeName || !category || !email || !phone) {
        if (formStatus) {
          formStatus.textContent = "Merci de remplir tous les champs requis.";
          formStatus.className = "cm-carte-form-status err";
        }
        return;
      }
      var fd = new FormData();
      fd.append("place_name", placeName);
      fd.append("category", category);
      fd.append("contact_name", (form.contact_name.value || "").trim());
      fd.append("email", email);
      fd.append("phone", phone);
      fd.append("description", (form.description && form.description.value) || "");
      fd.append(
        "signup_channel",
        (form.signup_channel && form.signup_channel.value) || "carte"
      );
      if (photoInput && photoInput.files && photoInput.files[0]) {
        fd.append("photo", photoInput.files[0]);
      }
      if (submitBtn) submitBtn.disabled = true;
      if (formStatus) formStatus.textContent = "Création de l’espace…";
      fetch("/partner-api/signup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: placeName,
          category: category,
          contact_name: (form.contact_name.value || "").trim(),
          email: email,
          phone: phone,
          description: (form.description && form.description.value) || "",
          region: "Médina",
        }),
      })
        .then(function (r) {
          return r.json().then(function (j) {
            return { ok: r.ok && j && j.ok && j.portal_url, j: j };
          });
        })
        .then(function (res) {
          if (!res.ok) {
            var err = (res.j && res.j.error) || "";
            var msg = "Envoi impossible — réessayez ou WhatsApp.";
            if (err === "email") msg = "Courriel invalide.";
            if (formStatus) {
              formStatus.textContent = msg;
              formStatus.className = "cm-carte-form-status err";
            }
            return;
          }
          fetch("/coins/api/carte/signup", { method: "POST", body: fd }).catch(function () {});
          try {
            sessionStorage.setItem("cm_partner_token", res.j.token);
          } catch (e) {}
          if (formStatus) {
            formStatus.textContent = "Espace créé. Ouverture de la fiche…";
            formStatus.className = "cm-carte-form-status ok";
          }
          location.href = res.j.portal_url + (res.j.portal_url.indexOf("?") >= 0 ? "&" : "?") + "next=fiche#fiche";
        })
        .catch(function () {
          if (formStatus) {
            formStatus.textContent = "Réseau indisponible — réessayez plus tard.";
            formStatus.className = "cm-carte-form-status err";
          }
        })
        .finally(function () {
          if (submitBtn) submitBtn.disabled = false;
        });
    });
  }
})();
