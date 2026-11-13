import pytest
from app.db import run_readonly
from app.metrics import METRICS, metric_sql
from app.seed import seed


@pytest.fixture(scope="module", autouse=True)
def data():
    seed(n_users=3000)


def test_every_metric_sql_runs():
    for name in METRICS:
        assert run_readonly(metric_sql(name, "sqlite"))["row_count"] >= 1, name


def test_planted_retention_drop_is_detectable():
    q = (f"WITH r AS ({metric_sql('week2_retention', 'sqlite')}) SELECT u.acquisition_channel, "
         "CASE WHEN u.signup_date >= '2026-10-01' THEN 'oct' ELSE 'earlier' END AS cohort, AVG(r.retained_w2) "
         "FROM r JOIN users u ON u.user_id = r.user_id GROUP BY 1, 2")
    got = {(a, b): v for a, b, v in run_readonly(q)["rows"]}
    assert got[("paid_social", "oct")] < got[("paid_social", "earlier")] - 0.15
