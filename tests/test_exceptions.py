import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.engine.exceptions import ExceptionType, severity_of, classify

class TestClassify:
    def test_duplicate_wins_over_unmatched(self):
        assert classify(is_duplicate=True, candidate_count=0) == ExceptionType.DUPLICATE_TRANSACTION

    def test_unmatched_source(self):
        assert classify(matched=False, candidate_count=0) == ExceptionType.UNMATCHED_SOURCE

    def test_ambiguous_match(self):
        assert classify(matched=False, candidate_count=2) == ExceptionType.AMBIGUOUS_MATCH

    def test_amount_mismatch(self):
        assert classify(matched=True, amount_delta=0.02) == ExceptionType.AMOUNT_MISMATCH

    def test_date_out_of_tolerance(self):
        assert classify(matched=True, date_delta_days=4) == ExceptionType.DATE_OUT_OF_TOLERANCE

    def test_merchant_unresolved(self):
        assert classify(matched=True, merchant_id=None) == ExceptionType.MERCHANT_UNRESOLVED

    def test_clean_match(self):
        assert classify(matched=True, merchant_id="valid") is None

class TestSeverityOf:
    def test_duplicate_severity(self):
        assert severity_of(ExceptionType.DUPLICATE_TRANSACTION) == 5

    def test_amount_mismatch_severity(self):
        assert severity_of(ExceptionType.AMOUNT_MISMATCH) == 4

    def test_unmatched_source_severity(self):
        assert severity_of(ExceptionType.UNMATCHED_SOURCE) == 3

    def test_unmatched_target_severity(self):
        assert severity_of(ExceptionType.UNMATCHED_TARGET) == 3

    def test_ambiguous_match_severity(self):
        assert severity_of(ExceptionType.AMBIGUOUS_MATCH) == 3

    def test_date_out_of_tolerance_severity(self):
        assert severity_of(ExceptionType.DATE_OUT_OF_TOLERANCE) == 2

    def test_split_payment_severity(self):
        assert severity_of(ExceptionType.SPLIT_PAYMENT) == 2

    def test_merchant_unresolved_severity(self):
        assert severity_of(ExceptionType.MERCHANT_UNRESOLVED) == 1

class TestExceptionType:
    def test_amount_mismatch_value(self):
        assert ExceptionType.AMOUNT_MISMATCH.value == "amount_mismatch"
