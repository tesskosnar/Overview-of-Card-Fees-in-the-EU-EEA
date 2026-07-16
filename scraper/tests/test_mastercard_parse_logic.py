"""
Validates the row-extraction + classification logic against a REAL
sample (Germany, fetched by hand from mastercard.com on 2026-07-14)
without needing network access or a live PDF: this exercises the
text-fallback code path in parse_common, which is also what runs for
any Mastercard page where extract_tables() finds nothing.

Run: python3 tests/test_mastercard_parse_logic.py
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from parse_common import carry_forward_product_prefix, _rows_from_text  # noqa: E402
from parse_mastercard import _classify, PRODUCT_MARKERS  # noqa: E402

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "mastercard_germany_raw.txt"


def main() -> None:
    text = FIXTURE.read_text()

    # simulate a single page (page=0) the way parse_common would tag it
    rows = _rows_from_text(text)
    for r in rows:
        r.page = 0
    rows = carry_forward_product_prefix(rows, PRODUCT_MARKERS)

    consumer_credit, consumer_debit, commercial, unclassified = [], [], [], []
    for row in rows:
        bucket = _classify(row.label)
        target = {
            "consumer_credit": consumer_credit,
            "consumer_debit": consumer_debit,
            "commercial": commercial,
        }.get(bucket, unclassified)
        if bucket == "unclassified":
            target.append((row.label, row.values))
        else:
            target.extend(row.values)

    print(f"rows parsed:        {len(rows)}")
    print(f"consumer_credit:    n={len(consumer_credit)} "
          f"min={min(consumer_credit):.2f} max={max(consumer_credit):.2f}")
    print(f"consumer_debit:     n={len(consumer_debit)} "
          f"min={min(consumer_debit):.2f} max={max(consumer_debit):.2f}")
    print(f"commercial:         n={len(commercial)} "
          f"min={min(commercial):.2f} max={max(commercial):.2f} "
          f"avg={sum(commercial)/len(commercial):.2f}")
    print(f"unclassified rows:  {len(unclassified)}")
    for label, values in unclassified:
        print(f"    ? {label!r} -> {values}")

    # --- assertions against known-correct values for Germany -----------
    assert consumer_credit and set(consumer_credit) == {0.30}, \
        f"expected consumer_credit == [0.30]*n, got {set(consumer_credit)}"
    assert consumer_debit and set(consumer_debit) == {0.20}, \
        f"expected consumer_debit == [0.20]*n, got {set(consumer_debit)}"
    assert commercial and min(commercial) == 0.68 and max(commercial) == 2.40, \
        f"expected commercial range 0.68-2.40, got {min(commercial)}-{max(commercial)}"

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
