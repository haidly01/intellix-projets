# Intellix — Catalogue Vente (V2.1)

Catalogue Coins Marocain / Intellix : Digital Doorway (dh) et Agence Doorway ($CAD).
Les produits et modèles **Call Center** sont archivés (historique des devis conservé).

## Modèles

- Starter Intellix → `INTELLIX_BASE`
- Croissance IA → base + agent + conception neuf + bundle M (ajustable)
- Présence Digitale Complète → + site Standard + maintenance + SEO Essentiel

## Entité / devise

- Client local → Digital Doorway (dh)
- Client international → Agence Doorway ($CAD)
- Forçage manuel possible tant que le devis n’est pas envoyé

## Gel des prix

À l’envoi (`sent` / `sale`) : prix, clauses et URL vidéo sont figés.
Un changement de catalogue ne recalcule pas un devis déjà envoyé.

## Vidéo secteur

Champ **Secteur prospect** → table `ix.category.video` (Ventes → Configuration → Vidéos devis).
Coller le lien HeyGen / Vimeo par catégorie. Les devis déjà envoyés gardent leur lien.

## Taxes (catalogue HT)

- Digital Doorway : TVA Maroc **20 %** (taxe vente société)
- Agence Doorway : **TPS 5 % + TVQ 9,975 %** (groupe vente société)
- Mode devis : taxes ON par défaut (`with_tax`). HT possible via « Hors taxes ».

## Clauses

Version de démarrage, sans bandeau avocat. Prix HT + taxes en sus, énoncés dans les clauses.
