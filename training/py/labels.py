"""Map source labels to the shared taxonomy (src/types.ts).

A value of IGNORE marks a span that the benchmark neither requires nor counts as a false positive.
Address and name parts are merged into one entity when they are adjacent (see merge_parts).
"""

IGNORE = "IGNORE"
# Parts that merge into PERSON / ADDRESS. ADDRESS groups need an anchor part, otherwise IGNORE.
PERSON_PART = "PERSON_PART"
ADDR_ANCHOR = "ADDR_ANCHOR"
ADDR_PART = "ADDR_PART"

NEMOTRON = {
    "first_name": PERSON_PART, "last_name": PERSON_PART,
    "street_address": ADDR_ANCHOR, "postcode": ADDR_PART, "city": ADDR_PART, "state": ADDR_PART,
    "county": ADDR_PART, "prefecture": ADDR_PART, "country": ADDR_PART,
    "coordinate": "ADDRESS",
    "email": "EMAIL",
    "phone_number": "PHONE", "fax_number": "PHONE", "previous_phone_number": "PHONE",
    "ipv4": "IP", "ipv6": "IP",
    "credit_debit_card": "CREDIT_CARD",
    "account_number": "BANK_ACCOUNT",
    "ssn": "NATIONAL_ID", "national_id": "NATIONAL_ID", "tax_id": "NATIONAL_ID",
    "my_number": "JP_MYNUMBER",
    "password": "SECRET", "api_key": "SECRET", "http_cookie": "SECRET", "pin": "SECRET", "cvv": "SECRET",
    "company_name": "ORG", "domestic_company_name": "ORG",
    # Internal account identifiers are not PII in v1 (see PLAN.md, defaults to confirm).
    "user_name": IGNORE, "customer_id": IGNORE, "employee_id": IGNORE, "unique_id": IGNORE,
    "medical_record_number": "OTHER_ID", "health_plan_beneficiary_number": "OTHER_ID",
    "certificate_license_number": "OTHER_ID", "biometric_identifier": "OTHER_ID",
    "vehicle_identifier": "OTHER_ID", "license_plate": "OTHER_ID", "device_identifier": "OTHER_ID",
    "mac_address": "OTHER_ID", "health_insurer_number": "OTHER_ID",
    "health_insurance_card_symbol_number": "OTHER_ID", "public_expense_payer_number": "OTHER_ID",
}

OPENPII = {
    "GIVENNAME": PERSON_PART, "SURNAME": PERSON_PART,
    "STREET": ADDR_ANCHOR, "BUILDINGNUM": ADDR_ANCHOR, "CITY": ADDR_PART, "ZIPCODE": ADDR_PART,
    "EMAIL": "EMAIL", "TELEPHONENUM": "PHONE",
    "CREDITCARDNUMBER": "CREDIT_CARD",
    "IDCARDNUM": "NATIONAL_ID", "SOCIALNUM": "NATIONAL_ID", "PASSPORTNUM": "NATIONAL_ID",
    "DRIVERLICENSENUM": "NATIONAL_ID", "TAXNUM": "NATIONAL_ID",
    "ACCOUNTNUM": "BANK_ACCOUNT", "PASSWORD": "SECRET", "IPV4": "IP",
    "USERNAME": IGNORE, "ORGANISATION": "ORG",
}

PII_BENCH_ZH = {
    "person": "PERSON", "phone": "PHONE", "id_number": "CN_ID", "address": "ADDRESS",
    "email": "EMAIL", "bank_card": "CREDIT_CARD", "passport": "NATIONAL_ID", "license_plate": "OTHER_ID",
}

GRETEL = {
    "name": "PERSON", "first_name": PERSON_PART, "last_name": PERSON_PART,
    "company": "ORG", "street_address": "ADDRESS", "phone_number": "PHONE", "email": "EMAIL",
    "employee_id": IGNORE, "customer_id": IGNORE, "user_name": IGNORE,
    "bban": "BANK_ACCOUNT", "iban": "BANK_ACCOUNT",
    "ssn": "NATIONAL_ID", "passport_number": "NATIONAL_ID", "driver_license_number": "NATIONAL_ID",
    "credit_card_number": "CREDIT_CARD", "credit_card_security_code": "SECRET", "account_pin": "SECRET",
    "api_key": "SECRET", "password": "SECRET",
    "ipv4": "IP", "ipv6": "IP", "local_latlng": "ADDRESS",
}

MERGE_GAP_PERSON = set(" 　・·")
MERGE_GAP_ADDR = set(" 　,、，\n")


def merge_parts(text: str, spans: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """spans: (start, end, mapped label) in code points, sorted. Returns final labels."""
    spans = sorted(spans)
    out: list[tuple[int, int, str]] = []
    i = 0
    while i < len(spans):
        s, e, lab = spans[i]
        if lab == PERSON_PART:
            j = i + 1
            while j < len(spans) and spans[j][2] == PERSON_PART and gap_ok(text, e, spans[j][0], MERGE_GAP_PERSON, 2):
                e = max(e, spans[j][1])
                j += 1
            out.append((s, e, "PERSON"))
            i = j
        elif lab in (ADDR_ANCHOR, ADDR_PART):
            anchor = lab == ADDR_ANCHOR
            j = i + 1
            while j < len(spans) and spans[j][2] in (ADDR_ANCHOR, ADDR_PART) and gap_ok(text, e, spans[j][0], MERGE_GAP_ADDR, 3):
                e = max(e, spans[j][1])
                anchor = anchor or spans[j][2] == ADDR_ANCHOR
                j += 1
            out.append((s, e, "ADDRESS" if anchor else IGNORE))
            i = j
        else:
            out.append((s, e, lab))
            i += 1
    return out


def gap_ok(text: str, a: int, b: int, allowed: set[str], max_len: int) -> bool:
    if b < a:
        return True
    g = text[a:b]
    return len(g) <= max_len and all(ch in allowed for ch in g)
