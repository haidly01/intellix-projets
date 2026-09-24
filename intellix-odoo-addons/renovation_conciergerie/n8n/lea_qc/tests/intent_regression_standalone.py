#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests d'intention — port Python de detectIntent (miroir de conversation_sofia_process.js)."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "golden_transcripts.json"


def norm_transcript(raw: str) -> str:
    t = (raw or "").lower()
    t = unicodedata.normalize("NFD", t)
    t = re.sub(r"[\u0300-\u036f]", "", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def detect_greeting_intent(text: str) -> dict | None:
    if re.search(
        r"(locataire|je suis locataire|en location|je loue|pas ma maison|pas proprietaire)",
        text,
        re.I,
    ) and not re.search(r"oui|ouais|proprietaire|c est ma maison|c est moi", text, re.I):
        return {"intent": "locataire"}
    g_vendre = re.compile(
        r"(vendre|vente|mettre en vente|revendre|revente|me d[ée]barrasser de (ma|la) maison|liquider)", re.I
    )
    g_reno = re.compile(
        r"(r[ée]nov|r[ée]no|travaux|cuisine|salle\s+de\s+bain|toiture|sous-?\s*sol|agrandissement|fen[êe]tre|fenetre|refaire|r[ée]nover)",
        re.I,
    )
    if g_vendre.search(text) and g_reno.search(text):
        return {"intent": "proprietaire", "besoin": "les_deux"}
    if g_vendre.search(text):
        return {"intent": "proprietaire", "besoin": "immo"}
    if g_reno.search(text):
        return {"intent": "proprietaire", "besoin": "reno"}
    if re.search(r"(chalet|residence secondaire|maison de campagne|chalet de lac)", text, re.I):
        return {"intent": "proprietaire"}
    if re.search(
        r"(^\s*(allo|allô|bonjour|salut|ouin|hey|hello|hi)\b|oui\s+(allo|allô|bonjour)|^(ouin|ouais)\s*$)",
        text,
        re.I,
    ):
        return {"intent": "proprietaire"}
    if re.search(
        r"(proprietaire|proprietaires|\boui\b|ouais|ouaip|yes|yeah|yep|c est ma maison|c est moi|speaking|allo|allô)",
        text,
        re.I,
    ):
        return {"intent": "proprietaire"}
    if len(text) <= 4 and re.match(r"^(oui|oua|ouin|yes|yep|ok)$", text.strip(), re.I):
        return {"intent": "proprietaire"}
    return None


def detect_intent(step: str, text: str) -> dict:
    if not text.strip():
        return {"intent": "silence"}
    if re.search(
        r"(stop|retir|ne plus|pas interesse d etre contact|do not call|dnc|arretez|retirez mon numero|liste noire|trop d appels|ne plus appeler)",
        text,
        re.I,
    ):
        return {"intent": "dnc"}
    if step in ("GREETING", "GREETING_CLARIF"):
        greeting_hit = detect_greeting_intent(text)
        if greeting_hit:
            return greeting_hit
    if re.search(
        r"(rappeler plus tard|rappellez plus tard|dans quelques mois|une autre fois|pas maintenant|rappeler un autre jour)",
        text,
        re.I,
    ):
        return {"intent": "rappeler_plus_tard"}
    if re.search(
        r"(pas le temps|pas le temps la|je n ai pas le temps|occupe|trop occupe|pas disponible|pas le bon moment|periode chargee|trop occupes)",
        text,
        re.I,
    ):
        return {"intent": "pas_le_temps"}
    if re.search(r"(pas interesse|ca m interesse pas|non merci|laissez moi|au revoir)", text, re.I):
        return {"intent": "pas_interesse"}
    if re.search(
        r"(c est quoi|c est qui|comment vous avez|comment vous a eu|vous appelez de ou|qui etes vous|soumission entrepreneurs|soumission entrepreneur)",
        text,
        re.I,
    ):
        return {"intent": "qui_etes_vous"}
    if re.search(r"(arnaque|scam|pas confiance|je fais pas confiance|appels froids|phishing|frauduleux)", text, re.I):
        return {"intent": "arnaque"}
    if re.search(
        r"(deja un entrepreneur|j ai un entrepreneur|j ai mon entrepreneur|mon contracteur|mon beau frere fait ca)",
        text,
        re.I,
    ):
        return {"intent": "objection_entrepreneur"}
    if step in ("GREETING", "GREETING_CLARIF"):
        return {"intent": "incertain"}
    if step == "QUESTION_BESOIN":
        if re.search(
            r"(non|pas vraiment|rien|aucun|pas besoin|rien pour l instant|pas de projet|maison est correcte|maison parfaite|rien a faire|vient de finir|on a fini les travaux|on vient de renover|tout est correct|on est bien)",
            text,
            re.I,
        ):
            return {"intent": "pas_besoin"}
        veut_vendre = re.compile(
            r"(vendre|vente|revendre|revente|immobilier|mettre en vente|valeur|[ée]valu|estim|prix de (ma|la) maison|combien (ç|c)a vaut|combien vaut|je veux vendre|j'aimerais vendre|j aimerais vendre)",
            re.I,
        )
        veut_reno = re.compile(
            r"(r[ée]nov|r[ée]no|travaux|cuisine|salle\s+de\s+bain|toiture|sous-?\s*sol|agrandissement|fen[êe]tre|fenetre|r[ée]nover|refaire|projet)",
            re.I,
        )
        les_deux = re.compile(
            r"(?:les deux|les[\s-]?2|un peu les(?: deux| 2)?|un peu des|peut etre les|peut.?etre les|autant|\bdeux\b|\b2\b)",
            re.I,
        )
        if les_deux.search(text) or (veut_reno.search(text) and veut_vendre.search(text)):
            return {"intent": "les_deux"}
        if veut_vendre.search(text):
            return {"intent": "immo"}
        if veut_reno.search(text):
            return {"intent": "reno"}
        return {"intent": "incertain"}
    if step in ("QUESTION_PROJET", "SONDER_FUTUR"):
        projets = re.compile(
            r"(cuisine|salle\s+de\s+bain|toiture|fenetre|fenetres|sou\s*sol|sous\s*sol|soussol|agrandissement|isolation|plancher|terrasse|patio|garage|peinture|electricite|plomberie|renovation|travaux|salon|chambre|toit|fondation|revetement)",
            re.I,
        )
        if projets.search(text):
            return {"intent": "projet", "valeur": text[:80]}
        if re.search(r"(pas vraiment|pas pour l'instant|pas s[ûu]r|non)", text, re.I):
            return {"intent": "pas_projet"}
        if re.search(r"(oui|peut-être|peut être|un peu|quelque chose)", text, re.I):
            return {"intent": "projet", "valeur": text[:80]}
        if len(text.strip()) >= 3:
            return {"intent": "projet", "valeur": text[:80]}
        return {"intent": "incertain"}
    if step == "QUESTION_IMMO":
        if re.search(
            r"(oui|peut-être|peut être|d'ici|dans l'année|prochains mois|bient[oô]t|\d+\s*mois|12 mois|24 mois|6 mois|18 mois)",
            text,
            re.I,
        ):
            return {"intent": "vente_oui", "valeur": text[:80]}
        if re.search(r"(non|pas pour l'instant|pas vraiment)", text, re.I):
            return {"intent": "vente_non"}
        if len(text.strip()) >= 3:
            return {"intent": "vente_oui", "valeur": text[:80]}
    if step == "CAPTURER_DISPO":
        if re.search(r"(matin|avant.?midi|tot le matin|le matin)", text, re.I):
            return {"intent": "dispo", "valeur": "matin"}
        if re.search(r"(apres.?midi|apres midi|l apres midi|apres-midi)", text, re.I):
            return {"intent": "dispo", "valeur": "après-midi"}
        if re.search(r"(soir|soiree|fin de journee|le soir|apres 5|apres 17|apres 18)", text, re.I):
            return {"intent": "dispo", "valeur": "soir"}
        if re.search(r"\d{1,2}\s*h", text, re.I):
            return {"intent": "dispo", "valeur": text[:30]}
        if re.search(r"(oui|ok|correct|confirme)", text, re.I):
            return {"intent": "confirme"}
    return {"intent": "incertain"} if text.strip() else {"intent": "silence"}


BUILTIN_TESTS = [
    {"step": "GREETING", "raw": "oui", "expect": {"intent": "proprietaire"}, "label": "greeting oui"},
    {"step": "GREETING", "raw": "ouais", "expect": {"intent": "proprietaire"}, "label": "greeting ouais"},
    {"step": "GREETING", "raw": "je veux vendre ma maison", "expect": {"intent": "proprietaire", "besoin": "immo"}, "label": "vendre ma maison"},
    {"step": "GREETING", "raw": "cuisine", "expect": {"intent": "proprietaire", "besoin": "reno"}, "label": "cuisine au greeting"},
    {"step": "GREETING", "raw": "sous-sol", "expect": {"intent": "proprietaire", "besoin": "reno"}, "label": "sous-sol au greeting"},
    {"step": "QUESTION_PROJET", "raw": "Sous sol", "expect": {"intent": "projet"}, "label": "sous-sol projet"},
    {"step": "QUESTION_PROJET", "raw": "cuisine et salle de bain", "expect": {"intent": "projet"}, "label": "cuisine sdb"},
    {"step": "QUESTION_PROJET", "raw": "sou sol", "expect": {"intent": "projet"}, "label": "sou sol"},
    {"step": "QUESTION_BESOIN", "raw": "vendre ma maison", "expect": {"intent": "immo"}, "label": "besoin immo"},
    {"step": "QUESTION_BESOIN", "raw": "des travaux de rénovation", "expect": {"intent": "reno"}, "label": "besoin reno travaux"},
    {"step": "QUESTION_BESOIN", "raw": "rénovation", "expect": {"intent": "reno"}, "label": "besoin reno"},
    {"step": "GREETING", "raw": "", "expect": {"intent": "silence"}, "label": "silence greeting"},
    {"step": "CAPTURER_DISPO", "raw": "le soir", "expect": {"intent": "dispo", "valeur": "soir"}, "label": "dispo le soir"},
    {"step": "CAPTURER_DISPO", "raw": "le matin", "expect": {"intent": "dispo", "valeur": "matin"}, "label": "dispo le matin"},
    {"step": "CAPTURER_DISPO", "raw": "l'après-midi", "expect": {"intent": "dispo", "valeur": "après-midi"}, "label": "dispo apres-midi"},
    {"step": "CAPTURER_DISPO", "raw": "17h", "expect": {"intent": "dispo"}, "label": "dispo heure precise"},
    {"step": "GREETING", "raw": "non merci pas intéressé", "expect": {"intent": "pas_interesse"}, "label": "objection pas interesse"},
    {"step": "GREETING", "raw": "je ne suis pas intéressé", "expect": {"intent": "pas_interesse"}, "label": "objection pas interesse 2"},
    {"step": "GREETING", "raw": "pas le temps là", "expect": {"intent": "pas_le_temps"}, "label": "objection pas le temps"},
    {"step": "GREETING", "raw": "je n'ai pas le temps", "expect": {"intent": "pas_le_temps"}, "label": "objection pas le temps 2"},
    {"step": "GREETING", "raw": "je suis occupé", "expect": {"intent": "pas_le_temps"}, "label": "objection occupe"},
    {"step": "GREETING", "raw": "je suis locataire", "expect": {"intent": "locataire"}, "label": "objection locataire"},
    {"step": "GREETING", "raw": "en location", "expect": {"intent": "locataire"}, "label": "objection en location"},
    {"step": "GREETING", "raw": "rappeler plus tard", "expect": {"intent": "rappeler_plus_tard"}, "label": "objection rappeler plus tard"},
    {"step": "GREETING", "raw": "dans quelques mois", "expect": {"intent": "rappeler_plus_tard"}, "label": "objection dans quelques mois"},
    {"step": "GREETING", "raw": "c'est qui vous", "expect": {"intent": "qui_etes_vous"}, "label": "objection qui etes vous"},
    {"step": "GREETING", "raw": "c'est une arnaque", "expect": {"intent": "arnaque"}, "label": "objection arnaque"},
    {"step": "GREETING", "raw": "arrêtez de m'appeler", "expect": {"intent": "dnc"}, "label": "objection dnc arret"},
    {"step": "GREETING", "raw": "j'ai un chalet", "expect": {"intent": "proprietaire"}, "label": "chalet proprietaire"},
    {"step": "QUESTION_BESOIN", "raw": "les 2", "expect": {"intent": "les_deux"}, "label": "besoin les 2"},
    {"step": "QUESTION_BESOIN", "raw": "les deux", "expect": {"intent": "les_deux"}, "label": "besoin les deux"},
    {"step": "QUESTION_BESOIN", "raw": "un peu les 2", "expect": {"intent": "les_deux"}, "label": "besoin un peu les 2"},
    {"step": "QUESTION_BESOIN", "raw": "Un peu les 2.", "expect": {"intent": "les_deux"}, "label": "besoin un peu les 2 ponctuation"},
    {"step": "QUESTION_BESOIN", "raw": "un peu les deux", "expect": {"intent": "les_deux"}, "label": "besoin un peu les deux"},
    {"step": "QUESTION_BESOIN", "raw": "peut-être les deux", "expect": {"intent": "les_deux"}, "label": "besoin peut-etre les deux"},
    {"step": "QUESTION_BESOIN", "raw": "peut-être les 2", "expect": {"intent": "les_deux"}, "label": "besoin peut-etre les 2"},
    {"step": "QUESTION_BESOIN", "raw": "Un peu les 2 les 2", "expect": {"intent": "les_deux"}, "label": "besoin un peu les 2 stutter"},
    {"step": "QUESTION_BESOIN", "raw": "pas de projet", "expect": {"intent": "pas_besoin"}, "label": "pas de projet besoin"},
    {"step": "QUESTION_BESOIN", "raw": "maison parfaite", "expect": {"intent": "pas_besoin"}, "label": "maison parfaite besoin"},
    {"step": "QUESTION_PROJET", "raw": "j'ai déjà un entrepreneur", "expect": {"intent": "objection_entrepreneur"}, "label": "objection entrepreneur"},
    {"step": "QUESTION_IMMO", "raw": "3 mois", "expect": {"intent": "vente_oui"}, "label": "immo delai 3 mois"},
    {"step": "QUESTION_IMMO", "raw": "dans 6 mois", "expect": {"intent": "vente_oui"}, "label": "immo delai 6 mois"},
    {"step": "QUESTION_IMMO", "raw": "non", "expect": {"intent": "vente_non"}, "label": "immo vente non"},
]


def main() -> int:
    fixture_tests: list = []
    if FIXTURES.is_file():
        fixture_tests = json.loads(FIXTURES.read_text(encoding="utf-8"))
    all_tests = BUILTIN_TESTS + fixture_tests
    passed = failed = 0
    for t in all_tests:
        text = norm_transcript(t["raw"])
        got = detect_intent(t["step"], text)
        expect = t.get("expect") or {"intent": t.get("expect_intent")}
        ok = got.get("intent") == expect.get("intent")
        if ok and "besoin" in expect:
            ok = got.get("besoin") == expect["besoin"]
        if ok and "valeur" in expect:
            ok = got.get("valeur") == expect["valeur"]
        label = t.get("label") or f"[{t['step']}] \"{t['raw']}\""
        if ok:
            passed += 1
            print(f"OK  {label}")
        else:
            failed += 1
            extra = f" besoin={expect.get('besoin')}" if "besoin" in expect else ""
            got_extra = f" besoin={got.get('besoin')}" if got.get("besoin") else ""
            print(f"FAIL {label}: got intent={got.get('intent')}{got_extra}, expected intent={expect.get('intent')}{extra}")
    print(f"\n{passed}/{len(all_tests)} tests intent passés")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
