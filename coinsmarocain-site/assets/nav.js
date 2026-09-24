/* Coins Marocain — nav desktop (dropdowns) + overlay mobile (accordion) */
(function () {
  function fold(s) {
    return String(s || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "");
  }
  function isOldEventsHome() {
    var path = location.pathname || "/";
    if (path !== "/" && path !== "") return false;
    return /evenements, mariage|mariage, anniversaire|groupes et entreprise/.test(
      fold(document.title)
    );
  }
  function kickOldHome() {
    if (isOldEventsHome()) location.replace("/accueil");
  }
  kickOldHome();
  window.addEventListener("pageshow", kickOldHome);
})();
(function () {
  var WA_BASE = "https://wa.me/212660159177?text=";
  var defaultMsg =
    "Bonjour Yasmine, je souhaite un devis sur mesure pour Coins Marocain à Marrakech.";

  function waHref(msg) {
    return WA_BASE + encodeURIComponent(msg || defaultMsg);
  }

  var pageWa =
    (document.body && document.body.getAttribute("data-wa-msg")) || defaultMsg;

  var isEn = /^\/en(\/|$)/.test(location.pathname || "/");

  var NAV_FR = [
    {
      kind: "group",
      label: "Marrakech en vidéo",
      href: "/carte",
      children: [
        { href: "/carte/hebergement", label: "Hébergement" },
        { href: "/carte/bien-etre", label: "Bien-être" },
        { href: "/carte/route-gourmande", label: "Route gourmande" },
        { href: "/carte/evenements", label: "Événements" }
      ]
    },
    { href: "/activites", label: "Activités", kind: "link" },
    {
      kind: "group",
      label: "Réunir & célébrer",
      href: "/evenements",
      children: [
        { href: "/evenements/mariages", label: "Mariages" },
        { href: "/evenements/fiancailles", label: "Fiançailles" },
        { href: "/evenements/anniversaires", label: "Anniversaires" },
        { href: "/evenements/groupes-amis-famille", label: "Groupes" },
        { href: "/evenements/soiree-entreprise", label: "Soirée entreprise" },
        { href: "/evenements/seminaires-entreprise", label: "Séminaires" },
        { href: "/evenements/team-building-retraites", label: "Team building & retraites" },
        { href: "/evenements/evjf-evg", label: "EVJF / EVG" },
        { href: "/evenements/galas-levees-de-fonds", label: "Galas & levées de fonds" }
      ]
    },
    {
      kind: "group",
      label: "Notre sélection",
      href: "/notre-selection/comment-on-choisit",
      children: [
        { href: "/notre-selection/comment-on-choisit", label: "Comment on choisit" },
        { href: "/notre-selection/equipe", label: "L'équipe" }
      ]
    },
    { href: "/blog/", label: "Blogue", kind: "link" }
  ];

  var NAV_EN = [
    {
      kind: "group",
      label: "Marrakech on video",
      href: "/en/map",
      children: [
        { href: "/en/map/stay", label: "Stay" },
        { href: "/en/map/wellness", label: "Wellness" },
        { href: "/en/map/food", label: "Food trail" },
        { href: "/en/map/events", label: "Events" }
      ]
    },
    { href: "/activites", label: "Activities", kind: "link" },
    {
      kind: "group",
      label: "Gather & Celebrate",
      href: "/en/events",
      children: [
        { href: "/en/events/weddings", label: "Weddings" },
        { href: "/en/events/hen-stag", label: "Hen & stag" },
        { href: "/en/events", label: "All events" }
      ]
    },
    {
      kind: "group",
      label: "Our selection",
      href: "/notre-selection/comment-on-choisit",
      children: [
        { href: "/notre-selection/comment-on-choisit", label: "How we choose" },
        { href: "/notre-selection/equipe", label: "The team" }
      ]
    },
    { href: "/blog/", label: "Blog", kind: "link" }
  ];

  var NAV = isEn ? NAV_EN : NAV_FR;

  var SECONDARY = isEn
    ? [
        { href: "/partenaires", label: "Partners" },
        { href: "/carnet", label: "Traveller's notebook" },
        { href: "/en/villas-riads", label: "Villas & Riads" }
      ]
    : [
        { href: "/partenaires", label: "Partenaires" },
        { href: "/carnet", label: "Carnet du Voyageur" },
        { href: "/villas-riads-marrakech", label: "Villas & Riads" }
      ];

  var h = document.getElementById("siteHeader");
  var b = document.getElementById("burger");
  var o = document.getElementById("menuOverlay");
  var c = document.getElementById("menuClose");

  /* Pages crème (carte, contact…) : header toujours solide — sinon le menu
     redevient blanc sur fond clair dès le scroll=0 (illisible). */
  var forceSolid =
    !!h &&
    (document.body.classList.contains("cm-carte-page") ||
      document.body.classList.contains("cm-contact-page") ||
      document.body.getAttribute("data-header") === "solid");

  var solidPending = false;
  function solid() {
    if (!h || solidPending) return;
    if (forceSolid) {
      h.classList.add("solid");
      return;
    }
    solidPending = true;
    requestAnimationFrame(function () {
      solidPending = false;
      var y = window.pageYOffset || document.documentElement.scrollTop || 0;
      h.classList.toggle("solid", y > 40);
    });
  }
  window.addEventListener("scroll", solid, { passive: true });
  solid();

  function openMenu() {
    if (!o) return;
    o.classList.add("on");
    o.setAttribute("aria-hidden", "false");
    document.body.classList.add("cm-menu-open");
    document.body.style.overflow = "hidden";
    if (b) b.setAttribute("aria-expanded", "true");
  }
  function closeMenu() {
    if (!o) return;
    o.classList.remove("on");
    o.setAttribute("aria-hidden", "true");
    document.body.classList.remove("cm-menu-open");
    document.body.style.overflow = "";
    if (b) b.setAttribute("aria-expanded", "false");
  }
  if (b) {
    b.setAttribute("aria-expanded", "false");
    b.setAttribute("aria-controls", "menuOverlay");
    b.addEventListener("click", function (e) {
      e.preventDefault();
      if (o && o.classList.contains("on")) closeMenu();
      else openMenu();
    });
  }
  if (c) c.addEventListener("click", closeMenu);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeMenu();
  });

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

  function openPlanner(e) {
    if (e) e.preventDefault();
    closeMenu();
    loadPlanner(function () {
      if (window.CoinsPlanner) window.CoinsPlanner.open();
    });
  }

  function ensureDevisCta() {
    var actions = document.querySelector(".header-actions");
    if (!actions) {
      var inner = document.querySelector(".header-inner");
      if (!inner) return;
      actions = document.createElement("div");
      actions.className = "header-actions";
      var burger = document.getElementById("burger");
      if (burger) {
        burger.parentNode.insertBefore(actions, burger);
        actions.appendChild(burger);
      } else {
        inner.appendChild(actions);
      }
    }
    var existing = actions.querySelector(".cm-devis-cta");
    if (existing) {
      // Upgrade legacy WA link → planner CTA
      existing.classList.add("cm-planner-cta");
      existing.removeAttribute("target");
      existing.removeAttribute("rel");
      existing.href = "#planifier";
      existing.setAttribute("role", "button");
      existing.addEventListener("click", openPlanner);
      loadPlanner(function () {
        var labels = window.CoinsPlanner && window.CoinsPlanner.labels();
        if (!labels) return;
        existing.setAttribute("data-label-long", labels.long);
        existing.setAttribute("data-label-short", labels.short);
        existing.textContent =
          window.matchMedia("(min-width: 720px)").matches ? labels.long : labels.short;
      });
      return;
    }
    var a = document.createElement("a");
    a.className = "cm-devis-cta cm-planner-cta";
    a.href = "#planifier";
    a.setAttribute("role", "button");
    a.textContent = isEn ? "Plan my stay" : "Planifier mon séjour";
    a.addEventListener("click", openPlanner);
    var burgerEl = actions.querySelector(".burger");
    if (burgerEl) actions.insertBefore(a, burgerEl);
    else actions.appendChild(a);

    loadPlanner(function () {
      var labels = window.CoinsPlanner && window.CoinsPlanner.labels();
      if (!labels) return;
      a.setAttribute("data-label-long", labels.long);
      a.setAttribute("data-label-short", labels.short);
      function syncLabel() {
        a.textContent = window.matchMedia("(min-width: 720px)").matches
          ? labels.long
          : labels.short;
      }
      syncLabel();
      window.addEventListener("resize", syncLabel, { passive: true });
    });
  }

  function buildDesktopNav() {
    var inner = document.querySelector(".header-inner");
    if (!inner || inner.querySelector(".cm-desk-nav")) return;

    var nav = document.createElement("nav");
    nav.className = "cm-desk-nav";
    nav.setAttribute("aria-label", "Navigation principale");

    NAV.forEach(function (item) {
      if (item.kind === "group") {
        var wrap = document.createElement("div");
        wrap.className = "cm-desk-drop";
        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "cm-desk-drop-btn";
        btn.setAttribute("aria-expanded", "false");
        btn.innerHTML =
          '<span>' +
          item.label +
          '</span><svg width="10" height="6" viewBox="0 0 10 6" aria-hidden="true"><path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>';
        var panel = document.createElement("div");
        panel.className = "cm-desk-panel";
        panel.hidden = true;
        (item.children || []).forEach(function (ch) {
          var a = document.createElement("a");
          a.href = ch.href;
          a.textContent = ch.label;
          panel.appendChild(a);
        });
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          clearCloseTimer();
          var open = wrap.classList.contains("open");
          document.querySelectorAll(".cm-desk-drop.open").forEach(function (d) {
            d.classList.remove("open");
            var b2 = d.querySelector(".cm-desk-drop-btn");
            var p2 = d.querySelector(".cm-desk-panel");
            if (b2) b2.setAttribute("aria-expanded", "false");
            if (p2) p2.hidden = true;
          });
          if (!open) {
            wrap.classList.add("open");
            btn.setAttribute("aria-expanded", "true");
            panel.hidden = false;
          }
        });
        var closeTimer = null;
        function clearCloseTimer() {
          if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
          }
        }
        function openDrop() {
          clearCloseTimer();
          document.querySelectorAll(".cm-desk-drop.open").forEach(function (d) {
            if (d === wrap) return;
            d.classList.remove("open");
            var p2 = d.querySelector(".cm-desk-panel");
            var b2 = d.querySelector(".cm-desk-drop-btn");
            if (p2) p2.hidden = true;
            if (b2) b2.setAttribute("aria-expanded", "false");
          });
          wrap.classList.add("open");
          btn.setAttribute("aria-expanded", "true");
          panel.hidden = false;
        }
        function closeDrop() {
          wrap.classList.remove("open");
          btn.setAttribute("aria-expanded", "false");
          panel.hidden = true;
        }
        wrap.addEventListener("mouseenter", function () {
          if (window.matchMedia("(hover: hover) and (min-width: 980px)").matches) {
            openDrop();
          }
        });
        wrap.addEventListener("mouseleave", function () {
          if (window.matchMedia("(hover: hover) and (min-width: 980px)").matches) {
            clearCloseTimer();
            closeTimer = setTimeout(closeDrop, 180);
          }
        });
        wrap.appendChild(btn);
        wrap.appendChild(panel);
        nav.appendChild(wrap);
      } else {
        var a = document.createElement("a");
        a.href = item.href;
        a.className = "cm-desk-link";
        a.textContent = item.label;
        nav.appendChild(a);
      }
    });

    var brand = inner.querySelector(".brand");
    if (brand && brand.nextSibling) inner.insertBefore(nav, brand.nextSibling);
    else inner.insertBefore(nav, inner.firstChild);

    document.addEventListener("click", function () {
      document.querySelectorAll(".cm-desk-drop.open").forEach(function (d) {
        d.classList.remove("open");
        var b2 = d.querySelector(".cm-desk-drop-btn");
        var p2 = d.querySelector(".cm-desk-panel");
        if (b2) b2.setAttribute("aria-expanded", "false");
        if (p2) p2.hidden = true;
      });
    });
  }

  function rebuildOverlay(root) {
    if (!root) return;
    root.setAttribute("aria-hidden", "true");
    root.classList.remove("on");

    var eyebrow = root.querySelector(".m-eyebrow");
    var closeBtn = root.querySelector(".menu-close");
    Array.prototype.slice.call(root.children).forEach(function (n) {
      if (n !== closeBtn && n !== eyebrow) n.remove();
    });

    var scroll = document.createElement("div");
    scroll.className = "cm-overlay-scroll";

    function addSimple(href, label, cls) {
      var a = document.createElement("a");
      a.href = href;
      a.textContent = label;
      if (cls) a.className = cls;
      scroll.appendChild(a);
      return a;
    }

    NAV.forEach(function (item) {
      if (item.kind === "group") {
        var block = document.createElement("div");
        block.className = "cm-acc";
        var head = document.createElement("button");
        head.type = "button";
        head.className = "cm-acc-btn";
        head.setAttribute("aria-expanded", "false");
        head.innerHTML =
          "<span>" +
          item.label +
          '</span><svg width="12" height="8" viewBox="0 0 12 8" aria-hidden="true"><path d="M1 1l5 5 5-5" fill="none" stroke="currentColor" stroke-width="1.6"/></svg>';
        var body = document.createElement("div");
        body.className = "cm-acc-body";
        body.hidden = true;
        (item.children || []).forEach(function (ch) {
          var a = document.createElement("a");
          a.href = ch.href;
          a.textContent = ch.label;
          body.appendChild(a);
        });
        head.addEventListener("click", function () {
          var open = block.classList.toggle("open");
          head.setAttribute("aria-expanded", open ? "true" : "false");
          body.hidden = !open;
        });
        block.appendChild(head);
        block.appendChild(body);
        scroll.appendChild(block);
      } else {
        addSimple(item.href, item.label, "cm-overlay-link");
      }
    });

    SECONDARY.forEach(function (s) {
      addSimple(s.href, s.label, "cm-overlay-sec");
    });

    var cta = document.createElement("a");
    cta.className = "btn m-cta";
    cta.href = waHref(pageWa);
    cta.textContent = isEn ? "Custom quote" : "Devis sur mesure";
    cta.target = "_blank";
    cta.rel = "noopener noreferrer";
    scroll.appendChild(cta);

    if (closeBtn) root.appendChild(closeBtn);
    if (eyebrow) root.appendChild(eyebrow);
    root.appendChild(scroll);

    scroll.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", closeMenu);
    });
  }

  function ensureFooterLinks(root) {
    if (!root) return;
    var map = [
      { href: "/villas-riads-marrakech", re: /\/(forfaits|villas-riads-marrakech)\/?$/ },
      { href: "/evenements", re: /\/evenements\/?$/ },
      { href: "/activites", re: /\/activites\/?$/ }
    ];
    map.forEach(function (item) {
      root.querySelectorAll("a[href]").forEach(function (a) {
        var href = a.getAttribute("href") || "";
        if (item.re.test(href.replace(location.origin, ""))) {
          a.setAttribute("href", item.href);
        }
      });
    });
  }

  function ensureContactLink(root) {
    if (!root) return;
    if (root.querySelector('a[href="/contact"], a[href$="/contact"], a[href*="/contact.html"]')) return;
    var mail = root.querySelector('a[href^="mailto:info@coinsmarocain"]');
    var a = document.createElement("a");
    a.href = "/contact";
    a.textContent = "Nous contacter";
    if (mail && mail.parentNode) mail.parentNode.insertBefore(a, mail.nextSibling);
    else {
      var legal = ensureFootLegal(root);
      if (legal) legal.insertBefore(a, legal.firstChild);
      else root.appendChild(a);
    }
  }

  function ensureFootLegal(root) {
    if (!root) return null;
    var legal = root.querySelector(".foot-legal");
    if (!legal) {
      legal = document.createElement("nav");
      legal.className = "foot-legal";
      legal.setAttribute("aria-label", "Liens utiles");
      var bottom = root.querySelector(".foot-bottom");
      if (bottom) bottom.appendChild(legal);
      else root.appendChild(legal);
    }
    /* Ancien bug : liens injectés en enfants directs du footer (collés sans espace) */
    Array.prototype.slice.call(root.children).forEach(function (child) {
      if (child.tagName === "A" && child.getAttribute("href")) {
        legal.appendChild(child);
      }
    });
    return legal;
  }

  function ensureLegal(root, href, label, afterSel) {
    if (!root || root.querySelector('a[href*="' + href.replace(/^\//, "") + '"]')) return;
    var legal = ensureFootLegal(root);
    if (!legal) return;
    var after = null;
    (afterSel || []).some(function (sel) {
      after = legal.querySelector(sel);
      return !!after;
    });
    var a = document.createElement("a");
    a.href = href;
    a.textContent = label;
    if (after && after.parentNode) after.parentNode.insertBefore(a, after.nextSibling);
    else legal.appendChild(a);
  }

  var SOCIAL = [
    {
      key: "instagram",
      href: "https://www.instagram.com/coinsmarocain_/",
      label: "Instagram",
      match: "instagram.com",
    },
    {
      key: "facebook",
      href: "https://www.facebook.com/people/Coins-Marrakech/61592118442323/",
      label: "Facebook",
      match: "facebook.com",
    },
    {
      key: "linkedin",
      href: "https://www.linkedin.com/company/coins-marocain",
      label: "LinkedIn",
      match: "linkedin.com",
    },
  ];

  function ensureFootSocial(root) {
    if (!root) return null;
    var box = root.querySelector(".foot-social");
    if (box) return box;
    box = document.createElement("div");
    box.className = "foot-social";
    box.setAttribute("aria-label", isEn ? "Social networks" : "Réseaux sociaux");
    var legal = root.querySelector(".foot-legal");
    if (legal && legal.parentNode) {
      legal.parentNode.insertBefore(box, legal.nextSibling);
      return box;
    }
    var cols = root.querySelector(".footer-cols");
    if (cols && cols.lastElementChild) {
      cols.lastElementChild.appendChild(box);
      return box;
    }
    var brand = root.querySelector(".foot-brand");
    if (brand && brand.parentNode) {
      brand.parentNode.appendChild(box);
      return box;
    }
    var bottom = root.querySelector(".foot-bottom");
    if (bottom) root.insertBefore(box, bottom);
    else root.appendChild(box);
    return box;
  }

  function ensureSocial(root) {
    if (!root) return;
    var box = ensureFootSocial(root);
    if (!box) return;
    SOCIAL.forEach(function (net) {
      if (root.querySelector('a[href*="' + net.match + '"]') || box.querySelector('a[href*="' + net.match + '"]'))
        return;
      var a = document.createElement("a");
      a.className = "social-link";
      a.href = net.href;
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      a.setAttribute("aria-label", net.label + " Coins Marocain");
      a.textContent = net.label;
      box.appendChild(a);
    });
  }

  function ensureCrossPromo() {
    if (document.querySelector(".cm-xpromo")) return;
    var path = (location.pathname || "/").replace(/\/+$/, "") || "/";
    var variant = null;
    // Une variante fixe par page pilier — pas de rotation aléatoire
    if (
      path === "/forfaits" ||
      path.indexOf("/forfaits") === 0 ||
      path === "/villas-riads-marrakech" ||
      path.indexOf("/villas-riads-marrakech") === 0
    ) {
      variant = {
        text: "Découvrez ce lieu en vidéo → Voir sur la carte",
        href: "/carte",
        cta: "Voir la carte",
      };
    } else if (path === "/activites" || path.indexOf("/activites") === 0) {
      variant = {
        text: "Créateur de contenu ? Devenez ambassadeur vidéo de Coins Marocain →",
        href: "/partenaires#createur",
        cta: "Devenir créateur",
      };
    } else if (path === "/evenements" || path.indexOf("/evenements") === 0) {
      variant = {
        text: "Vous avez aimé votre séjour ? Parrainez vos proches →",
        href: "/partenaires#voyageur",
        cta: "Programme Ambassadeur",
      };
    } else if (path === "/partenaires" || path.indexOf("/partenaires") === 0) {
      variant = {
        text: "Vous aimez ce que vous voyez ? Investissez ici — BabInvest sélectionne et vérifie les projets immobiliers à Marrakech",
        href: "https://maisonrecherchee.fr/?utm_source=coinsmarocain&utm_medium=referral&utm_campaign=partenaires-babinvest",
        cta: "Découvrir BabInvest",
      };
    } else if (path === "/blog" || path.indexOf("/blog") === 0) {
      variant = {
        text: "Découvrez ce lieu en vidéo → Voir sur la carte",
        href: "/carte",
        cta: "Voir la carte",
      };
    }
    if (!variant) return;
    if (!document.querySelector('link[href*="cm-cross-promo.css"]')) {
      var link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = "/assets/cm-cross-promo.css?v=cm78";
      document.head.appendChild(link);
    }
    var foot =
      document.querySelector("footer.site-footer, footer.evt-footer, .site-footer, .evt-footer") ||
      document.querySelector("footer");
    if (!foot) return;
    var band = document.createElement("aside");
    band.className = "cm-xpromo";
    band.setAttribute("aria-label", "Découvrir aussi");
    band.innerHTML =
      '<div class="inner"><p>' +
      variant.text +
      '</p><a href="' +
      variant.href +
      '">' +
      variant.cta +
      "</a></div>";
    foot.parentNode.insertBefore(band, foot);
  }

  ensureDevisCta();
  buildDesktopNav();
  rebuildOverlay(o);
  document.querySelectorAll("footer, .site-footer, .foot, .footer-nav, .evt-footer").forEach(function (el) {
    ensureFooterLinks(el);
    ensureContactLink(el);
    ensureLegal(el, "/affiliation", "Affiliation", ['a[href*="confidentialite"]']);
    ensureLegal(el, "/wedding-planner", "Wedding planner", ['a[href*="affiliation"]', 'a[href*="confidentialite"]']);
    ensureLegal(el, "/journee-piscine", "Journée piscine", ['a[href*="wedding-planner"]']);
    ensureLegal(el, "/agence-de-voyage", "Agence de voyage", ['a[href*="journee-piscine"]']);
    var guideHref = (location.pathname || "").indexOf("/en/") === 0 ? "/en/guide-marrakech" : "/guide-marrakech";
    var guideLabel = (location.pathname || "").indexOf("/en/") === 0 ? "Day-trip ideas" : "Guide des escapades";
    ensureLegal(el, guideHref, guideLabel, ['a[href*="agence-de-voyage"]', 'a[href*="carnet"]', 'a[href*="blog"]', 'a[href*="activites"]']);
    ensureSocial(el);
  });
  ensureCrossPromo();
})();
