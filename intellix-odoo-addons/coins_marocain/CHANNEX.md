# Channex — environnement **PRODUCTION**

**Marqueur :** l’intégration Odoo `coins_marocain` / Module Hébergement (`intellix_riad`)
parle à **Channex production**, pas à staging.

| | |
|---|---|
| Point d’entrée | `https://app.channex.io/api/v1` |
| Confirmé par | Evan Davies (CEO Channex) après souscription |
| Ancien staging | `https://staging.channex.io/api/v1` — **conservé en repli**, pas supprimé |
| Ancien UUID staging | `052b3e3b-4cc8-45de-a661-a7561a94d06b` (« Test Property - IntelliX ») — **ne pas réutiliser** |
| UUID production (fiche test) | `7b7a4ac1-3f97-47a9-8110-ae182c70caf0` |

## Clé API

La clé se **génère dans le tableau de bord** production
(`app.channex.io` → Organisation → API Keys / Developer), ce n’est pas une clé
envoyée par Channex.

Stockage uniquement :

```
# /etc/odoo-doorway.env   (chmod 640 root:odoo, jamais commité)
CHANNEX_API_KEY=…
# optionnel, sinon l’ICP / le défaut production s’applique
CHANNEX_BASE_URL=https://app.channex.io/api/v1
CHANNEX_ENVIRONMENT=production
```

Le service Odoo lit `CHANNEX_API_KEY` **avant** `ir.config_parameter`.
Le wizard « Connexion Channex » refuse d’écrire la clé en base.

Après modification de l’env : `systemctl restart odoo-server`.

## Repli staging (si la prod n’est pas stable)

1. Wizard Channex → **Repli staging**, ou
2. ICP `coins.channex.environment=staging` (garde `coins.channex.staging_url`).

Ne pas effacer la config staging tant que la production n’est pas confirmée.

## Mapping

Les chambres / tarifs **réels** (Ysabella, Asrari, etc.) ne se connectent à
la production qu’après les 3 tests de validation sur une fiche test.

Full sync certif : exactement **2 POST** (`/availability` + `/restrictions`),
500 jours, Twin + Double, 4 plans (`twin_bar`, `twin_bb`, `double_bar`, `double_bb`).

## Tests production — revalidés le 2026-09-09

Fiche test uniquement (Odoo `#26`). Aucun riad réel mappé.

1. Résa 1 nuit (`CM/2026/0006`, 2026-10-19) → dispo 0 ce jour-là, voisin inchangé.
   task_id `59105e6e-0e8f-44a3-82d9-3f04b9121060`
2. Décalage +1 semaine (2026-10-26) → ancienne date rouverte, nouvelle fermée.
   task_ids `6bee390e-…` / `834f902b-…`
3. Full Sync → 2 POST : dispo `0c40afc8-…` + restrictions `a9b80bc1-…`

Détail : `notes/channex-production-20260909/STATUS.md`.
