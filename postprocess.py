#!/usr/bin/env python3
import csv
import datetime as dt
import json
import re
import sys
from pathlib import Path


FIELDS = [
    "Last_name_ru", "First_name_ru", "Middle_name_ru", "Sex_ru",
    "Birth_date", "Birth_place_ru", "Issue_date",
    "Issue_organisation_code", "Licence_number", "Issue_organization_ru",
]
CURRENT_DATE = dt.date(2026, 10, 1)


def clean(value):
    return " ".join(str(value or "").split()).strip()


def upper(value):
    return clean(value).upper()


def field_text(item):
    return clean(" ".join(line.get("text", "") for line in (item or {}).get("lines", [])))


def char_min(item):
    values = [c for line in (item or {}).get("lines", [])
              for c in line.get("char_conf", [])]
    return min(values) if values else 0.0


def canonical_date(value):
    value = clean(value).replace("/", ".").replace("-", ".")
    digits = re.sub(r"\D", "", value)
    if len(digits) == 8:
        return f"{digits[:2]}.{digits[2:4]}.{digits[4:]}"
    return value


def parse_date(value):
    try:
        return dt.datetime.strptime(canonical_date(value), "%d.%m.%Y").date()
    except ValueError:
        return None


def canonical_code(value):
    digits = re.sub(r"\D", "", value)
    return f"{digits[:3]}-{digits[3:]}" if len(digits) == 6 else clean(value)


def canonical_sex(value):
    value = upper(value).rstrip(".")
    if value == "ЖЕН":
        value = "ЖЕН."
    elif value == "МУЖ":
        value = "МУЖ."
    return value if value in {"МУЖ.", "ЖЕН."} else clean(value)


def mrz_checks(document):
    mrz = document.get("mrz") or {}
    lines = mrz.get("lines") or []
    if len(lines) < 2:
        return {}
    line = lines[1].get("text", "")
    if len(line) < 41:
        return {}
    values = {
        "Birth_date": f"{line[17:19]}.{line[15:17]}.20{line[13:15]}",
        "Issue_date": f"{line[33:35]}.{line[31:33]}.20{line[29:31]}",
        "Issue_organisation_code": f"{line[35:38]}-{line[38:41]}",
    }
    sex = {"M": "МУЖ.", "F": "ЖЕН."}.get(line[20])
    if sex:
        values["Sex_ru"] = sex
    return values


RU_TO_MRZ = {
    "А": "A", "Б": "B", "В": "V", "Г": "G", "Д": "D", "Е": "E",
    "Ё": "E", "Ж": "ZH", "З": "Z", "И": "I", "Й": "I", "К": "K",
    "Л": "L", "М": "M", "Н": "N", "О": "O", "П": "P", "Р": "R",
    "С": "S", "Т": "T", "У": "U", "Ф": "F", "Х": "KH", "Ц": "TS",
    "Ч": "CH", "Ш": "SH", "Щ": "SHCH", "Ъ": "", "Ы": "Y", "Ь": "",
    "Э": "E", "Ю": "IU", "Я": "IA",
}


def mrz_surname(document):
    lines = (document.get("mrz") or {}).get("lines") or []
    if not lines:
        return None, 0.0
    text = lines[0].get("text", "")
    if not text.startswith("PNRUS") or "<<" not in text:
        return None, 0.0
    surname = text[5:].split("<<", 1)[0].replace("<", "")
    confidence = min(lines[0].get("char_conf", []) or [0.0])
    return surname, confidence


def russian_to_mrz(value):
    return "".join(RU_TO_MRZ.get(char, char) for char in upper(value)
                   if char.isalpha() or char in "- ").replace("-", "").replace(" ", "")


def valid_on_date(fields):
    birth = parse_date(fields.get("Birth_date", ""))
    issue = parse_date(fields.get("Issue_date", ""))
    if not birth or not issue or issue < birth or issue > CURRENT_DATE:
        return False
    age_at_issue = issue.year - birth.year - ((issue.month, issue.day) < (birth.month, birth.day))
    if age_at_issue < 14:
        return False
    def birthday(year):
        try:
            return birth.replace(year=year)
        except ValueError:
            return birth.replace(year=year, day=28)

    if age_at_issue < 20:
        expiry = birthday(birth.year + 20) + dt.timedelta(days=90)
    elif age_at_issue < 45:
        expiry = birthday(birth.year + 45) + dt.timedelta(days=90)
    else:
        expiry = CURRENT_DATE
    return CURRENT_DATE <= expiry


def load_reference(path):
    if not path.exists():
        return {}
    result = {}
    with path.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            result.setdefault(row["code"], set()).add(upper(row["name"]))
    return result


def process(document, reference):
    fields = {}
    quality = document.get("quality") or {}
    signals = []
    for name in FIELDS:
        item = (document.get("viz") or {}).get(name)
        value = field_text(item)
        if not item or not value:
            return {"doc_id": document["doc_id"], "decision": "reject"}
        if name == "Birth_date" or name == "Issue_date":
            value = canonical_date(value)
        elif name == "Issue_organisation_code":
            value = canonical_code(value)
        elif name == "Sex_ru":
            value = canonical_sex(value)
        fields[name] = value
        conf_floor = 0.992 if name in {"Birth_place_ru", "Issue_organization_ru"} else 0.997
        if name in {"Birth_place_ru", "Issue_organization_ru"}:
            char_floor = 0.992
        elif name == "Licence_number":
            char_floor = 0.999
        else:
            char_floor = 0.995
        signals.append(item.get("conf", 0) >= conf_floor and char_min(item) >= char_floor)

    if not all(signals):
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if quality.get("doc_px", 0) < 900 or quality.get("sharpness", 0) < 90:
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", fields["Birth_date"]):
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", fields["Issue_date"]):
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if not re.fullmatch(r"\d{3}-\d{3}", fields["Issue_organisation_code"]):
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if fields["Sex_ru"] not in {"МУЖ.", "ЖЕН."}:
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if not re.fullmatch(r"\d{2} \d{2} \d{6}", fields["Licence_number"]):
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if not valid_on_date(fields):
        return {"doc_id": document["doc_id"], "decision": "reject"}

    redundant = mrz_checks(document)
    mrz_name, mrz_name_conf = mrz_surname(document)
    if mrz_name and mrz_name_conf >= 0.999:
        if russian_to_mrz(fields["Last_name_ru"]) != mrz_name:
            return {"doc_id": document["doc_id"], "decision": "reject"}
    for name in ("Birth_date", "Issue_date", "Sex_ru", "Issue_organisation_code"):
        if name in redundant:
            lines = (document.get("mrz") or {}).get("lines", [])
            mrz_conf = min(lines[1].get("char_conf", []) or [0])
            if mrz_conf >= 0.985 and upper(redundant[name]) != upper(fields[name]):
                return {"doc_id": document["doc_id"], "decision": "reject"}

    if reference and fields["Issue_organisation_code"] not in reference:
        return {"doc_id": document["doc_id"], "decision": "reject"}
    if fields["Issue_organization_ru"].split()[0] not in {
        "ОТДЕЛ", "ГУ", "ТП", "ОТДЕЛЕНИЕ", "УМВД", "ОВД", "МВД", "ОУФМС",
        "МИГРАЦИОННЫЙ", "ТЕРРИТОРИАЛЬНЫЙ", "УВД", "УФМС", "МП", "МЕЖРАЙОННЫЙ",
        "ОФМС", "ПАСПОРТНО-ВИЗОВОЕ", "РЕЗЕРВ", "МО", "1", "ПВС",
    }:
        return {"doc_id": document["doc_id"], "decision": "reject"}
    return {"doc_id": document["doc_id"], "decision": "accept", "fields": fields}


def main():
    if len(sys.argv) not in {3, 4}:
        raise SystemExit("usage: python postprocess.py predictions.jsonl answers.jsonl [subdivisions.csv]")
    source, target = map(Path, sys.argv[1:3])
    reference = load_reference(Path(sys.argv[3]) if len(sys.argv) == 4 else Path("reference/subdivisions.csv"))
    with source.open(encoding="utf-8") as src, target.open("w", encoding="utf-8") as dst:
        for line in src:
            if line.strip():
                dst.write(json.dumps(process(json.loads(line), reference), ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
