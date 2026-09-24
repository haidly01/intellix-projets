# -*- coding: utf-8 -*-
"""Parser CSV / XLSX pour import contacts campagne."""
import base64
import csv
import io
import re


def normalize_phone(phone, default_country="FR"):
    if not phone:
        return ""
    digits = re.sub(r"\D", "", str(phone))
    country = (default_country or "FR").upper()
    if country in ("CA", "QC", "US"):
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) > 10:
            head = digits[:10]
            if head[0] in "23456789":
                digits = head
            else:
                digits = digits[-10:]
        return digits[:10] if len(digits) >= 10 else ""
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if country == "FR":
        if digits.startswith("33") and len(digits) >= 11:
            digits = digits[2:]
        if len(digits) == 10 and digits.startswith("0"):
            digits = digits[1:]
    if country in ("ES", "ESP", "SPAIN"):
        if digits.startswith("34") and len(digits) > 9:
            digits = digits[2:]
        if len(digits) > 9:
            digits = digits[-9:]
        return digits if len(digits) == 9 else ""
    return digits[:18]


def is_valid_phone(phone, default_country="FR"):
    """True si le numéro est valide pour le pays de la campagne."""
    country = (default_country or "FR").upper()
    norm = normalize_phone(phone, country)
    if not norm:
        return False, ""
    if country in ("ES", "ESP", "SPAIN"):
        return bool(re.match(r"^[6789]\d{8}$", norm)), norm
    if country in ("CA", "QC", "US"):
        return bool(re.match(r"^[2-9]\d{9}$", norm)), norm
    if country == "FR":
        return bool(re.match(r"^[1-9]\d{8}$", norm)), norm
    return len(norm) >= 8, norm


class FileImporter:
    """Parse fichiers contacts (CSV ou XLSX)."""

    def parse(self, file_data, filename="", default_country="FR"):
        raw = base64.b64decode(file_data)
        return self.parse_bytes(raw, filename or "", default_country=default_country)

    def parse_bytes(self, raw, filename="", default_country="FR"):
        name = (filename or "").lower()
        country = (default_country or "FR").upper()
        if country in ("ES", "ESP", "SPAIN") or any(
            hint in name for hint in ("espagne", "spain", "avatrade", "españa")
        ):
            country = "ES"
        if "broker source" in name:
            return self._parse_broker_xlsx(raw)
        if "artisan" in name:
            return self._parse_artisans_csv(raw)
        if "rappel" in name and "quebec" in name:
            return self._parse_csv(raw, default_country="CA")
        if name.endswith(".xlsx") or name.endswith(".xls"):
            return self._parse_xlsx(raw, default_country=country)
        return self._parse_csv(raw, default_country=country)

    def _parse_csv(self, raw, default_country="FR"):
        text = raw.decode("utf-8-sig", errors="replace")
        delimiter = ";" if text.count(";") > text.count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("CSV vide ou sans en-têtes.")
        return self._rows_from_dict_reader(reader, default_country=default_country)

    def _parse_xlsx(self, raw, default_country="FR"):
        try:
            import openpyxl
        except ImportError as exc:
            raise ValueError(
                "openpyxl requis pour les fichiers XLSX (pip install openpyxl)."
            ) from exc
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        sheet = wb.active
        rows_iter = sheet.iter_rows(values_only=True)
        headers = [str(h or "").strip() for h in next(rows_iter, [])]
        if not headers:
            raise ValueError("Feuille XLSX vide.")
        field_map = {h.lower(): i for i, h in enumerate(headers)}

        def col(*names):
            for n in names:
                idx = field_map.get(n.lower())
                if idx is not None:
                    return idx
            return None

        phone_idx = col("phone", "phone_number", "telephone", "tel", "mobile", "tel")
        if phone_idx is None:
            raise ValueError("Colonne téléphone introuvable.")
        fn_idx = col("first_name", "prenom", "prénom", "firstname")
        ln_idx = col("last_name", "nom", "lastname")
        email_idx = col("email", "courriel")
        addr_idx = col("adresse", "address", "address1")
        city_idx = col("ville", "city")
        zip_idx = col("cp", "code postal", "postal_code", "code_postal")
        code_idx = col("vendor_lead_code", "code", "id")

        rows = []
        for row in rows_iter:
            if not row or phone_idx >= len(row):
                continue
            phone = normalize_phone(row[phone_idx], default_country=default_country)
            if not phone:
                continue
            comment_idx = col("commentaire", "comments", "notes")
            email_val = str(row[email_idx] or "").strip()[:70] if email_idx is not None else ""
            if not email_val and comment_idx is not None and "@" in str(row[comment_idx] or ""):
                email_val = str(row[comment_idx] or "").strip()[:70]
            rows.append(
                {
                    "phone_number": phone,
                    "first_name": str(row[fn_idx] or "").strip()[:30] if fn_idx is not None else "",
                    "last_name": str(row[ln_idx] or "").strip()[:30] if ln_idx is not None else "",
                    "email": email_val,
                    "address1": str(row[addr_idx] or "").strip()[:100] if addr_idx is not None else "",
                    "city": str(row[city_idx] or "").strip()[:50] if city_idx is not None else "",
                    "postal_code": str(row[zip_idx] or "").strip()[:10] if zip_idx is not None else "",
                    "vendor_lead_code": str(row[code_idx] or "XLSX")[:20]
                    if code_idx is not None
                    else "XLSX",
                }
            )
        return rows

    def _parse_artisans_csv(self, raw):
        text = raw.decode("utf-8-sig", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = []
        seen = set()
        for row in reader:
            if len(row) < 8:
                continue
            phone = normalize_phone(row[7])
            if len(phone) < 9 or phone in seen:
                continue
            seen.add(phone)
            company = str(row[0] or "").strip()
            rows.append(
                {
                    "phone_number": phone,
                    "first_name": "",
                    "last_name": company[:30],
                    "email": str(row[9] or "").strip()[:70] if len(row) > 9 else "",
                    "address1": str(row[2] or "").strip()[:100],
                    "city": str(row[3] or "").strip()[:50],
                    "postal_code": re.sub(r"\D", "", str(row[4] or ""))[:10],
                    "vendor_lead_code": "ARTISAN",
                    "source_id": "ARTISANS",
                    "comments": str(row[5] or "").strip()[:255],
                }
            )
        return rows

    def _parse_broker_xlsx(self, raw):
        try:
            import openpyxl
        except ImportError as exc:
            raise ValueError("openpyxl requis pour les fichiers XLSX.") from exc
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        rows = []
        for row in wb.active.iter_rows(values_only=True):
            if not row or len(row) < 8:
                continue
            phone = normalize_phone(row[6])
            if not phone:
                continue
            full_name = str(row[0] or "").strip()
            full_name = re.sub(r"^(M|MME|MR|MLLE|MONSIEUR|MADAME)\s+", "", full_name, flags=re.I)
            first_name, last_name = "", full_name[:30]
            if "," in full_name:
                parts = [p.strip() for p in full_name.split(",", 1)]
                last_name = (parts[0] or "")[:30]
                first_name = (parts[1] if len(parts) > 1 else "")[:30]
            rows.append(
                {
                    "phone_number": phone,
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": str(row[7] or "").strip()[:70],
                    "address1": str(row[3] or "").strip()[:100],
                    "city": str(row[2] or "").strip()[:50],
                    "postal_code": str(row[1] or "").strip()[:10],
                    "vendor_lead_code": "BROKER",
                }
            )
        return rows

    def _rows_from_dict_reader(self, reader, default_country="FR"):
        fields_map = {h.lower().strip(): h for h in reader.fieldnames}

        def col(*names):
            for n in names:
                key = fields_map.get(n.lower())
                if key:
                    return key
            return None

        phone_col = col("phone", "phone_number", "telephone", "tel", "mobile", "tel")
        if not phone_col:
            raise ValueError(
                "Colonne téléphone introuvable (phone, phone_number, telephone…)."
            )
        fn_col = col("first_name", "prenom", "prénom", "firstname")
        ln_col = col("last_name", "nom", "lastname")
        email_col = col("email", "courriel")
        comment_col = col("commentaire", "comments", "notes")
        addr_col = col("adresse", "address", "address1")
        city_col = col("ville", "city")
        zip_col = col("cp", "code postal", "postal_code", "code_postal")
        code_col = col("vendor_lead_code", "code", "id")
        state_col = col("state", "province")
        country_col = col("country_code", "country")
        rank_col = col("rank")
        status_col = col("status")

        rows = []
        for row in reader:
            country = (
                (row.get(country_col) or default_country or "FR").strip().upper()
                if country_col
                else default_country
            )
            phone = normalize_phone(row.get(phone_col) or "", country)
            if not phone:
                continue
            email_val = (row.get(email_col) or "").strip()[:70] if email_col else ""
            if not email_val and comment_col and "@" in str(row.get(comment_col) or ""):
                email_val = str(row.get(comment_col) or "").strip()[:70]
            rank_val = 0
            if rank_col and str(row.get(rank_col) or "").strip().isdigit():
                rank_val = int(row.get(rank_col))
            rows.append(
                {
                    "phone_number": phone,
                    "first_name": (row.get(fn_col) or "").strip()[:30] if fn_col else "",
                    "last_name": (row.get(ln_col) or "").strip()[:30] if ln_col else "",
                    "email": email_val,
                    "address1": (row.get(addr_col) or "").strip()[:100] if addr_col else "",
                    "city": (row.get(city_col) or "").strip()[:50] if city_col else "",
                    "postal_code": (row.get(zip_col) or "").strip()[:10] if zip_col else "",
                    "state": (row.get(state_col) or "").strip()[:2] if state_col else "",
                    "country_code": country[:3],
                    "phone_code": (
                        "1"
                        if country in ("CA", "QC", "US")
                        else "34"
                        if country in ("ES", "ESP", "SPAIN")
                        else "33"
                    ),
                    "comments": (row.get(comment_col) or "").strip()[:255]
                    if comment_col
                    else "",
                    "rank": rank_val,
                    "status": (row.get(status_col) or "NEW").strip()[:6]
                    if status_col
                    else "NEW",
                    "vendor_lead_code": (row.get(code_col) or "CSV")[:20]
                    if code_col
                    else "CSV",
                }
            )
        return rows
