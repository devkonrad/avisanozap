import csv
import io
import re
import unicodedata

from django.db import transaction

from .models import Prospect


SEGMENT_MAP = {
    "salao de beleza": Prospect.Segment.BEAUTY_SALON,
    "barbearia": Prospect.Segment.BARBERSHOP,
    "estetica": Prospect.Segment.AESTHETICS,
    "esmalteria": Prospect.Segment.NAIL_SALON,
    "manicure": Prospect.Segment.MANICURE,
}

PHONE_STATUS_MAP = {
    "celular - confirmar whatsapp": (
        Prospect.PhoneStatus.MOBILE_UNVERIFIED
    ),
    "telefone fixo - whatsapp nao confirmado": (
        Prospect.PhoneStatus.LANDLINE_UNVERIFIED
    ),
    "ddd divergente - verificar": (
        Prospect.PhoneStatus.AREA_CODE_TO_VERIFY
    ),
    "whatsapp confirmado": (
        Prospect.PhoneStatus.WHATSAPP_CONFIRMED
    ),
}


def normalize_text(value):
    normalized = unicodedata.normalize("NFKD", value.strip())
    normalized = "".join(
        char for char in normalized
        if not unicodedata.combining(char)
    )
    return normalized.casefold()


def normalize_phone_number(value):
    digits = re.sub(r"\D", "", value)

    if len(digits) in (10, 11):
        return f"55{digits}"

    if len(digits) in (12, 13) and digits.startswith("55"):
        return digits

    raise ValueError("Número de telefone inválido.")


def read_csv_rows(uploaded_file):
    content = uploaded_file.read()

    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")

    if not content.strip():
        raise ValueError("O arquivo CSV está vazio.")

    sample = content[:2048]

    try:
        dialect = csv.Sniffer().sniff(
            sample,
            delimiters=";,\t",
        )
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = ";"

    reader = csv.DictReader(
        io.StringIO(content),
        dialect=dialect,
    )

    if not reader.fieldnames:
        raise ValueError("O CSV não possui cabeçalho.")

    reader.fieldnames = [
        normalize_text(name or "")
        for name in reader.fieldnames
    ]

    required_columns = {
        "nome",
        "segmento",
        "telefone_publico",
        "bairro",
        "status_whatsapp",
    }

    missing_columns = required_columns - set(reader.fieldnames)

    if missing_columns:
        raise ValueError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(sorted(missing_columns))
        )

    return reader


def import_prospects_csv(uploaded_file):
    reader = read_csv_rows(uploaded_file)

    existing_phones = set(
        Prospect.objects.values_list(
            "phone_number",
            flat=True,
        )
    )

    seen_phones = set()

    records = []
    duplicates = 0
    invalid = 0
    errors = []

    for line_number, row in enumerate(reader, start=2):
        try:
            business_name = (row.get("nome") or "").strip()
            segment_name = normalize_text(
                row.get("segmento") or ""
            )
            raw_phone = (row.get("telefone_publico") or "").strip()
            neighborhood = (row.get("bairro") or "").strip()
            phone_status_name = normalize_text(
                row.get("status_whatsapp") or ""
            )

            if not business_name:
                raise ValueError("Nome do estabelecimento ausente.")

            segment = SEGMENT_MAP.get(segment_name)

            if not segment:
                raise ValueError("Segmento não reconhecido.")

            phone_number = normalize_phone_number(raw_phone)

            phone_status = PHONE_STATUS_MAP.get(
                phone_status_name
            )

            if not phone_status:
                raise ValueError(
                    "Classificação do telefone não reconhecida."
                )

            if (
                phone_number in existing_phones
                or phone_number in seen_phones
            ):
                duplicates += 1
                continue

            seen_phones.add(phone_number)

            records.append(
                Prospect(
                    business_name=business_name,
                    phone_number=phone_number,
                    phone_status=phone_status,
                    segment=segment,
                    city="Porto Alegre",
                    neighborhood=neighborhood,
                    source="Lista pública",
                )
            )

        except (ValueError, AttributeError) as exc:
            invalid += 1

            if len(errors) < 50:
                errors.append(
                    f"Linha {line_number}: {exc}"
                )

    with transaction.atomic():
        Prospect.objects.bulk_create(records)

    return {
        "total": len(records) + duplicates + invalid,
        "imported": len(records),
        "duplicates": duplicates,
        "invalid": invalid,
        "errors": errors,
    }
