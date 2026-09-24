/* Thèmes Carte — SEO + filtres (FR / EN). Route gourmande prête sans adresses. */
window.CM_CARTE_THEMES = {
  hebergement: {
    slug_fr: "hebergement",
    slug_en: "stay",
    filter: "hebergement",
    fr: {
      title: "Hébergement à Marrakech — villas & riads en vidéo | Coins Marocain",
      description:
        "Découvrez les hébergements partenaires à Marrakech en vidéo : villas et riads sélectionnés, pins sur la carte, privatisation possible.",
      h1: "Hébergement à Marrakech",
      lead:
        "Villas et riads en vidéo — choisissez avec le regard, puis demandez dates et capacité."
    },
    en: {
      title: "Stay in Marrakech — villas & riads on video | Coins Marocain",
      description:
        "Browse partner stays in Marrakech on video: curated villas and riads, map pins, privatisation on request.",
      h1: "Stay in Marrakech",
      lead:
        "Villas and riads on video — choose by eye, then ask for dates and capacity."
    }
  },
  bien_etre: {
    slug_fr: "bien-etre",
    slug_en: "wellness",
    filter: "bien_etre",
    fr: {
      title: "Route bien-être Marrakech — spas, hammams et massages | Coins Marocain",
      description:
        "Route bien-être à Marrakech : villas événementielles avec salle dédiée et hammams spécialisés — massages, soins, créneaux mixtes ou non-mixtes.",
      h1: "Route bien-être à Marrakech",
      lead:
        "Hammams, massages et villas avec espace bien-être — en vidéo, puis sur devis."
    },
    en: {
      title: "Marrakech wellness trail — spas, hammams & massage | Coins Marocain",
      description:
        "Marrakech wellness trail: event villas with a dedicated wellness room and specialist hammams — massage, treatments, mixed or women/men-only slots.",
      h1: "A wellness trail through Marrakech",
      lead:
        "Hammams, massage and event villas with a wellness room — on video, then on quote."
    }
  },
  route_gourmande: {
    slug_fr: "route-gourmande",
    slug_en: "food",
    filter: "route_gourmande",
    fr: {
      title: "Route gourmande Marrakech — restaurants et tables d'exception | Coins Marocain",
      description:
        "Route gourmande à Marrakech : restaurants et tables d'exception sélectionnés pour leur cadre et leur assiette — carte vidéo Coins Marocain.",
      h1: "Route gourmande à Marrakech",
      lead:
        "Tables et rooftops choisis pour le cadre autant que l’assiette — en vidéo d’abord."
    },
    en: {
      title: "Marrakech food trail — exceptional restaurants & tables | Coins Marocain",
      description:
        "Marrakech food trail: restaurants and tables chosen for setting and plate alike — on the Coins Marocain video map.",
      h1: "A food trail through Marrakech",
      lead:
        "Tables and rooftops chosen for setting and plate alike — video first."
    }
  },
  experiences: {
    slug_fr: "experiences",
    slug_en: "experiences",
    filter: "experiences",
    viator: true,
    fr: {
      title: "Activités et expériences à Marrakech — Agafay, Atlas | Coins Marocain",
      description:
        "Activités et expériences à Marrakech : excursion Agafay, Atlas, Ourika — quad, chameau, randonnée. Sélection via notre partenaire Viator.",
      h1: "Activités et expériences à Marrakech",
      lead:
        "Désert, Atlas, Ourika — des sorties tout inclus, à deux pas de la ville. Vidéo d’abord, réservation en un message."
    },
    en: {
      title: "Activities & experiences in Marrakech — Agafay, Atlas | Coins Marocain",
      description:
        "Activities and day trips from Marrakech: Agafay desert, Atlas, Ourika — ATV, camel rides, hiking. Curated via our Viator partner.",
      h1: "Activities & experiences in Marrakech",
      lead:
        "Desert, Atlas, Ourika — all-inclusive day trips just outside the city. Video first, booking in one message."
    }
  },
  evenements: {
    slug_fr: "evenements",
    slug_en: "events",
    filter: "evenements",
    fr: {
      title: "Événements à Marrakech — lieux en vidéo | Coins Marocain",
      description:
        "Lieux pour événements à Marrakech en vidéo : mariages, célébrations et privatisation — carte Coins Marocain.",
      h1: "Événements à Marrakech",
      lead:
        "Lieux pensés pour célébrer — mariages, galas, groupes. Chaque pin montre l’ambiance en vidéo ; le devis reste humain, sous 48h."
    },
    en: {
      title: "Events in Marrakech — venues on video | Coins Marocain",
      description:
        "Event venues in Marrakech on video: weddings, celebrations and privatisation — Coins Marocain map.",
      h1: "Events in Marrakech",
      lead:
        "Venues made for celebrating — weddings, galas, groups. Each pin shows the atmosphere on video; quotes stay human, within 48 hours."
    }
  }
};

window.CM_CARTE_THEME_SLUGS = {
  hebergement: "hebergement",
  "bien-etre": "bien_etre",
  bien_etre: "bien_etre",
  "route-bien-etre": "bien_etre",
  route_bien_etre: "bien_etre",
  "route-gourmande": "route_gourmande",
  route_gourmande: "route_gourmande",
  "plein-air": "experiences",
  plein_air: "experiences",
  experiences: "experiences",
  evenements: "evenements",
  stay: "hebergement",
  wellness: "bien_etre",
  food: "route_gourmande",
  outdoors: "experiences",
  events: "evenements"
};

/* Filtres secondaires Route bien-être (pastilles combinables). */
window.CM_CARTE_BE_FILTERS = {
  fr: [
    {
      dim: "type_lieu",
      label: "Type de lieu",
      options: [
        { value: "villa_evenementiel", label: "Villa/riad événementiel" },
        { value: "hammam_specialise", label: "Hammam spécialisé" }
      ]
    },
    {
      dim: "services",
      label: "Services",
      options: [
        { value: "massage", label: "Massage" },
        { value: "hammam_traditionnel", label: "Hammam traditionnel" },
        { value: "soin_visage", label: "Soin visage" },
        { value: "henna", label: "Henna" },
        { value: "brushing", label: "Brushing" },
        { value: "soins_beaute", label: "Soins beauté" }
      ]
    },
    {
      dim: "mixte",
      label: "Mixte / non-mixte",
      options: [
        { value: "mixte", label: "Mixte" },
        { value: "creneaux_separes", label: "Créneaux séparés" },
        { value: "non_mixte", label: "Non-mixte" }
      ]
    }
  ],
  en: [
    {
      dim: "type_lieu",
      label: "Venue type",
      options: [
        { value: "villa_evenementiel", label: "Event villa/riad" },
        { value: "hammam_specialise", label: "Specialist hammam" }
      ]
    },
    {
      dim: "services",
      label: "Services",
      options: [
        { value: "massage", label: "Massage" },
        { value: "hammam_traditionnel", label: "Traditional hammam" },
        { value: "soin_visage", label: "Facial" },
        { value: "henna", label: "Henna" },
        { value: "brushing", label: "Blow-dry" },
        { value: "soins_beaute", label: "Beauty care" }
      ]
    },
    {
      dim: "mixte",
      label: "Mixed / women-men",
      options: [
        { value: "mixte", label: "Mixed" },
        { value: "creneaux_separes", label: "Separate slots" },
        { value: "non_mixte", label: "Non-mixed" }
      ]
    }
  ]
};

/* Filtres secondaires Route gourmande (pastilles combinables). */
window.CM_CARTE_RG_FILTERS = {
  fr: [
    {
      dim: "cuisine",
      label: "Type de cuisine",
      options: [
        { value: "marocaine_traditionnelle", label: "Marocaine traditionnelle" },
        { value: "fusion", label: "Fusion" },
        { value: "mediterraneenne", label: "Méditerranéenne" },
        { value: "internationale", label: "Internationale" },
        { value: "street_food", label: "Street food" }
      ]
    },
    {
      dim: "cadre",
      label: "Cadre",
      options: [
        { value: "rooftop", label: "Rooftop" },
        { value: "terrasse_exterieure", label: "Terrasse" },
        { value: "jardin", label: "Jardin" },
        { value: "salle_interieure", label: "Salle intérieure" },
        { value: "salle_privee", label: "Salle privée" }
      ]
    },
    {
      dim: "alcool",
      label: "Alcool",
      options: [
        { value: "licence_complete", label: "Licence complète" },
        { value: "sans_alcool", label: "Sans alcool" },
        { value: "sur_demande", label: "Sur demande" }
      ]
    },
    {
      dim: "animations",
      label: "Animations",
      options: [
        { value: "musique_live", label: "Musique live" },
        { value: "dj", label: "DJ" },
        { value: "danse_orientale", label: "Danse orientale" },
        { value: "lounge", label: "Lounge / calme" },
        { value: "aucune", label: "Aucune" }
      ]
    }
  ],
  en: [
    {
      dim: "cuisine",
      label: "Cuisine",
      options: [
        { value: "marocaine_traditionnelle", label: "Traditional Moroccan" },
        { value: "fusion", label: "Fusion" },
        { value: "mediterraneenne", label: "Mediterranean" },
        { value: "internationale", label: "International" },
        { value: "street_food", label: "Gourmet street food" }
      ]
    },
    {
      dim: "cadre",
      label: "Setting",
      options: [
        { value: "rooftop", label: "Rooftop" },
        { value: "terrasse_exterieure", label: "Terrace" },
        { value: "jardin", label: "Garden" },
        { value: "salle_interieure", label: "Indoor room" },
        { value: "salle_privee", label: "Private room" }
      ]
    },
    {
      dim: "alcool",
      label: "Alcohol",
      options: [
        { value: "licence_complete", label: "Full licence" },
        { value: "sans_alcool", label: "Alcohol-free" },
        { value: "sur_demande", label: "On request" }
      ]
    },
    {
      dim: "animations",
      label: "Entertainment",
      options: [
        { value: "musique_live", label: "Live music" },
        { value: "dj", label: "DJ" },
        { value: "danse_orientale", label: "Oriental dance" },
        { value: "lounge", label: "Lounge / calm" },
        { value: "aucune", label: "None" }
      ]
    }
  ]
};
