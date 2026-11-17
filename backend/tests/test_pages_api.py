"""Smoke tests: every page endpoint answers and returns its KPI block. Skipped when the data folder is absent."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if not (ROOT / "data" / "processed" / "fact_sales.csv").exists():
    pytest.skip("data folder not available", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402
from backend.main import app  # noqa: E402

client = TestClient(app)
PAGES = ["executive-overview", "sales-performance", "branches", "products", "customers", "returns",
         "inventory", "procurement", "marketing", "workforce"]


@pytest.mark.parametrize("page", PAGES)
def test_page_endpoint_ok(page):
    r = client.get(f"/api/analytics/{page}")
    assert r.status_code == 200 and r.json()["success"] is True


def test_mom_uses_complete_months():
    p = client.get("/api/analytics/sales-performance").json()["period"]
    if p["partial_month"]:
        assert p["latest_month"] < p["partial_month"]


def test_customer_metrics_exclude_anonymous_orders():
    k = client.get("/api/analytics/customers").json()["kpis"]
    assert k["orders_without_customer_id"] > 0 and k["purchasing_customers"] <= k["customers_total"]
