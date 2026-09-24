# -*- coding: utf-8 -*-
from odoo import api, models


class PeopleEngineLegalEngine(models.AbstractModel):
    _name = "pe.legal.engine"
    _description = "Moteur bibliothèque juridique People Engine"

    DISCLAIMER = """
⚠️ AVIS IMPORTANT : Les informations fournies par People Engine
sont à titre informatif uniquement et ne constituent pas
des conseils juridiques. Pour toute action disciplinaire formelle
ou mise à pied, consultez un avocat en droit du travail
ou votre service RH qualifié avant d'agir.
"""

    @api.model
    def get_relevant_articles(self, action_type, jurisdiction_code, context=None):
        domain = [
            ("is_current", "=", True),
            ("jurisdiction_id.code", "=", jurisdiction_code),
        ]
        articles = self.env["pe.legal.article"].search(domain)
        if action_type:
            articles = articles.filtered(
                lambda a: not a.applicable_action_ids
                or action_type in a.applicable_action_ids.mapped("code")
            )
        return articles

    @api.model
    def build_legal_context_for_claude(
        self, action_type, jurisdiction_code, employee_profile=None
    ):
        articles = self.get_relevant_articles(action_type, jurisdiction_code)
        if not articles:
            return (
                f"Juridiction : {jurisdiction_code}\n"
                f"Aucun article spécifique trouvé dans la base.\n"
                f"{self.DISCLAIMER}"
            )
        legal_context = f"CONTEXTE LÉGAL — {jurisdiction_code}\n{'=' * 50}\n\n"
        for article in articles[:5]:
            legal_context += f"""
Article {article.code} — {article.title}
{'-' * 40}
Résumé pratique : {article.plain_language or article.summary or '—'}

Obligations employeur : {article.employer_obligations or 'Non spécifié'}
Droits employé : {article.employee_rights or 'Non spécifié'}
Délais à respecter : {self._extract_delays(article)}

"""
        legal_context += f"\n{self.DISCLAIMER}"
        return legal_context

    @api.model
    def check_compliance(self, action_type, jurisdiction_code, employee_data):
        warnings = []
        blockers = []
        employee_data = employee_data or {}
        if jurisdiction_code == "QC":
            blockers, warnings = self._check_quebec_compliance(
                action_type, employee_data, blockers, warnings
            )
        elif jurisdiction_code == "FR":
            blockers, warnings = self._check_france_compliance(
                action_type, employee_data, blockers, warnings
            )
        elif jurisdiction_code == "MA":
            blockers, warnings = self._check_morocco_compliance(
                action_type, employee_data, blockers, warnings
            )
        return {
            "compliant": len(blockers) == 0,
            "can_proceed": len(blockers) == 0,
            "warnings": warnings,
            "blockers": blockers,
            "disclaimer": self.DISCLAIMER,
        }

    @api.model
    def _check_quebec_compliance(self, action_type, employee_data, blockers, warnings):
        months_employed = employee_data.get("months_employed", 0) or 0
        if action_type in ("termination",):
            if months_employed < 3:
                warnings.append(
                    "LNT Art. 82 : Employé en probation — "
                    "délai de congé peut ne pas s'appliquer"
                )
            elif months_employed < 12:
                blockers.append(
                    "LNT Art. 82 : Délai de congé minimum 1 semaine requis"
                )
            elif months_employed < 60:
                blockers.append(
                    "LNT Art. 82 : Délai de congé minimum 2 semaines requis"
                )
            if months_employed >= 24:
                warnings.append(
                    "LNT Art. 124 : Employé avec 2+ ans d'ancienneté — "
                    "cause juste et suffisante requise. Documenter soigneusement."
                )
        if action_type in ("formal_warn", "pip"):
            warnings.append(
                "Jurisprudence QC : Respecter la gradation des sanctions — "
                "avertissement verbal → écrit → suspension → congédiement."
            )
        return blockers, warnings

    @api.model
    def _check_france_compliance(self, action_type, employee_data, blockers, warnings):
        months_employed = employee_data.get("months_employed", 0) or 0
        contract_type = employee_data.get("contract_type", "CDI")
        if action_type == "termination":
            if contract_type == "CDI":
                blockers.append(
                    "Code Travail L1232-2 : Entretien préalable obligatoire "
                    "avant tout licenciement CDI (convocation LRAR, 5 jours ouvrables)."
                )
                if months_employed >= 8:
                    blockers.append(
                        "Code Travail L1237-1 : Préavis obligatoire selon convention."
                    )
        if action_type == "formal_warn":
            blockers.append(
                "Code Travail L1332-2 : Notification écrite obligatoire "
                "dans le mois suivant l'entretien disciplinaire."
            )
        return blockers, warnings

    @api.model
    def _check_morocco_compliance(self, action_type, employee_data, blockers, warnings):
        months_employed = employee_data.get("months_employed", 0) or 0
        if action_type == "termination":
            blockers.append(
                "Code Travail Art. 62-63 : Convocation RAR et entretien préalable "
                "obligatoires (délai minimum 8 jours) avant licenciement."
            )
            if months_employed >= 12:
                warnings.append(
                    "Code Travail Art. 43-51 : Préavis obligatoire selon catégorie "
                    "et ancienneté (8 jours à 3 mois)."
                )
            if months_employed >= 12:
                warnings.append(
                    "Code Travail Art. 52-53 : Indemnité de licenciement due "
                    "(sauf faute grave ou force majeure)."
                )
        if action_type in ("formal_warn", "pip"):
            warnings.append(
                "Code Travail Maroc : Gradation des sanctions recommandée — "
                "avertissement → mise en demeure → convocation → licenciement."
            )
        return blockers, warnings

    @api.model
    def _extract_delays(self, article):
        content = (article.content or "").lower()
        if "jour" in content or "semaine" in content:
            return "Vérifier les délais dans l'article complet"
        return "Consulter l'article"
