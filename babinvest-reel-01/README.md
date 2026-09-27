# BabInvest — Reel 01 « 7 quartiers de Marrakech classés par rendement »

Autrice : Karine Barmaki

## Version livrée : illustrations stylisées

Les visuels de maisonrecherchee.fr n'étaient pas accessibles depuis l'environnement de rendu.
La version livrée utilise donc des **scènes illustrées stylisées**, dessinées en Python
(`illustrations.py`, sans photo ni image générée par IA). Chaque scène est une pile de calques,
ce qui donne un vrai parallaxe 2.5D. La mention « Illustrations stylisées — visuels non
contractuels » est ajoutée à l'écran, en plus des mentions obligatoires.

```bash
python3 build_reel.py --illustrations
```

## Lancer le rendu avec les vrais visuels du site (sur une machine qui accède à maisonrecherchee.fr)

```bash
python3 -m pip install pillow numpy          # + optionnel : pip install depthflow
# ffmpeg/ffprobe doivent être installés (brew install ffmpeg / apt install ffmpeg)
python3 build_reel.py                        # DepthFlow si dispo, sinon Ken Burns
python3 build_reel.py --no-depthflow         # forcer Ken Burns
```

Le script télécharge les 9 visuels listés dans `SOURCES` vers `sources/`, dont la 1re image
de rendu de la page The One, qu'il repère automatiquement. Si un téléchargement échoue, déposez le fichier à la main
dans `sources/` sous le même nom (`palmeraie.jpg`, `theone.jpg`, `hero-home.webm`…),
puis relancez.

Sorties : `reel_babinvest_01.mp4`, `cover_babinvest_01.png`, `caption.txt`,
`contact_sheet.png`, `build_log.txt` (sources utilisées, DepthFlow ou Ken Burns, ffprobe).

`--preview` produit dans `preview/` un aperçu de mise en page : les sources manquantes
y sont remplacées par des aplats gris « SOURCE MANQUANTE ». Cet aperçu n'est jamais livrable.

Pour un autre Reel, dupliquez `build_reel.py` et modifiez seulement le bloc CONFIG :
`SOURCES`, `SEGMENTS`, `FOCUS`, `COVER_*` et `CAPTION`.

Polices : Fraunces et Inter (Google Fonts, licence OFL, voir `fonts/`).
