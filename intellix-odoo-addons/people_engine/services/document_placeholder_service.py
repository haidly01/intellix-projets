# -*- coding: utf-8 -*-
import re
from datetime import date

from odoo import fields


class DocumentPlaceholderService:
    """Remplace les variables dans les modèles de lettres RH."""

    _FR_MONTHS = (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    )

    def __init__(self, env):
        self.env = env

    @classmethod
    def format_fr_date(cls, value):
        if not value:
            return ""
        if isinstance(value, str):
            value = fields.Date.to_date(value)
        if not isinstance(value, date):
            return ""
        return "%d %s %d" % (value.day, cls._FR_MONTHS[value.month - 1], value.year)

    def _split_name(self, full_name):
        full_name = (full_name or "").strip()
        if not full_name:
            return "", ""
        parts = full_name.split(None, 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else parts[0]
        return first_name, last_name

    def build_values(self, profile, letter_date=None):
        profile.ensure_one()
        employee = profile.employee_id
        company = profile.company_id or self.env.company
        letter_date = letter_date or fields.Date.context_today(self.env.user)
        if isinstance(letter_date, str):
            letter_date = fields.Date.to_date(letter_date)

        full_name = employee.name or profile.display_name or ""
        first_name, last_name = self._split_name(full_name)
        job_name = ""
        if profile.job_id:
            job_name = profile.job_id.name
        elif employee.job_id:
            job_name = employee.job_id.name

        start_date = employee.date_start or employee.contract_date_start
        date_fr = self.format_fr_date(letter_date)
        start_date_fr = self.format_fr_date(start_date)

        return {
            "full_name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "job": job_name or "",
            "company": company.name or "",
            "date_fr": date_fr,
            "start_date": start_date_fr,
            "department": profile.department_id.name if profile.department_id else "",
            "email": employee.work_email or employee.private_email or "",
            "telephone": employee.work_phone or employee.mobile_phone or "",
            "adresse": employee.private_street or "",
            "ville": employee.private_city or "",
            "salaire": str(int(profile.salaire_base or 0)),
            "cin": employee.ssnid or "",
        }

    def _placeholder_map(self, values):
        return {
            "{{employee_name}}": values["full_name"],
            "{{nom}}": values["last_name"],
            "{{prenom}}": values["first_name"],
            "{{name}}": values["full_name"],
            "{{date}}": values["date_fr"],
            "{{date_today}}": values["date_fr"],
            "{{poste}}": values["job"],
            "{{job}}": values["job"],
            "{{company}}": values["company"],
            "{{societe}}": values["company"],
            "{{date_debut}}": values["start_date"],
            "{{department}}": values["department"],
            "{{departement}}": values["department"],
            "[DATE]": values["date_fr"],
            "[Date]": values["date_fr"],
            "[PRÉNOM NOM]": values["full_name"],
            "[Prénom Nom]": values["full_name"],
            "[PRENOM NOM]": values["full_name"],
            "[NOM]": values["last_name"],
            "[Nom]": values["last_name"],
            "[PRÉNOM]": values["first_name"],
            "[Prénom]": values["first_name"],
            "[PRENOM]": values["first_name"],
            "[TITRE DU POSTE]": values["job"],
            "[Titre du poste]": values["job"],
            "[POSTE]": values["job"],
            "[Poste]": values["job"],
            "[DATE DE DÉBUT]": values["start_date"],
            "[Date de début]": values["start_date"],
            "[DATE DE DEBUT]": values["start_date"],
            "[SOCIÉTÉ]": values["company"],
            "[Société]": values["company"],
            "[SOCIETE]": values["company"],
            "[EMAIL]": values["email"],
            "[Email]": values["email"],
            "[TELEPHONE]": values["telephone"],
            "[Téléphone]": values["telephone"],
            "[ADRESSE]": values["adresse"],
            "[Adresse]": values["adresse"],
            "[VILLE]": values["ville"],
            "[Ville]": values["ville"],
            "[SALAIRE]": values["salaire"],
            "[Salaire]": values["salaire"],
            "[CIN]": values["cin"],
            "{{email}}": values["email"],
            "{{telephone}}": values["telephone"],
            "{{salaire}}": values["salaire"],
            "{{cin}}": values["cin"],
        }

    def render(self, content, profile, letter_date=None):
        if not content:
            return ""
        values = self.build_values(profile, letter_date=letter_date)
        # Placeholders contrat (description_variable, objectifs_text, devise)
        contract = profile.contract_ids.filtered(
            lambda c: c.statut in ("active", "draft")
        )[:1]
        if contract:
            content = content.replace("{{description_variable}}", contract.description_variable or "")
            content = content.replace("{{objectifs_text}}", contract.objectifs_text or "")
            content = content.replace("{{devise}}", contract.devise or profile.devise_remuneration or "MAD")
            content = content.replace("{{primes}}", contract.description_variable or "")
        else:
            content = content.replace("{{description_variable}}", profile.description_variable or "")
            content = content.replace("{{objectifs_text}}", "")
            content = content.replace("{{devise}}", profile.devise_remuneration or "MAD")
            content = content.replace("{{primes}}", profile.description_variable or "")
        rendered = content
        for token, replacement in self._placeholder_map(values).items():
            rendered = rendered.replace(token, replacement or "")
        rendered = re.sub(
            r"\{\{\s*([a-zA-Z_]+)\s*\}\}",
            lambda match: values.get(match.group(1).lower(), match.group(0)),
            rendered,
        )
        return rendered
