# Coins Marocain — Airbnb iCal + fiche propriété (DEV)

## Décision modèle
`coins.property` existait déjà (Biens). **Étendu** plutôt que créer `coins.propriete` en doublon.

Mapping brief → existant :
| Brief | Implémenté |
|-------|------------|
| `coins.propriete` | `coins.property` (étendu) |
| `type_propriete` | `property_type` (déjà là) |
| `partner_id` | `owner_id` (déjà là) |
| `capacite` | `capacity` |
| `adresse` | `street` |
| `description` | nouveau champ `description` (Html) |
| enfants | `coins.property.photo` / `.disponibilite` / `.blocage` |

Aucun modèle hors `coins_marocain` modifié. `reservation_id` sur blocage pointe vers `coins.reservation` existant (Many2one sortant uniquement).

## Fichiers
- `models/coins_property.py` — champs Airbnb + `_recalculer_disponibilites` + `est_disponible`
- `models/coins_property_photo.py` (nouveau)
- `models/coins_property_disponibilite.py` (nouveau)
- `models/coins_property_blocage.py` (nouveau)
- `models/coins_property_airbnb_sync.py` (nouveau) — fetch/parse iCal + cron
- `data/coins_airbnb_ical_cron.xml` — cron 3 h
- `views/coins_property_views.xml` — fiche + calendrier dispos + audit blocages
- `views/coins_menus.xml` — Biens → Fiches / Disponibilités / Blocages
- `security/ir.model.access.csv` — ACL nouveaux modèles
- `controllers/main.py` — route `POST /coins_marocain/airbnb_ical/sync`
- `__manifest__.py` — `19.0.1.17.0` + `external_dependencies: icalendar`

## DEV (187.124.50.69)
- Module upgradé : **19.0.1.17.0**
- `icalendar` 7.2.0 installé
- Pilote : **Riad Pilote Médina** (id=2)
- Cron log : `fetched=2 created=2` puis `updated=2 errors=0`
- Preuve visuelle : `proof_airbnb_ical_dev.jpg`
