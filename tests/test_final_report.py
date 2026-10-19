from finance_automation import final_report


def month(name, income, expenses, review):
    return {
        "month": name,
        "rows": 10,
        "income": income,
        "expenses": expenses,
        "net_savings": income + expenses,
        "savings_rate": (income + expenses) / income,
        "reconciled": True,
        "methods": [{"method": "rule", "rows": 7}, {"method": "llm", "rows": 2}, {"method": "internal", "rows": 1}],
        "categories": [
            {"category": "Housing", "rows": 1, "total": -500.0},
            {"category": "Income", "rows": 1, "total": income},
        ],
        "in_review": review,
    }


def test_pdf_is_written(tmp_path):
    pending = [{"description": "PERSON A", "llm_category": "Other", "confidence": 0.4}]
    ev = {
        "golden": 5,
        "accuracy": 0.8,
        "auto_applied": 4,
        "auto_accuracy": 0.75,
        "sent_to_review": 1,
        "errors_caught_by_review": 0,
        "confusion": [{"expected": "Education", "predicted": "Subscriptions", "count": 1}],
    }
    path = final_report.write(
        tmp_path / "r.pdf",
        [month("2026-07", 1000.0, -900.0, pending), month("2026-08", 1000.0, -800.0, [])],
        ev,
        {"new_rows": 0, "duplicates": 10},
    )
    data = path.read_bytes()
    assert data[:4] == b"%PDF" and data.count(b"/Type /Page\n") + data.count(b"/Type /Page ") >= 1
