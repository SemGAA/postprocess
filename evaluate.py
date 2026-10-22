import json
import sys


FIELDS = [
    "Last_name_ru", "First_name_ru", "Middle_name_ru", "Sex_ru",
    "Birth_date", "Birth_place_ru", "Issue_date",
    "Issue_organisation_code", "Licence_number", "Issue_organization_ru",
]


def norm(value):
    return " ".join(str(value or "").split()).upper()


def load(path):
    with open(path, encoding="utf-8") as file:
        return {item["doc_id"]: item for item in map(json.loads, file)}


def main(answer_path, label_path):
    answers = load(answer_path)
    labels = load(label_path)
    missing = set(labels) - set(answers)
    if missing:
        examples = sorted(missing)[:3]
        raise SystemExit(f"нет ответа для {len(missing)} документов, например {examples}")

    good = 0
    bad = 0
    field_errors = {field: 0 for field in FIELDS}
    for doc_id, label in labels.items():
        answer = answers[doc_id]
        if answer.get("decision") != "accept":
            continue
        actual = answer.get("fields") or {}
        expected = label["fields"]
        wrong = [field for field in FIELDS if norm(actual.get(field)) != norm(expected[field])]
        for field in wrong:
            field_errors[field] += 1
        if wrong:
            bad += 1
        else:
            good += 1

    count = len(labels)
    errors = ", ".join(f"{field}={value}" for field, value in field_errors.items() if value)
    print(f"документов:              {count}")
    print(f"принято верно:           {good}  ({good / count:.1%})")
    print(f"принято с ошибкой:       {bad}")
    print(f"ошибки по полям:         {errors}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
