/**
 * Villas séjour + checkout Stripe — /forfaits
 * Aucune clé secrète Stripe ici.
 */
(function () {
  "use strict";

  var API_BASE = (window.COINS_API_BASE || "").replace(/\/$/, "");
  var state = {
    proprietes: [],
    crossSell: [],
    madPerCad: 7.2,
    displayNote: "",
    selected: null,
    displayCurrency: "MAD",
    lightbox: { urls: [], index: 0 },
  };

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  function el(tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }
  function ficheSlug(p) {
    var known = [
      "la-casa-ysabella",
      "dar-sacada",
      "casa-alma",
      "villa-nafsi",
      "villa-michelle",
      "riad-ines",
    ];
    if (p && p.slug && known.indexOf(p.slug) !== -1) return p.slug;
    var map = {
      "La Casa Ysabella": "la-casa-ysabella",
      "Dar Sacada": "dar-sacada",
      "Casa Alma": "casa-alma",
      "Villa Nafsi": "villa-nafsi",
      "Villa Michelle": "villa-michelle",
      "Riad Ines": "riad-ines",
    };
    return map[(p && p.nom) || ""] || "";
  }
  function fichePath(p) {
    var s = ficheSlug(p);
    if (s === "la-casa-ysabella") return "/lieux/riad-medina-marrakech-la-casa-ysabella";
    return s ? "/lieux/" + s : "";
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
  function nightsBetween(a, b) {
    var d0 = new Date(a + "T12:00:00");
    var d1 = new Date(b + "T12:00:00");
    return Math.round((d1 - d0) / 86400000);
  }
  function inDispo(dispos, start, endExclusive) {
    if (!dispos || !dispos.length) return false;
    var cur = new Date(start + "T12:00:00");
    var last = new Date(endExclusive + "T12:00:00");
    last.setDate(last.getDate() - 1);
    while (cur <= last) {
      var ymd = cur.toISOString().slice(0, 10);
      var ok = dispos.some(function (d) {
        return ymd >= d.date_debut && ymd <= d.date_fin;
      });
      if (!ok) return false;
      cur.setDate(cur.getDate() + 1);
    }
    return true;
  }
  function formatDispoBadge(dispos) {
    if (!dispos || !dispos.length) {
      return { text: "Contactez-nous pour vérifier les disponibilités", empty: true };
    }
    var d = dispos[0];
    return {
      text: "Disponible · dès " + d.date_debut + (dispos.length > 1 ? " (+)" : ""),
      empty: false,
    };
  }
  function publicDesc(text) {
    var t = String(text || "");
    t = t.split(/\bSource Airbnb\b/i)[0];
    t = t.split(/À compléter\s*:/i)[0];
    t = t.replace(/\bannonce\s*#?\s*\d+/gi, "");
    t = t.replace(/https?:\/\/\S*airbnb\S*/gi, "");
    return t.replace(/\s+/g, " ").trim().replace(/^[·\-\s]+|[·\-\s]+$/g, "");
  }
  function cadToDisplay(cad) {
    var rate = state.madPerCad || 7.2;
    if (state.displayCurrency === "EUR") {
      // approx CAD→EUR via MAD pivot (indicatif)
      var mad = cad * rate;
      return { value: mad / 10.8, symbol: "€", label: "EUR" };
    }
    return { value: cad * rate, symbol: "DH", label: "MAD" };
  }
  function money(cad) {
    var d = cadToDisplay(cad);
    return (
      d.symbol +
      " " +
      d.value.toLocaleString("fr-FR", { maximumFractionDigits: 0 })
    );
  }

  function setStatus(msg) {
    var box = $("#ffVillasStatus");
    var grid = $("#ffVillasGrid");
    if (!box) return;
    box.hidden = !msg;
    box.textContent = msg || "";
    if (grid) grid.hidden = !!msg;
  }

  function photoThumb(ph) {
    return (ph && (ph.url_thumb || ph.url)) || "";
  }
  function photoCard(ph) {
    return (ph && (ph.url || ph.url_thumb)) || "";
  }
  function photoFull(ph) {
    return (ph && (ph.url_full || ph.url || ph.url_thumb)) || "";
  }
  function openLightbox(photos, index) {
    var urls = (photos || [])
      .map(photoFull)
      .filter(Boolean);
    if (!urls.length) return;
    state.lightbox.urls = urls;
    state.lightbox.index = Math.max(0, Math.min(index || 0, urls.length - 1));
    renderLightbox();
    var box = $("#ffLightbox");
    if (!box) return;
    box.hidden = false;
    box.classList.add("is-open");
    box.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    if (!box.dataset.wheelBound) {
      box.dataset.wheelBound = "1";
      box.addEventListener(
        "wheel",
        function (ev) {
          ev.preventDefault();
          if (state.lightbox.urls.length < 2) return;
          lightboxStep(ev.deltaY > 0 ? 1 : -1);
        },
        { passive: false }
      );
    }
  }
  function closeLightbox() {
    var box = $("#ffLightbox");
    if (!box) return;
    box.classList.remove("is-open");
    box.setAttribute("aria-hidden", "true");
    box.hidden = true;
    state.lightbox.urls = [];
    if (!$("#ffVillaModal") || !$("#ffVillaModal").classList.contains("is-open")) {
      document.body.style.overflow = "";
    }
  }
  function renderLightbox() {
    var urls = state.lightbox.urls;
    var i = state.lightbox.index;
    var img = $("#ffLbImg");
    var count = $("#ffLbCount");
    var prev = $("#ffLbPrev");
    var next = $("#ffLbNext");
    if (!img || !urls.length) return;
    img.src = urls[i];
    img.alt = "Photo " + (i + 1);
    if (count) count.textContent = i + 1 + " / " + urls.length;
    if (prev) prev.hidden = urls.length < 2;
    if (next) next.hidden = urls.length < 2;
  }
  function lightboxStep(delta) {
    var urls = state.lightbox.urls;
    if (urls.length < 2) return;
    state.lightbox.index = (state.lightbox.index + delta + urls.length) % urls.length;
    renderLightbox();
  }

  function renderCards() {
    var grid = $("#ffVillasGrid");
    if (!grid) return;
    grid.innerHTML = "";
    if (!state.proprietes.length) {
      setStatus("Informations bientôt disponibles — revenez un peu plus tard.");
      return;
    }
    setStatus("");
    state.proprietes.forEach(function (p) {
      var badge = formatDispoBadge(p.disponibilites);
      var card = el("article", "ff-villa-card");
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      var media = el("div", "ff-villa-media");
      if (p.photos && p.photos[0]) {
        var img = document.createElement("img");
        img.src = photoCard(p.photos[0]);
        img.alt = p.nom || "";
        img.loading = "lazy";
        img.decoding = "async";
        media.appendChild(img);
      }
      var body = el("div", "ff-villa-body");
      body.appendChild(el("span", "ff-badge-dispo" + (badge.empty ? " is-empty" : ""), esc(badge.text)));
      body.appendChild(el("h3", "", esc(p.nom)));
      body.appendChild(
        el(
          "p",
          "ff-villa-meta",
          esc((p.ville || "") + (p.capacite ? " · jusqu’à " + p.capacite + " pers." : ""))
        )
      );
      var desc = publicDesc(p.description);
      body.appendChild(
        el(
          "p",
          "ff-villa-desc",
          esc(desc.slice(0, 160)) + (desc.length > 160 ? "…" : "")
        )
      );
      if (p.reservable && p.prix_nuit_cad > 0) {
        body.appendChild(
          el("p", "ff-villa-meta", "À partir de " + esc(money(p.prix_nuit_cad)) + " / nuit")
        );
      }
      card.appendChild(media);
      card.appendChild(body);
      card.addEventListener("click", function () {
        var s = fichePath(p);
        if (s) {
          window.location.href = s;
          return;
        }
        openModal(p);
      });
      card.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          var s = fichePath(p);
          if (s) {
            window.location.href = s;
            return;
          }
          openModal(p);
        }
      });
      grid.appendChild(card);
    });
  }

  function openModal(p) {
    state.selected = p;
    var overlay = $("#ffVillaModal");
    if (!overlay) return;
    $("#ffModalTitle").textContent = p.nom;
    var prevFiche = $("#ffModalFicheLink");
    if (prevFiche) prevFiche.remove();
    if (ficheSlug(p)) {
      var ficheA = document.createElement("a");
      ficheA.id = "ffModalFicheLink";
      ficheA.href = fichePath(p);
      ficheA.textContent = "Voir la fiche complète →";
      ficheA.style.display = "inline-block";
      ficheA.style.margin = "0 0 10px";
      $("#ffModalTitle").insertAdjacentElement("afterend", ficheA);
    }
    $("#ffModalMeta").textContent =
      (p.ville || "") + (p.capacite ? " · " + p.capacite + " personnes" : "");
    $("#ffModalDesc").textContent = publicDesc(p.description);
    var gal = $("#ffModalGallery");
    gal.innerHTML = "";
    (p.photos || []).forEach(function (ph, idx) {
      var img = document.createElement("img");
      img.src = photoThumb(ph);
      img.alt = ph.legende || p.nom;
      img.loading = "lazy";
      img.decoding = "async";
      img.title = "Agrandir";
      img.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openLightbox(p.photos, idx);
      });
      gal.appendChild(img);
    });

    var badge = formatDispoBadge(p.disponibilites);
    var emptyNote = $("#ffModalEmptyDispo");
    emptyNote.hidden = !badge.empty;
    emptyNote.textContent = badge.text;

    var form = $("#ffBookForm");
    form.hidden = badge.empty && !p.reservable;
    $("#ffClientBlock").hidden = !p.reservable;
    $("#ffXsell").hidden = !p.reservable;
    $("#ffTotalBox").hidden = !p.reservable;
    $("#ffBtnReserve").hidden = !p.reservable;
    $("#ffBtnDevis").hidden = !!p.reservable;

    var din = $("#ffDateIn");
    var dout = $("#ffDateOut");
    var voy = $("#ffVoyageurs");
    din.value = "";
    dout.value = "";
    if (p.disponibilites && p.disponibilites[0]) {
      din.min = p.disponibilites[0].date_debut;
      dout.min = p.disponibilites[0].date_debut;
    }
    if (voy) {
      voy.value = "2";
      voy.min = "1";
      voy.max = String(p.capacite || 30);
    }

    renderRoomSelect(p);
    renderOffers(p);
    renderXsell();
    updateTotal();
    overlay.classList.add("is-open");
    overlay.setAttribute("aria-hidden", "false");
  }

  function moneyCad(cad) {
    var disp = cadToDisplay(cad || 0);
    return (
      disp.symbol +
      " " +
      disp.value.toLocaleString("fr-FR", { maximumFractionDigits: 0 })
    );
  }

  function renderRoomSelect(p) {
    var wrap = $("#ffRoomWrap");
    var sel = $("#ffRoom");
    if (!wrap || !sel) return;
    var rooms = (p && p.rooms) || [];
    sel.innerHTML = "";
    if (!rooms.length) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    rooms.forEach(function (r) {
      var opt = document.createElement("option");
      opt.value = String(r.id);
      opt.textContent =
        r.nom + (r.sleeps ? " (" + r.sleeps + " couchages)" : "");
      sel.appendChild(opt);
    });
    applyRoomCapacityCap();
  }

  function selectedRoom() {
    var p = state.selected;
    if (!p || !(p.rooms || []).length) return null;
    var sel = $("#ffRoom");
    if (!sel || !sel.value) return p.rooms[0];
    var id = parseInt(sel.value, 10);
    for (var i = 0; i < p.rooms.length; i++) {
      if (p.rooms[i].id === id) return p.rooms[i];
    }
    return p.rooms[0];
  }

  function applyRoomCapacityCap() {
    var voy = $("#ffVoyageurs");
    var p = state.selected;
    if (!voy || !p) return;
    var room = selectedRoom();
    var max = room && room.sleeps ? room.sleeps : p.capacite || 30;
    voy.max = String(max);
    if (parseInt(voy.value, 10) > max) voy.value = String(max);
  }

  function renderOffers(p) {
    var box = $("#ffOffers");
    if (!box) return;
    var meals = (p && p.meals) || {};
    var showDay = !!(p && p.daypass_piscine);
    var showB = !!(meals.breakfast && meals.breakfast.available);
    var showL = !!(meals.lunch && meals.lunch.available);
    var showD = !!(meals.dinner && meals.dinner.available);
    var any = showDay || showB || showL || showD;
    box.hidden = !any || !p.reservable;

    function setOffer(labelId, cbId, textId, show, label, priceCad) {
      var lab = $("#" + labelId);
      var cb = $("#" + cbId);
      var txt = $("#" + textId);
      if (!lab || !cb || !txt) return;
      lab.hidden = !show;
      cb.checked = false;
      cb.dataset.priceCad = String(priceCad || 0);
      txt.textContent =
        label +
        (priceCad > 0 ? " — " + moneyCad(priceCad) + " / pers." : "");
    }

    setOffer(
      "ffDaypassLabel",
      "ffDaypass",
      "ffDaypassText",
      showDay,
      "Daypass piscine",
      p.daypass_price_cad || 0
    );
    setOffer(
      "ffBreakfastLabel",
      "ffBreakfast",
      "ffBreakfastText",
      showB,
      "Petit-déjeuner",
      (meals.breakfast && meals.breakfast.price_cad) || 0
    );
    setOffer(
      "ffLunchLabel",
      "ffLunch",
      "ffLunchText",
      showL,
      "Déjeuner",
      (meals.lunch && meals.lunch.price_cad) || 0
    );
    setOffer(
      "ffDinnerLabel",
      "ffDinner",
      "ffDinnerText",
      showD,
      "Dîner",
      (meals.dinner && meals.dinner.price_cad) || 0
    );
    var al = $("#ffAllergies");
    if (al) al.value = "";
  }

  function offerExtrasCad() {
    var guests = guestsCount();
    var total = 0;
    [
      ["ffDaypass", "ffDaypassLabel"],
      ["ffBreakfast", "ffBreakfastLabel"],
      ["ffLunch", "ffLunchLabel"],
      ["ffDinner", "ffDinnerLabel"],
    ].forEach(function (pair) {
      var cb = $("#" + pair[0]);
      var lab = $("#" + pair[1]);
      if (!cb || !lab || lab.hidden || !cb.checked) return;
      total += (parseFloat(cb.dataset.priceCad || "0") || 0) * guests;
    });
    return total;
  }

  function closeModal() {
    var overlay = $("#ffVillaModal");
    if (!overlay) return;
    overlay.classList.remove("is-open");
    overlay.setAttribute("aria-hidden", "true");
    state.selected = null;
    if (!$("#ffLightbox") || !$("#ffLightbox").classList.contains("is-open")) {
      document.body.style.overflow = "";
    }
  }

  function guestsCount() {
    var n = $("#ffVoyageurs");
    var v = n ? parseInt(n.value, 10) : 2;
    if (!v || v < 1) v = 1;
    var p = state.selected;
    var room = selectedRoom();
    var max = room && room.sleeps ? room.sleeps : p && p.capacite ? p.capacite : 30;
    if (v > max) v = max;
    if (n && parseInt(n.value, 10) !== v) n.value = String(v);
    return v;
  }
  function packQty(pack) {
    return (pack.unit || "person") === "group" ? 1 : guestsCount();
  }
  function packLineCad(pack) {
    return (parseFloat(pack.price_cad) || 0) * packQty(pack);
  }

  function renderXsell() {
    var box = $("#ffXsellList");
    if (!box) return;
    var checked = {};
    document.querySelectorAll("#ffXsellList input[type=checkbox]:checked").forEach(function (cb) {
      checked[cb.value] = true;
    });
    box.innerHTML = "";
    var guests = guestsCount();
    var groups = {};
    var order = [];
    state.crossSell.forEach(function (pack) {
      var g = pack.group || "forfait";
      if (!groups[g]) {
        groups[g] = [];
        order.push(g);
      }
      groups[g].push(pack);
    });
    order.forEach(function (g) {
      var label =
        (groups[g][0] && groups[g][0].group_label) ||
        (g === "activite"
          ? "Activités & excursions"
          : g === "bienetre"
            ? "Massage & soins (Zen)"
            : "Forfaits piscine");
      box.appendChild(el("p", "ff-xsell-group", esc(label)));
      groups[g].forEach(function (pack) {
        var row = el("label", "ff-xsell-item");
        var cb = document.createElement("input");
        cb.type = "checkbox";
        cb.value = pack.code;
        cb.dataset.priceCad = String(pack.price_cad);
        cb.dataset.unit = pack.unit || "person";
        if (checked[pack.code]) cb.checked = true;
        cb.addEventListener("change", updateTotal);
        var text = el("div", "");
        text.appendChild(el("strong", "", esc(pack.name)));
        text.appendChild(el("p", "ff-villa-meta", esc(pack.description)));
        var unit = pack.unit || "person";
        var unitPrice = money(pack.price_cad);
        var line = packLineCad(pack);
        var priceHtml =
          unit === "group"
            ? esc(unitPrice) + " <span class=\"ff-xs-unit\">/ groupe</span>"
            : esc(unitPrice) +
              " <span class=\"ff-xs-unit\">/ pers.</span>" +
              (guests > 1
                ? "<br><span class=\"ff-xs-line\">× " +
                  guests +
                  " = " +
                  esc(money(line)) +
                  "</span>"
                : "");
        var price = el("div", "ff-xs-price", priceHtml);
        row.appendChild(cb);
        row.appendChild(text);
        row.appendChild(price);
        box.appendChild(row);
      });
    });
  }

  function selectedCrossSell() {
    var guests = guestsCount();
    var out = [];
    document.querySelectorAll("#ffXsellList input[type=checkbox]:checked").forEach(function (cb) {
      var unit = cb.dataset.unit || "person";
      out.push({
        code: cb.value,
        qty: unit === "group" ? 1 : guests,
      });
    });
    return out;
  }

  function updateTotal() {
    var p = state.selected;
    var box = $("#ffTotalBox");
    if (!p || !box) return;
    var din = $("#ffDateIn").value;
    var dout = $("#ffDateOut").value;
    var n = din && dout ? nightsBetween(din, dout) : 0;
    var villa = n > 0 ? n * (p.prix_nuit_cad || 0) : 0;
    var frais = villa * ((p.frais_service_pct || 0) / 100);
    var guests = guestsCount();
    var xsell = 0;
    document.querySelectorAll("#ffXsellList input[type=checkbox]:checked").forEach(function (cb) {
      var unit = cb.dataset.unit || "person";
      var unitPrice = parseFloat(cb.dataset.priceCad || "0");
      xsell += unit === "group" ? unitPrice : unitPrice * guests;
    });
    var offers = offerExtrasCad();
    var total = villa + frais + xsell + offers;
    var disp = cadToDisplay(total);
    $("#ffTotalCad").textContent =
      disp.symbol +
      " " +
      disp.value.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
    if (state.displayCurrency === "EUR") {
      var mad = total * (state.madPerCad || 7.2);
      $("#ffTotalDisp").textContent =
        "≈ DH " + mad.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
    } else {
      var eur = (total * (state.madPerCad || 7.2)) / 10.8;
      $("#ffTotalDisp").textContent =
        "≈ € " + eur.toLocaleString("fr-FR", { maximumFractionDigits: 0 });
    }
    var hint =
      state.displayNote ||
      "Paiement en ligne (cartes internationales) ou sur place (espèces / carte).";
    if (guests > 0) {
      hint =
        guests +
        " voyageur" +
        (guests > 1 ? "s" : "") +
        " — forfaits & activités au prix / personne. " +
        hint;
    }
    $("#ffTotalHint").textContent = hint;
    var err = $("#ffBookErr");
    if (din && dout && n < 1) err.textContent = "Choisissez au moins une nuit.";
    else if (din && dout && !inDispo(p.disponibilites, din, dout))
      err.textContent = "Ces dates ne sont pas entièrement disponibles.";
    else {
      var room = selectedRoom();
      var max = room && room.sleeps ? room.sleeps : p.capacite;
      if (max && guests > max)
        err.textContent =
          "Capacité max : " +
          max +
          " personnes" +
          (room ? " pour « " + room.nom + " »" : "") +
          ".";
      else err.textContent = "";
    }
  }

  async function doCheckout(e) {
    e.preventDefault();
    var p = state.selected;
    if (!p || !p.reservable) return;
    var din = $("#ffDateIn").value;
    var dout = $("#ffDateOut").value;
    var nom = $("#ffClientNom").value.trim();
    var email = $("#ffClientEmail").value.trim();
    var tel = $("#ffClientTel").value.trim();
    var err = $("#ffBookErr");
    err.textContent = "";
    if (!din || !dout || nightsBetween(din, dout) < 1) {
      err.textContent = "Dates invalides.";
      return;
    }
    if (!inDispo(p.disponibilites, din, dout)) {
      err.textContent = "Créneau indisponible.";
      return;
    }
    if (!nom || !email) {
      err.textContent = "Nom et email requis.";
      return;
    }
    var guests = guestsCount();
    var room = selectedRoom();
    var max = room && room.sleeps ? room.sleeps : p.capacite;
    if (max && guests > max) {
      err.textContent =
        "Capacité max : " +
        max +
        " personnes" +
        (room ? " pour « " + room.nom + " »" : "") +
        ".";
      return;
    }
    var btn = $("#ffBtnReserve");
    btn.disabled = true;
    btn.textContent = "Redirection…";
    try {
      function offerChecked(cbId, labelId) {
        var cb = $("#" + cbId);
        var lab = $("#" + labelId);
        return !!(cb && lab && !lab.hidden && cb.checked);
      }
      var payload = {
        propriete_id: p.id,
        date_debut: din,
        date_fin: dout,
        voyageurs: guests,
        client_nom: nom,
        client_email: email,
        client_telephone: tel,
        cross_sell: selectedCrossSell(),
        daypass_piscine: offerChecked("ffDaypass", "ffDaypassLabel"),
        meal_breakfast: offerChecked("ffBreakfast", "ffBreakfastLabel"),
        meal_lunch: offerChecked("ffLunch", "ffLunchLabel"),
        meal_dinner: offerChecked("ffDinner", "ffDinnerLabel"),
        allergies: ($("#ffAllergies") && $("#ffAllergies").value.trim()) || "",
      };
      if (room) payload.room_id = room.id;
      var res = await fetch(API_BASE + "/api/coins-marocain/reservations/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      var data = await res.json();
      if (!data.ok || !data.url) {
        var msg =
          data.error === "unavailable"
            ? "Ce créneau vient d’être pris — choisissez d’autres dates."
            : data.error === "daypass_full"
              ? "Daypass complet pour cette date."
              : data.error === "too_many_guests"
                ? data.detail || "Trop de voyageurs pour cette chambre."
                : "Impossible de démarrer le paiement (" + (data.error || res.status) + ").";
        err.textContent = msg;
        btn.disabled = false;
        btn.textContent = "Réserver et payer";
        return;
      }
      window.location.href = data.url;
    } catch (ex) {
      err.textContent = "Erreur réseau — réessayez.";
      btn.disabled = false;
      btn.textContent = "Réserver et payer";
    }
  }

  async function load() {
    var url = API_BASE + "/api/coins-marocain/proprietes.json";
    try {
      var res = await fetch(url, { credentials: "omit" });
      if (!res.ok) throw new Error("http " + res.status);
      var data = await res.json();
      state.proprietes = data.proprietes || [];
      state.crossSell = data.cross_sell || [];
      state.madPerCad = data.mad_per_cad || 7.2;
      state.displayNote = data.display_note || "";
      renderCards();
    } catch (e) {
      setStatus("Informations bientôt disponibles — le catalogue villas se recharge sous peu.");
    }
  }

  function bind() {
    var overlay = $("#ffVillaModal");
    if (overlay) {
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) closeModal();
      });
    }
    var closeBtn = $("#ffModalClose");
    if (closeBtn) closeBtn.addEventListener("click", closeModal);

    var lb = $("#ffLightbox");
    if (lb) {
      lb.addEventListener("click", function (e) {
        if (e.target === lb) closeLightbox();
      });
    }
    var lbClose = $("#ffLbClose");
    if (lbClose) lbClose.addEventListener("click", closeLightbox);
    var lbPrev = $("#ffLbPrev");
    if (lbPrev) lbPrev.addEventListener("click", function (e) {
      e.stopPropagation();
      lightboxStep(-1);
    });
    var lbNext = $("#ffLbNext");
    if (lbNext) lbNext.addEventListener("click", function (e) {
      e.stopPropagation();
      lightboxStep(1);
    });
    document.addEventListener("keydown", function (e) {
      if (!$("#ffLightbox") || !$("#ffLightbox").classList.contains("is-open")) return;
      if (e.key === "Escape") closeLightbox();
      if (e.key === "ArrowLeft") lightboxStep(-1);
      if (e.key === "ArrowRight") lightboxStep(1);
    });

    ["ffDateIn", "ffDateOut", "ffDisplayCurrency", "ffVoyageurs", "ffRoom"].forEach(function (id) {
      var n = $("#" + id);
      if (!n) return;
      n.addEventListener("change", function () {
        if (id === "ffDisplayCurrency") state.displayCurrency = n.value;
        if (id === "ffRoom") applyRoomCapacityCap();
        if (id === "ffVoyageurs" || id === "ffRoom") {
          guestsCount();
          renderXsell();
        }
        updateTotal();
        if (id !== "ffVoyageurs" && id !== "ffRoom") {
          renderXsell();
          updateTotal();
        }
      });
      if (id === "ffVoyageurs") {
        n.addEventListener("input", function () {
          guestsCount();
          renderXsell();
          updateTotal();
        });
      }
    });
    ["ffDaypass", "ffBreakfast", "ffLunch", "ffDinner"].forEach(function (id) {
      var n = $("#" + id);
      if (!n) return;
      n.addEventListener("change", updateTotal);
    });
    var form = $("#ffBookForm");
    if (form) form.addEventListener("submit", doCheckout);
    var devis = $("#ffBtnDevis");
    if (devis) {
      devis.addEventListener("click", function () {
        var p = state.selected;
        var q = encodeURIComponent(
          "Bonjour Yasmine, je souhaite un devis pour " +
            (p ? p.nom : "une villa") +
            " à Marrakech. Dates : "
        );
        window.open("https://wa.me/212660159177?text=" + q, "_blank", "noopener");
      });
    }
    var params = new URLSearchParams(window.location.search);
    if (params.get("booking") === "success") {
      var note = $("#ffBookingFlash");
      if (note) {
        note.hidden = false;
        note.textContent = "Paiement reçu — vous allez recevoir un email de confirmation.";
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    bind();
    load();
  });
})();
