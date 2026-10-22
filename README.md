# Постобработка OCR паспорта

Нужен Python 3.10 или новее. Дополнительные библиотеки не требуются.

После клонирования репозитория нужно распаковать архив с данными так, чтобы
файлы находились в папке `data`:

```text
data/train_predictions.jsonl
data/train_labels.jsonl
data/test_predictions.jsonl
```

Запуск на test:

```bash
python postprocess.py data/test_predictions.jsonl answers.jsonl
```

Проверка результата на train:

```bash
python postprocess.py data/train_predictions.jsonl train_answers.jsonl
python evaluate.py train_answers.jsonl data/train_labels.jsonl
```

Ожидаемый результат:

```text
документов:              3000
принято верно:           17  (0.6%)
принято с ошибкой:       0
ошибки по полям:
```

Чтобы убедиться, что test-ответ воспроизводится:

```bash
python postprocess.py data/test_predictions.jsonl answers_check.jsonl
cmp answers.jsonl answers_check.jsonl
```

Если `cmp` ничего не напечатал, файлы совпадают. Готовый `answers.jsonl`
содержит 2000 строк: 29 документов принято, 1971 отклонён.

Скрипт работает на CPU и не использует интернет. Справочник подразделений
читается из `reference/subdivisions.csv`.
