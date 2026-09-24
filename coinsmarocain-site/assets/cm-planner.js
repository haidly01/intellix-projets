/* Coins Marocain — planner séjour global (dates + budget + expériences) */
(function () {
  if (window.CoinsPlanner) return;

  var WA_BASE = "https://wa.me/212660159177?text=";
  // Sur links.coinsmarocain.com (vhost séparé), assets + API restent sur l’apex
  var SITE_ORIGIN =
    location.hostname === "links.coinsmarocain.com" ||
    location.hostname === "link.coinsmarocain.com"
      ? "https://coinsmarocain.com"
      : "";
  var CSS_HREF = SITE_ORIGIN + "/assets/cm-planner.css?v=cm149";

  var isEn =
    (document.documentElement.getAttribute("lang") || "")
      .toLowerCase()
      .indexOf("en") === 0 ||
    /^\/en(\/|$)/.test(location.pathname || "/");

  var I18N = isEn
    ? {
        title: "Plan my stay",
        sub: "Dates, budget from 500 DH, party size — Yasmine replies with a short proposal.",
        close: "Close",
        dates: "Dates",
        pickStart: "Select arrival",
        pickEnd: "Select departure",
        range: "From {a} to {b}",
        budget: "Budget (from 500 DH)",
        guests: "Number of people",
        guestsPh: "e.g. 8",
        eventType: "Event type",
        experience: "What I’m looking for",
        contact: "Your details",
        name: "Full name",
        phone: "Phone / WhatsApp",
        email: "Email",
        submit: "Send request",
        wa: "Continue on WhatsApp",
        sending: "Sending…",
        ok: "Thank you — we’ll get back to you shortly.",
        consent: "I agree to be contacted about this request (email or WhatsApp).",
        errConsent: "Please tick the consent box before sending.",
        errFields: "Please fill in name, email and phone.",
        errNet: "Network issue. Try again or use WhatsApp.",
        errServer: "Could not send. Try again or WhatsApp.",
        budgets: [
          { v: "500_1500", l: "From 500 DH" },
          { v: "1500_3000", l: "1,500 – 3,000 DH" },
          { v: "gt_3000", l: "3,000 DH +" },
        ],
        interests: [
          { v: "bien_etre", l: "Wellness / spa" },
          { v: "piscine", l: "Pool / villa" },
          { v: "gastronomie", l: "Gastronomy" },
          { v: "desert", l: "Desert / adventure" },
          { v: "culture", l: "Culture" },
          { v: "evenements", l: "Events / evenings" },
          { v: "mariage", l: "Wedding / hen" },
        ],
        eventTypes: [
          { v: "mariage", l: "Wedding" },
          { v: "evjf", l: "Hen / stag" },
          { v: "anniversaire", l: "Birthday" },
          { v: "soiree", l: "Private party" },
          { v: "team_building", l: "Team building" },
          { v: "gala", l: "Gala" },
          { v: "privatisation", l: "Venue buyout" },
          { v: "autre", l: "Other" },
        ],
        dow: ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
        months: [
          "January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December",
        ],
        waMsg:
          "Hi Yasmine, I’d like to plan a stay with Coins Marocain.\nDates: {dates}\nGuests: {guests}\nBudget: {budget}\nEvent: {event}\nLooking for: {exp}\nName: {name}\nPhone: {phone}\nEmail: {email}",
        ctaShort: "Plan stay",
        ctaLong: "Plan my stay",
      }
    : {
        title: "Planifier mon séjour",
        sub: "Dates, budget à partir de 500 DH et effectif — Yasmine vous répond avec une proposition courte.",
        close: "Fermer",
        dates: "Dates",
        pickStart: "Choisissez l’arrivée",
        pickEnd: "Choisissez le départ",
        range: "Du {a} au {b}",
        budget: "Budget (à partir de 500 DH)",
        guests: "Nombre de personnes",
        guestsPh: "ex. 8",
        eventType: "Type d’événement",
        experience: "Ce que je recherche",
        contact: "Vos coordonnées",
        name: "Nom complet",
        phone: "Téléphone / WhatsApp",
        email: "Courriel",
        submit: "Envoyer la demande",
        wa: "Continuer sur WhatsApp",
        sending: "Envoi en cours…",
        ok: "Merci — nous vous répondons rapidement.",
        consent: "J’accepte d’être contacté·e au sujet de cette demande (courriel ou WhatsApp).",
        errConsent: "Cochez la case de consentement avant d’envoyer.",
        errFields: "Merci de renseigner nom, courriel et téléphone.",
        errNet: "Réseau indisponible. Réessayez ou WhatsApp.",
        errServer: "Envoi impossible. Réessayez ou WhatsApp.",
        budgets: [
          { v: "500_1500", l: "À partir de 500 DH" },
          { v: "1500_3000", l: "1 500 – 3 000 DH" },
          { v: "gt_3000", l: "3 000 DH +" },
        ],
        interests: [
          { v: "bien_etre", l: "Bien-être / spa" },
          { v: "piscine", l: "Piscine / villa" },
          { v: "gastronomie", l: "Gastronomie" },
          { v: "desert", l: "Désert / aventure" },
          { v: "culture", l: "Culture" },
          { v: "evenements", l: "Événements / soirées" },
          { v: "mariage", l: "Mariage / EVJF" },
        ],
        eventTypes: [
          { v: "mariage", l: "Mariage" },
          { v: "evjf", l: "EVJF / EVG" },
          { v: "anniversaire", l: "Anniversaire" },
          { v: "soiree", l: "Soirée privée" },
          { v: "team_building", l: "Team building" },
          { v: "gala", l: "Gala" },
          { v: "privatisation", l: "Privatisation" },
          { v: "autre", l: "Autre" },
        ],
        dow: ["Lu", "Ma", "Me", "Je", "Ve", "Sa", "Di"],
        months: [
          "janvier", "février", "mars", "avril", "mai", "juin",
          "juillet", "août", "septembre", "octobre", "novembre", "décembre",
        ],
        waMsg:
          "Bonjour Yasmine, je souhaite planifier un séjour avec Coins Marocain.\nDates : {dates}\nPersonnes : {guests}\nBudget : {budget}\nÉvénement : {event}\nJe recherche : {exp}\nNom : {name}\nTél : {phone}\nEmail : {email}",
        ctaShort: "Planifier",
        ctaLong: "Planifier mon séjour",
      };

  var state = {
    viewY: 0,
    viewM: 0,
    start: null,
    end: null,
    budget: "500_1500",
    guests: "",
    eventType: "",
    lieuName: "",
    interests: {},
    open: false,
    lastFocus: null,
  };

  var els = {};

  function pad(n) {
    return n < 10 ? "0" + n : String(n);
  }

  function ymd(d) {
    return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
  }

  function parseYmd(s) {
    if (!s) return null;
    var p = s.split("-");
    if (p.length !== 3) return null;
    return new Date(+p[0], +p[1] - 1, +p[2]);
  }

  function todayStart() {
    var t = new Date();
    return new Date(t.getFullYear(), t.getMonth(), t.getDate());
  }

  function fmtShort(d) {
    if (!d) return "—";
    return pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + "/" + d.getFullYear();
  }

  function ensureCss() {
    if (document.querySelector('link[href*="cm-planner.css"]')) return;
    var link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = CSS_HREF;
    document.head.appendChild(link);
  }

  function defaultInterestsFromPage() {
    var body = document.body;
    var attr = (body && body.getAttribute("data-planner-interests")) || "";
    var fromAttr = attr
      .split(",")
      .map(function (s) {
        return s.trim();
      })
      .filter(Boolean);
    if (fromAttr.length) return fromAttr;

    var path = location.pathname || "/";
    var theme = (body && body.getAttribute("data-carte-theme")) || "";
    var out = [];

    if (/evenement|\/events|mariage|wedding|evjf|hen-stag|anniversaire|gala|team-building/i.test(path)) {
      out.push("evenements");
    }
    if (/mariage|wedding|evjf|hen-stag/i.test(path)) out.push("mariage");
    if (/bien-etre|wellness|piscine|journee-piscine/i.test(path) || theme === "bien_etre") {
      out.push("bien_etre");
    }
    if (/hebergement|stay|villas-riads|\/lieux\//i.test(path) || theme === "hebergement" || theme === "villas_riads") {
      out.push("piscine");
    }
    if (/route-gourmande|food|gastronom/i.test(path) || theme === "route_gourmande") {
      out.push("gastronomie");
    }
    if (/experiences|agafay|desert|ourika|plein-air|activites/i.test(path) || theme === "experiences" || theme === "plein_air") {
      out.push("desert");
    }
    if (/guide-marrakech|culture|medina/i.test(path)) out.push("culture");

    // unique
    var seen = {};
    return out.filter(function (c) {
      if (seen[c]) return false;
      seen[c] = true;
      return true;
    });
  }

  function buildDom() {
    if (document.getElementById("cmPlannerRoot")) return;

    var root = document.createElement("div");
    root.id = "cmPlannerRoot";
    root.className = "cm-planner-root";
    root.hidden = true;
    root.innerHTML =
      '<div class="cm-planner-backdrop" data-cm-planner-close="1"></div>' +
      '<div class="cm-planner-panel" role="dialog" aria-modal="true" aria-labelledby="cmPlannerTitle" tabindex="-1">' +
      '<div class="cm-planner-head">' +
      "<div><h2 id=\"cmPlannerTitle\">" +
      I18N.title +
      "</h2><p>" +
      I18N.sub +
      "</p></div>" +
      '<button type="button" class="cm-planner-close" data-cm-planner-close="1" aria-label="' +
      I18N.close +
      '">&times;</button>' +
      "</div>" +
      '<div class="cm-planner-body">' +
      '<div class="cm-planner-block">' +
      '<span class="cm-planner-label">' +
      I18N.dates +
      "</span>" +
      '<div class="cm-planner-cal-nav">' +
      '<button type="button" id="cmPlannerPrev" aria-label="Previous">‹</button>' +
      '<div class="cm-planner-cal-title" id="cmPlannerCalTitle"></div>' +
      '<button type="button" id="cmPlannerNext" aria-label="Next">›</button>' +
      "</div>" +
      '<p class="cm-planner-cal-range" id="cmPlannerRangeHint"></p>' +
      '<div class="cm-planner-cal-grid" id="cmPlannerGrid" role="grid"></div>' +
      "</div>" +
      '<div class="cm-planner-block">' +
      '<span class="cm-planner-label">' +
      I18N.budget +
      "</span>" +
      '<div class="cm-planner-chips" id="cmPlannerBudgets" role="group"></div>' +
      "</div>" +
      '<div class="cm-planner-block">' +
      '<span class="cm-planner-label" id="cmPlannerGuestsLabel">' +
      I18N.guests +
      "</span>" +
      '<div class="cm-planner-fields cm-planner-fields--guests">' +
      '<input type="number" id="cmPlannerGuests" min="1" max="500" step="1" inputmode="numeric" placeholder="' +
      I18N.guestsPh +
      '" aria-labelledby="cmPlannerGuestsLabel">' +
      "</div>" +
      "</div>" +
      '<div class="cm-planner-block">' +
      '<span class="cm-planner-label">' +
      I18N.experience +
      "</span>" +
      '<div class="cm-planner-chips" id="cmPlannerInterests" role="group"></div>' +
      "</div>" +
      '<div class="cm-planner-block" id="cmPlannerEventBlock" hidden>' +
      '<span class="cm-planner-label">' +
      I18N.eventType +
      "</span>" +
      '<div class="cm-planner-chips" id="cmPlannerEventTypes" role="group"></div>' +
      "</div>" +
      '<div class="cm-planner-block">' +
      '<span class="cm-planner-label">' +
      I18N.contact +
      "</span>" +
      '<div class="cm-planner-fields">' +
      "<label>" +
      I18N.name +
      '<input type="text" id="cmPlannerName" autocomplete="name" maxlength="120" required></label>' +
      "<label>" +
      I18N.phone +
      '<input type="tel" id="cmPlannerPhone" autocomplete="tel" maxlength="40" required></label>' +
      "<label>" +
      I18N.email +
      '<input type="email" id="cmPlannerEmail" autocomplete="email" maxlength="120" required></label>' +
      "</div>" +
      '<label class="cm-planner-consent" for="cmPlannerConsent">' +
      '<input type="checkbox" id="cmPlannerConsent" name="consent">' +
      "<span>" +
      I18N.consent +
      "</span></label>" +
      "</div>" +
      '<div class="cm-planner-actions">' +
      '<button type="button" class="cm-planner-submit" id="cmPlannerSubmit">' +
      I18N.submit +
      "</button>" +
      '<a class="cm-planner-wa" id="cmPlannerWa" href="#" target="_blank" rel="noopener noreferrer">' +
      I18N.wa +
      "</a>" +
      "</div>" +
      '<p class="cm-planner-status" id="cmPlannerStatus" role="status" aria-live="polite"></p>' +
      "</div></div>";

    document.body.appendChild(root);

    els.root = root;
    els.panel = root.querySelector(".cm-planner-panel");
    els.grid = document.getElementById("cmPlannerGrid");
    els.title = document.getElementById("cmPlannerCalTitle");
    els.rangeHint = document.getElementById("cmPlannerRangeHint");
    els.budgets = document.getElementById("cmPlannerBudgets");
    els.interests = document.getElementById("cmPlannerInterests");
    els.eventBlock = document.getElementById("cmPlannerEventBlock");
    els.eventTypes = document.getElementById("cmPlannerEventTypes");
    els.status = document.getElementById("cmPlannerStatus");
    els.submit = document.getElementById("cmPlannerSubmit");
    els.wa = document.getElementById("cmPlannerWa");
    els.name = document.getElementById("cmPlannerName");
    els.phone = document.getElementById("cmPlannerPhone");
    els.email = document.getElementById("cmPlannerEmail");
    els.consent = document.getElementById("cmPlannerConsent");
    els.guests = document.getElementById("cmPlannerGuests");

    I18N.budgets.forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cm-planner-chip";
      btn.setAttribute("data-budget", b.v);
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = b.l;
      btn.addEventListener("click", function () {
        state.budget = state.budget === b.v ? "500_1500" : b.v;
        syncBudgetChips();
        refreshWa();
      });
      els.budgets.appendChild(btn);
    });

    I18N.interests.forEach(function (it) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cm-planner-chip";
      btn.setAttribute("data-interest", it.v);
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = it.l;
      btn.addEventListener("click", function () {
        state.interests[it.v] = !state.interests[it.v];
        syncInterestChips();
        syncEventBlock();
        refreshWa();
      });
      els.interests.appendChild(btn);
    });

    (I18N.eventTypes || []).forEach(function (it) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cm-planner-chip";
      btn.setAttribute("data-event-type", it.v);
      btn.setAttribute("aria-pressed", "false");
      btn.textContent = it.l;
      btn.addEventListener("click", function () {
        state.eventType = state.eventType === it.v ? "" : it.v;
        syncEventTypeChips();
        refreshWa();
      });
      els.eventTypes.appendChild(btn);
    });

    document.getElementById("cmPlannerPrev").addEventListener("click", function () {
      state.viewM -= 1;
      if (state.viewM < 0) {
        state.viewM = 11;
        state.viewY -= 1;
      }
      renderCal();
    });
    document.getElementById("cmPlannerNext").addEventListener("click", function () {
      state.viewM += 1;
      if (state.viewM > 11) {
        state.viewM = 0;
        state.viewY += 1;
      }
      renderCal();
    });

    root.addEventListener("click", function (e) {
      if (e.target && e.target.getAttribute && e.target.getAttribute("data-cm-planner-close")) {
        close();
      }
    });

    els.submit.addEventListener("click", submitForm);
    [els.name, els.phone, els.email, els.guests].forEach(function (inp) {
      if (!inp) return;
      inp.addEventListener("input", function () {
        if (inp === els.guests) state.guests = (els.guests.value || "").trim();
        refreshWa();
      });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && state.open) {
        e.preventDefault();
        close();
      }
    });
  }

  function syncBudgetChips() {
    els.budgets.querySelectorAll(".cm-planner-chip").forEach(function (btn) {
      var on = btn.getAttribute("data-budget") === state.budget;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function syncInterestChips() {
    els.interests.querySelectorAll(".cm-planner-chip").forEach(function (btn) {
      var v = btn.getAttribute("data-interest");
      var on = !!state.interests[v];
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function pageWantsEvent() {
    var body = document.body;
    if (body && body.getAttribute("data-planner-event") === "1") return true;
    var theme = (body && body.getAttribute("data-carte-theme")) || "";
    if (theme === "evenements") return true;
    if (/evenement|\/events|mariage|wedding|evjf/i.test(location.pathname || "/")) {
      return true;
    }
    return !!state.interests.evenements || !!state.interests.mariage;
  }

  function syncEventTypeChips() {
    if (!els.eventTypes) return;
    els.eventTypes.querySelectorAll(".cm-planner-chip").forEach(function (btn) {
      var on = btn.getAttribute("data-event-type") === state.eventType;
      btn.classList.toggle("on", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function syncEventBlock() {
    if (!els.eventBlock) return;
    var show = pageWantsEvent();
    els.eventBlock.hidden = !show;
    if (!show) state.eventType = "";
    syncEventTypeChips();
  }

  function updateRangeHint() {
    if (!state.start && !state.end) {
      els.rangeHint.textContent = I18N.pickStart;
      return;
    }
    if (state.start && !state.end) {
      els.rangeHint.innerHTML =
        "<strong>" +
        fmtShort(state.start) +
        "</strong> — " +
        I18N.pickEnd;
      return;
    }
    els.rangeHint.innerHTML = I18N.range
      .replace("{a}", "<strong>" + fmtShort(state.start) + "</strong>")
      .replace("{b}", "<strong>" + fmtShort(state.end) + "</strong>");
  }

  function renderCal() {
    els.title.textContent = I18N.months[state.viewM] + " " + state.viewY;
    els.grid.innerHTML = "";
    I18N.dow.forEach(function (d) {
      var cell = document.createElement("div");
      cell.className = "cm-planner-dow";
      cell.textContent = d;
      els.grid.appendChild(cell);
    });

    var first = new Date(state.viewY, state.viewM, 1);
    // Monday-first: JS getDay Sun=0 → shift
    var startPad = (first.getDay() + 6) % 7;
    var daysInMonth = new Date(state.viewY, state.viewM + 1, 0).getDate();
    var today = todayStart();

    for (var i = 0; i < startPad; i++) {
      var empty = document.createElement("button");
      empty.type = "button";
      empty.className = "cm-planner-day out";
      empty.disabled = true;
      empty.setAttribute("aria-hidden", "true");
      els.grid.appendChild(empty);
    }

    for (var day = 1; day <= daysInMonth; day++) {
      var d = new Date(state.viewY, state.viewM, day);
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cm-planner-day";
      btn.textContent = String(day);
      btn.setAttribute("data-ymd", ymd(d));
      if (d < today) {
        btn.disabled = true;
        btn.classList.add("out");
      } else {
        btn.addEventListener("click", onDayClick);
      }
      if (state.start && ymd(d) === ymd(state.start)) btn.classList.add("start");
      if (state.end && ymd(d) === ymd(state.end)) btn.classList.add("end");
      if (state.start && state.end && d > state.start && d < state.end) {
        btn.classList.add("in-range");
      }
      if (state.start && state.end && ymd(d) === ymd(state.start) && ymd(d) !== ymd(state.end)) {
        btn.classList.add("in-range");
      }
      if (state.start && state.end && ymd(d) === ymd(state.end) && ymd(d) !== ymd(state.start)) {
        btn.classList.add("in-range");
      }
      els.grid.appendChild(btn);
    }
    updateRangeHint();
  }

  function onDayClick(e) {
    var s = e.currentTarget.getAttribute("data-ymd");
    var d = parseYmd(s);
    if (!d) return;

    if (!state.start || (state.start && state.end)) {
      state.start = d;
      state.end = null;
    } else if (d < state.start) {
      state.start = d;
      state.end = null;
    } else if (ymd(d) === ymd(state.start)) {
      state.start = null;
      state.end = null;
    } else {
      state.end = d;
    }
    renderCal();
    refreshWa();
  }

  function selectedInterestCodes() {
    return I18N.interests
      .map(function (it) {
        return it.v;
      })
      .filter(function (v) {
        return state.interests[v];
      });
  }

  function budgetLabel() {
    for (var i = 0; i < I18N.budgets.length; i++) {
      if (I18N.budgets[i].v === state.budget) return I18N.budgets[i].l;
    }
    return isEn ? "not set" : "non précisé";
  }

  function datesLabel() {
    if (state.start && state.end) return fmtShort(state.start) + " → " + fmtShort(state.end);
    if (state.start) return fmtShort(state.start) + " → …";
    return isEn ? "flexible" : "flexibles";
  }

  function expLabel() {
    var codes = selectedInterestCodes();
    if (!codes.length) return isEn ? "open" : "à préciser";
    return codes
      .map(function (c) {
        for (var i = 0; i < I18N.interests.length; i++) {
          if (I18N.interests[i].v === c) return I18N.interests[i].l;
        }
        return c;
      })
      .join(", ");
  }

  function guestsLabel() {
    var g =
      state.guests ||
      (els.guests && (els.guests.value || "").trim()) ||
      "";
    if (!g) return isEn ? "not set" : "non précisé";
    return g;
  }

  function eventLabel() {
    if (!state.eventType) return isEn ? "n/a" : "—";
    for (var i = 0; i < (I18N.eventTypes || []).length; i++) {
      if (I18N.eventTypes[i].v === state.eventType) return I18N.eventTypes[i].l;
    }
    return state.eventType;
  }

  function refreshWa() {
    if (!els.wa) return;
    var lieuBit = state.lieuName
      ? (isEn ? "\nPlace: " : "\nLieu : ") + state.lieuName
      : "";
    var msg = I18N.waMsg
      .replace("{dates}", datesLabel())
      .replace("{guests}", guestsLabel())
      .replace("{budget}", budgetLabel())
      .replace("{event}", eventLabel())
      .replace("{exp}", expLabel())
      .replace("{name}", (els.name.value || "").trim() || "—")
      .replace("{phone}", (els.phone.value || "").trim() || "—")
      .replace("{email}", (els.email.value || "").trim() || "—");
    if (lieuBit && msg.indexOf(state.lieuName) === -1) {
      msg = msg.replace(
        isEn ? "Coins Marocain.\n" : "Coins Marocain.\n",
        (isEn ? "Coins Marocain." : "Coins Marocain.") + lieuBit + "\n"
      );
    }
    els.wa.href = WA_BASE + encodeURIComponent(msg);
  }

  function setStatus(msg, kind) {
    els.status.textContent = msg || "";
    els.status.className = "cm-planner-status" + (kind ? " " + kind : "");
  }

  function trapFocus(e) {
    if (!state.open || e.key !== "Tab") return;
    var focusables = els.panel.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    if (!focusables.length) return;
    var first = focusables[0];
    var last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  function coerceDate(v) {
    if (!v) return null;
    if (v instanceof Date && !isNaN(v.getTime())) {
      return new Date(v.getFullYear(), v.getMonth(), v.getDate());
    }
    if (typeof v === "string") return parseYmd(v);
    return null;
  }

  function open(opts) {
    opts = opts || {};
    ensureCss();
    buildDom();
    var t = todayStart();
    state.viewY = t.getFullYear();
    state.viewM = t.getMonth();
    state.start = coerceDate(opts.start);
    state.end = coerceDate(opts.end);
    if (state.start) {
      state.viewY = state.start.getFullYear();
      state.viewM = state.start.getMonth();
    }
    state.budget = opts.budget || "500_1500";
    state.guests = opts.guests != null ? String(opts.guests) : "";
    state.eventType = opts.eventType || "";
    state.lieuName = opts.lieuName || "";
    if (els.guests) els.guests.value = state.guests;
    state.interests = {};
    defaultInterestsFromPage().forEach(function (c) {
      state.interests[c] = true;
    });
    if (opts.interests && opts.interests.length) {
      state.interests = {};
      opts.interests.forEach(function (c) {
        state.interests[c] = true;
      });
    }
    if (state.interests.mariage && !state.eventType) state.eventType = "mariage";
    state.lastFocus = document.activeElement;
    state.open = true;
    els.root.hidden = false;
    // force reflow for transition
    void els.root.offsetWidth;
    els.root.classList.add("on");
    document.body.style.overflow = "hidden";
    syncBudgetChips();
    syncInterestChips();
    syncEventBlock();
    renderCal();
    refreshWa();
    setStatus("");
    document.addEventListener("keydown", trapFocus);
    setTimeout(function () {
      if (els.name && opts.focusContact) {
        els.name.focus();
      } else if (els.panel) {
        els.panel.focus();
      }
    }, 50);
  }

  function close() {
    if (!els.root) return;
    state.open = false;
    els.root.classList.remove("on");
    document.body.style.overflow = "";
    document.removeEventListener("keydown", trapFocus);
    setTimeout(function () {
      if (!state.open) els.root.hidden = true;
    }, 280);
    if (state.lastFocus && state.lastFocus.focus) {
      try {
        state.lastFocus.focus();
      } catch (e) {}
    }
  }

  function submitForm() {
    var name = (els.name.value || "").trim();
    var email = (els.email.value || "").trim();
    var phone = (els.phone.value || "").trim();
    if (!name || !email || !phone) {
      setStatus(I18N.errFields, "err");
      return;
    }
    if (!els.consent || !els.consent.checked) {
      setStatus(I18N.errConsent, "err");
      return;
    }

    var guests =
      state.guests || (els.guests && (els.guests.value || "").trim()) || "";
    var payload = {
      request_type: "voyageur",
      name: name,
      email: email,
      phone: phone,
      message:
        (isEn ? "[Planner stay] " : "[Planner séjour] ") +
        (state.lieuName ? "Lieu: " + state.lieuName + " | " : "") +
        "Dates: " +
        datesLabel() +
        " | Personnes: " +
        guestsLabel() +
        " | Budget: " +
        budgetLabel() +
        " | Événement: " +
        eventLabel() +
        " | Exp: " +
        expLabel() +
        " | Page: " +
        (location.pathname || "/"),
      consentement_promo_whatsapp: !!(els.consent && els.consent.checked),
      budget: state.budget || "500_1500",
      interests: selectedInterestCodes(),
    };
    if (guests) payload.taille_groupe = guests;
    if (state.eventType && pageWantsEvent()) payload.event_type = state.eventType;
    if (state.start) payload.date_arrivee = ymd(state.start);
    if (state.end) payload.date_depart = ymd(state.end);

    els.submit.disabled = true;
    setStatus(I18N.sending);

    fetch(SITE_ORIGIN + "/coins/api/contact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (r) {
        return r.json().then(function (j) {
          return { ok: r.ok && j && j.ok, j: j };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          setStatus(I18N.errServer, "err");
          return;
        }
        setStatus(I18N.ok, "ok");
        els.name.value = "";
        els.phone.value = "";
        els.email.value = "";
        refreshWa();
      })
      .catch(function () {
        setStatus(I18N.errNet, "err");
      })
      .finally(function () {
        els.submit.disabled = false;
      });
  }

  window.CoinsPlanner = {
    open: open,
    close: close,
    labels: function () {
      return { short: I18N.ctaShort, long: I18N.ctaLong };
    },
  };
})();
