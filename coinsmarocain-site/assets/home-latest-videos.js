(function(){var t=document.title||"";if((location.pathname==="/"||location.pathname==="")&&/Événements, mariage|Mariage, anniversaire/.test(t)){location.replace("/accueil");}})();
/* Accueil — 4 derniers endroits visités. Priorité : Nougat + Asrari, sans doublon Sacada. */
(function () {
  var root = document.getElementById("cmHomeLatestVideos");
  if (!root) return;

  var PRIORITY = [
    {
      id: 28,
      name: "Château Nougat",
      category: "Hébergement",
      snippet_url: "",
      photo_url: "/assets/img/evenements/chateau-nougat-poster.jpg",
      detail_url: "/lieux/chateau-nougat",
    },
    {
      id: 24,
      name: "Riad Asrari",
      category: "Hébergement",
      snippet_url: "/assets/video/riad-asrari-piscine.mp4",
      photo_url: "/assets/img/evenements/riad-asrari-piscine-poster.jpg",
      detail_url: "/lieux/riad-asrari-medina-marrakech",
    },
  ];

  var FALLBACK = [
    PRIORITY[0],
    PRIORITY[1],
    {
      id: 19,
      name: "La Casa Ysabella",
      category: "Hébergement",
      snippet_url: "/assets/video/casa-ysabella-patio.mp4",
      photo_url: "/assets/img/evenements/casa-ysabella-patio-poster.jpg",
      detail_url: "/lieux/riad-medina-marrakech-la-casa-ysabella",
    },
    {
      id: 5,
      name: "Dar Sacada",
      category: "Bien-être",
      snippet_url: "/assets/video/dar-sacada-detente-snippet.mp4",
      photo_url: "/assets/img/evenements/dar-sacada-detente-poster.jpg",
      detail_url: "/lieux/dar-sacada",
    },
  ];

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function categoryLabel(pin) {
    if (pin.category) return pin.category;
    if (pin.pillar_label) return pin.pillar_label;
    var cats = pin.categories || [];
    for (var i = 0; i < cats.length; i++) {
      if (cats[i].code && cats[i].code !== "decouverte") return cats[i].label || cats[i].code;
    }
    return cats[0] ? cats[0].label || "Lieu" : "Lieu";
  }

  function mediaSrc(pin) {
    return pin.snippet_url || "";
  }

  function bustPoster(url) {
    if (!url) return url;
    if (/[?&]v=/.test(url)) return url;
    if (/\/assets\/img\/evenements\//.test(url)) {
      return url + (url.indexOf("?") >= 0 ? "&" : "?") + "v=cm172";
    }
    return url;
  }

  function posterOf(pin) {
    var url = "";
    if (pin.photo_url && !/\/api\/coins-marocain\/photos\//.test(pin.photo_url)) {
      url = pin.photo_url;
    } else {
      var u = pin.snippet_url || pin.video_url || "";
      var m = u.match(/\/assets\/video\/([^/?#]+?)(?:-snippet)?\.mp4/i);
      if (m) {
        var base = m[1].replace(/-snippet$/i, "");
        url = "/assets/img/evenements/" + base + "-poster.jpg";
      } else {
        url = pin.photo_url || "/assets/img/forfaits-hero.jpg";
      }
    }
    return bustPoster(url);
  }

  function saveData() {
    try {
      return navigator.connection && navigator.connection.saveData;
    } catch (e) {
      return false;
    }
  }

  function cardHtml(pin) {
    var src = mediaSrc(pin);
    var poster = posterOf(pin);
    var media =
      '<img class="cm-story-media cm-story-poster" alt="" src="' +
      escapeHtml(poster) +
      '" loading="lazy" decoding="async">' +
      (src
        ? '<video class="cm-story-media cm-story-video" muted playsinline loop preload="none" poster="' +
          escapeHtml(poster) +
          '" data-src="' +
          escapeHtml(src) +
          '" hidden></video>'
        : "");
    return (
      '<a class="cm-story-card cm-home-video-card" href="' +
      escapeHtml(pin.detail_url || "/carte") +
      '">' +
      media +
      '<div class="cm-story-gradient"></div>' +
      '<span class="cm-story-cat">' +
      escapeHtml(categoryLabel(pin)) +
      "</span>" +
      '<span class="cm-story-play" aria-hidden="true"><span class="tri"></span></span>' +
      '<h3 class="cm-story-name">' +
      escapeHtml(pin.name) +
      "</h3></a>"
    );
  }

  function armVideo(vid) {
    if (!vid || vid.getAttribute("src")) return;
    var src = vid.getAttribute("data-src");
    if (!src) return;
    vid.setAttribute("src", src);
    try {
      vid.load();
    } catch (e) {}
  }

  function bindHoverPlay() {
    root.querySelectorAll("img.cm-story-poster").forEach(function (img) {
      img.addEventListener("error", function () {
        var card = img.closest("a");
        var vid = card && card.querySelector("video.cm-story-video");
        img.hidden = true;
        if (!vid) return;
        armVideo(vid);
        vid.preload = "metadata";
        vid.hidden = false;
      });
    });
    if (saveData()) return;
    root.querySelectorAll("a.cm-home-video-card").forEach(function (card) {
      var vid = card.querySelector("video.cm-story-video");
      var poster = card.querySelector("img.cm-story-poster");
      if (!vid) return;
      function play() {
        armVideo(vid);
        if (poster) poster.hidden = true;
        vid.hidden = false;
        var p = vid.play();
        if (p && p.catch) {
          p.catch(function () {
            vid.hidden = true;
            if (poster) poster.hidden = false;
          });
        }
        vid.onerror = function () {
          vid.hidden = true;
          if (poster) poster.hidden = false;
        };
      }
      function stop() {
        vid.pause();
        try {
          vid.currentTime = 0;
        } catch (e) {}
        vid.hidden = true;
        if (poster) poster.hidden = false;
      }
      card.addEventListener("mouseenter", play);
      card.addEventListener("mouseleave", stop);
    });
  }

  function render(items) {
    root.innerHTML = items
      .slice(0, 4)
      .map(cardHtml)
      .join("");
    bindHoverPlay();
  }

  function normalizePin(p) {
    return {
      id: p.id,
      name: p.name,
      category: categoryLabel(p),
      snippet_url: p.snippet_url || "",
      photo_url: p.photo_url || "",
      video_url: p.video_url || "",
      detail_url: p.detail_url || "/carte",
      categories: p.categories,
      pillar_label: p.pillar_label,
    };
  }

  function dedupe(items) {
    var seen = {};
    var out = [];
    items.forEach(function (p) {
      var key = String(p.name || "")
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim();
      var idKey = String(p.id || "");
      if (!key && !idKey) return;
      if (seen[key] || seen["id:" + idKey]) return;
      if (key) seen[key] = true;
      if (idKey) seen["id:" + idKey] = true;
      out.push(p);
    });
    return out;
  }

  function pickLatest(pins) {
    var byId = {};
    (pins || []).forEach(function (p) {
      if (p && p.id != null) byId[String(p.id)] = normalizePin(p);
    });

    var items = [];
    PRIORITY.forEach(function (pref) {
      var live = byId[String(pref.id)];
      if (live) {
        items.push(
          Object.assign({}, pref, {
            snippet_url: live.snippet_url || pref.snippet_url,
            photo_url: live.photo_url || pref.photo_url,
            detail_url: live.detail_url || pref.detail_url,
            category: live.category || pref.category,
          })
        );
      } else {
        items.push(pref);
      }
    });

    var sorted = (pins || [])
      .slice()
      .sort(function (a, b) {
        return (b.id || 0) - (a.id || 0);
      })
      .map(normalizePin);

    sorted.forEach(function (p) {
      if (items.length >= 4) return;
      items.push(p);
    });

    FALLBACK.forEach(function (fb) {
      if (items.length >= 4) return;
      items.push(fb);
    });

    return dedupe(items).slice(0, 4);
  }

  render(FALLBACK);

  var idle = window.requestIdleCallback || function (cb) {
    setTimeout(cb, 1200);
  };
  idle(function () {
    if (saveData()) return;
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    var t = setTimeout(function () {
      if (ctrl) ctrl.abort();
    }, 3500);
    fetch("/coins/api/carte/pins", ctrl ? { signal: ctrl.signal } : undefined)
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var pins = (data && data.pins) || [];
        render(pickLatest(pins));
      })
      .catch(function () {})
      .finally(function () {
        clearTimeout(t);
      });
  });
})();
