"""Semantic metrics layer: one formal definition per business metric (plan step 3.3).
The agent is told to use these exactly instead of inventing definitions."""

METRICS = {
    "week2_retention": {
        "definition": "Share of users who have at least one event on or after signup_date + 14 days.",
        "population": "Users whose signup_date is at least 14 days before the last event in the data.",
        "window": "Measured per signup cohort; day 14 after signup, UTC dates.",
        "sql": {
            "sqlite": "SELECT u.user_id, CASE WHEN EXISTS (SELECT 1 FROM events e WHERE e.user_id = u.user_id AND e.event_time >= date(u.signup_date, '+14 day')) THEN 1 ELSE 0 END AS retained_w2 FROM users u WHERE u.signup_date <= date((SELECT MAX(event_time) FROM events), '-14 day')",
            "postgres": "SELECT u.user_id, CASE WHEN EXISTS (SELECT 1 FROM events e WHERE e.user_id = u.user_id AND e.event_time >= u.signup_date + 14) THEN 1 ELSE 0 END AS retained_w2 FROM users u WHERE u.signup_date <= (SELECT MAX(event_time) FROM events)::date - 14",
        },
    },
    "conversion_rate": {
        "definition": "Share of users with at least one order.",
        "population": "All users.", "window": "All time unless the question gives a period.",
        "sql": {"any": "SELECT AVG(CASE WHEN EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.user_id) THEN 1.0 ELSE 0.0 END) AS conversion_rate FROM users u"},
    },
    "subscription_churn": {
        "definition": "Share of paid subscriptions (plan other than free) with status 'cancelled'.",
        "population": "Paid subscriptions.", "window": "Current snapshot; the data has no cancellation date.",
        "sql": {"any": "SELECT AVG(CASE WHEN status = 'cancelled' THEN 1.0 ELSE 0.0 END) AS churn_rate FROM subscriptions WHERE plan <> 'free'"},
    },
    "revenue": {
        "definition": "Sum of orders.revenue, attributed to order_date. No refunds in the data.",
        "population": "All orders.", "window": "Filter on order_date for a period.",
        "sql": {"any": "SELECT SUM(revenue) AS revenue FROM orders"},
    },
    "average_order_value": {
        "definition": "Average of orders.revenue per order.",
        "population": "All orders.", "window": "Filter on order_date for a period.",
        "sql": {"any": "SELECT AVG(revenue) AS aov FROM orders"},
    },
}


def metric_sql(name: str, dialect: str) -> str:
    s = METRICS[name]["sql"]
    return s.get(dialect) or s["any"]


def metrics_prompt(dialect: str) -> str:
    lines = ["Business metric definitions. Use these exactly. If the user's term is ambiguous, say which definition you used:"]
    for name, m in METRICS.items():
        lines.append(f"- {name}: {m['definition']} Population: {m['population']} Window: {m['window']} SQL: {metric_sql(name, dialect)}")
    return "\n".join(lines)
