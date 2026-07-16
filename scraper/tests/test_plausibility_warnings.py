import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from parse_common import plausibility_warnings  # noqa: E402


def main() -> None:
    # normal, in-range values -> no warnings
    assert plausibility_warnings("consumer_debit", [0.20, 0.20, 0.20]) == []
    assert plausibility_warnings("consumer_credit", [0.30, 0.27]) == []

    # the exact anomaly reported from the live run: 0.65% credit, 0.10% debit
    credit_warnings = plausibility_warnings("consumer_credit", [0.30, 0.65, 0.20])
    assert len(credit_warnings) == 1
    assert "0.65" in credit_warnings[0]
    print("consumer_credit warning:", credit_warnings[0])

    debit_warnings = plausibility_warnings("consumer_debit", [0.20, 0.10])
    assert len(debit_warnings) == 1
    assert "0.1" in debit_warnings[0]
    print("consumer_debit warning:", debit_warnings[0])

    # unknown bucket name / empty input -> no crash, no warnings
    assert plausibility_warnings("commercial", [5.0]) == []
    assert plausibility_warnings("consumer_debit", []) == []

    print("\nALL ASSERTIONS PASSED")


if __name__ == "__main__":
    main()
