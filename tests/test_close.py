import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.engine.close import norm_ref, CloseRow, three_way_match


class TestNormRef:
    def test_basic_uppercase(self):
        assert norm_ref("foo") == "FOO"

    def test_strip_whitespace(self):
        assert norm_ref("  foo-bar_123  ") == "FOOBAR123"

    def test_remove_non_alphanumeric(self):
        assert norm_ref("ord-01@test") == "ORD01TEST"

    def test_none_and_blank(self):
        assert norm_ref(None) == ""
        assert norm_ref("") == ""
        assert norm_ref("   ") == ""

    def test_mixed_case_and_punctuation(self):
        assert norm_ref("!ABC-123#") == "ABC123"


class TestThreeWayMatch:
    def test_closed_complete(self):
        ops = [
            {
                "order_ref": "ORD-123",
                "gross_amount": 100,
                "fees": 0,
                "net_amount": 100,
            }
        ]
        erp = [{"order_ref": "ORD-123", "amount": 100, "id": "E1"}]
        bank = [{"reference_raw": "ORD-123", "amount": 100, "id": "B1"}]

        result = three_way_match(ops, erp, bank)

        assert len(result["rows"]) == 1
        row = result["rows"][0]
        assert row.status == "closed"
        assert row.variance == 0.0
        assert result["readiness"] == 1.0

    def test_ops_net_from_gross_fees(self):
        ops = [
            {
                "order_ref": "NEW",
                "gross_amount": 50,
                "fees": 2.5,
                "net_amount": None,
            }
        ]
        erp = [{"order_ref": "NEW", "amount": 47.5, "id": "E1"}]
        bank = [{"reference_raw": "NEW", "amount": 47.5, "id": "B1"}]

        result = three_way_match(ops, erp, bank)
        row = result["rows"][0]
        # 50 - 2.5 = 47.5
        assert row.ops_net == 47.5
        assert row.status == "closed"

    def test_partial_missing_bank(self):
        ops = [{"order_ref": "X", "gross_amount": 100, "fees": 0, "net_amount": 100}]
        erp = [{"order_ref": "X", "amount": 100, "id": "E1"}]
        bank = []

        result = three_way_match(ops, erp, bank)
        assert result["rows"][0].status == "partial"

    def test_partial_missing_erp(self):
        ops = [{"order_ref": "Y", "gross_amount": 100, "fees": 0, "net_amount": 100}]
        erp = []
        bank = [{"reference_raw": "Y", "amount": 100, "id": "B1"}]

        result = three_way_match(ops, erp, bank)
        assert result["rows"][0].status == "partial"

    def test_orphan(self):
        ops = [{"order_ref": "Z", "gross_amount": 10, "fees": 0, "net_amount": 10}]
        erp = []
        bank = []

        result = three_way_match(ops, erp, bank)
        assert result["rows"][0].status == "orphan"

    def test_bank_amount_variance(self):
        ops = [{"order_ref": "V", "gross_amount": 100, "fees": 0, "net_amount": 100}]
        erp = [{"order_ref": "V", "amount": 100, "id": "E1"}]
        # Bank amount differs by 2
        bank = [{"reference_raw": "V", "amount": 102, "id": "B1"}]

        result = three_way_match(ops, erp, bank)
        row = result["rows"][0]
        assert row.bank_amount == 102
        assert row.variance == -2.0
        # Variance is outside tolerance 0.01, so it is partial
        assert row.status == "partial"

    def test_unexplained_bank(self):
        ops = [
            {"order_ref": "ORD-55", "gross_amount": 100, "fees": 0, "net_amount": 100}
        ]
        erp = [{"order_ref": "ORD-55", "amount": 100, "id": "E1"}]
        bank = [
            {"reference_raw": "ORD-55", "amount": 100, "id": "B1"},
            {"reference_raw": "UNEXPLAINED", "amount": 200, "id": "B2"},
        ]

        result = three_way_match(ops, erp, bank)
        # Should contain ID of the bank row not matched by ops
        assert "B2" in result["unexplained_bank"]
        assert "ORD-55" not in result["unexplained_bank"]
        assert len(result["unexplained_bank"]) == 1

    def test_readiness_calculation(self):
        ops = [
            {"order_ref": "C1", "gross_amount": 10, "fees": 0, "net_amount": 10},
            {"order_ref": "C2", "gross_amount": 20, "fees": 0, "net_amount": 20},
            {"order_ref": "P1", "gross_amount": 30, "fees": 0, "net_amount": 30},
        ]
        erp = [{"order_ref": "C1", "amount": 10, "id": "E1"}, {"order_ref": "C2", "amount": 20, "id": "E2"}]
        bank = [
            {"reference_raw": "C1", "amount": 10, "id": "B1"},
            {"reference_raw": "C2", "amount": 20, "id": "B2"},
            {"reference_raw": "P1", "amount": 30, "id": "B3"}, # Matched bank but missing ERP -> Partial
        ]

        result = three_way_match(ops, erp, bank)
        # 2 closed (C1, C2), 1 partial (P1) -> 2/3
        assert result["readiness"] == 0.6667

    def test_empty_input_readiness_zero(self):
        result = three_way_match([], [], [], 0.01)
        assert result["summary"]["total"] == 0
        assert result["readiness"] == 0.0
        assert result["unexplained_bank"] == []

    def test_duplicate_handling_erp_first(self):
        ops = [{"order_ref": "DUPE", "gross_amount": 100, "fees": 0, "net_amount": 100}]
        erp = [{"order_ref": "DUPE", "amount": 100, "id": "E1"}, {"order_ref": "DUPE", "amount": 200, "id": "E2"}]
        bank = [{"reference_raw": "DUPE", "amount": 100, "id": "B1"}]

        result = three_way_match(ops, erp, bank)
        row = result["rows"][0]
        # Should match the first ERP occurrence (100) based on index logic
        assert row.erp_amount == 100
        # Var 100-100=0, closed
        assert row.status == "closed"

    def test_duplicate_handling_bank_first(self):
        ops = [{"order_ref": "DUPE", "gross_amount": 100, "fees": 0, "net_amount": 100}]
        erp = [{"order_ref": "DUPE", "amount": 100, "id": "E1"}]
        bank = [
            {"reference_raw": "DUPE", "amount": 99, "id": "B1"},
            {"reference_raw": "DUPE", "amount": 101, "id": "B2"},
        ]

        result = three_way_match(ops, erp, bank)
        row = result["rows"][0]
        # Should match the first Bank occurrence (99)
        # Variance 100 - 99 = 1.0 > 0.01 -> Partial
        assert row.bank_amount == 99
        assert row.status == "partial"
        assert row.variance == 1.0
