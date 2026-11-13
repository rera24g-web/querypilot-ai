"""Generate a sample product-analytics dataset with a planted retention drop:
paid_social users who signed up in Oct 2026 churn much faster than everyone else."""
import random
from datetime import date, datetime, timedelta
from .db import get_engine

DDL = [
    "DROP TABLE IF EXISTS subscriptions", "DROP TABLE IF EXISTS orders",
    "DROP TABLE IF EXISTS events", "DROP TABLE IF EXISTS users",
    "CREATE TABLE users (user_id INTEGER PRIMARY KEY, signup_date DATE, country TEXT, acquisition_channel TEXT)",
    "CREATE TABLE events (event_id INTEGER PRIMARY KEY, user_id INTEGER, event_name TEXT, event_time TIMESTAMP)",
    "CREATE TABLE orders (order_id INTEGER PRIMARY KEY, user_id INTEGER, revenue REAL, order_date DATE)",
    "CREATE TABLE subscriptions (subscription_id INTEGER PRIMARY KEY, user_id INTEGER, plan TEXT, status TEXT)",
]
STAY = {"organic": .93, "paid_search": .91, "referral": .95, "email": .92, "paid_social": .90}
END, START = date(2026, 10, 31), date(2025, 11, 1)


def seed(n_users: int = 3000, rng_seed: int = 7) -> dict:
    rnd = random.Random(rng_seed)
    users, events, orders, subs = [], [], [], []
    for uid in range(1, n_users + 1):
        signup = START + timedelta(days=rnd.randrange((END - START).days))
        ch = rnd.choices(list(STAY), weights=[35, 20, 25, 10, 10])[0]
        country = rnd.choices(["IN", "US", "UK", "DE", "BR"], weights=[40, 25, 15, 10, 10])[0]
        users.append({"user_id": uid, "signup_date": signup.isoformat(), "country": country, "acquisition_channel": ch})
        stay = 0.70 if (ch == "paid_social" and signup >= date(2026, 10, 1)) else STAY[ch]
        week, active = 0, True
        while active and signup + timedelta(days=7 * week) <= END:
            for _ in range(rnd.randint(1, 4)):
                day = signup + timedelta(days=7 * week + rnd.randrange(7))
                if day <= END:
                    events.append({"event_id": len(events) + 1, "user_id": uid,
                                   "event_name": rnd.choice(["app_open", "search", "add_to_cart"]),
                                   "event_time": datetime.combine(day, datetime.min.time()).isoformat(sep=" ")})
            if rnd.random() < 0.12:
                orders.append({"order_id": len(orders) + 1, "user_id": uid,
                               "revenue": round(rnd.lognormvariate(3.6, 0.5), 2),
                               "order_date": (signup + timedelta(days=7 * week)).isoformat()})
            active = rnd.random() < stay
            week += 1
        plan = rnd.choices(["free", "basic", "pro"], weights=[60, 25, 15])[0]
        status = "cancelled" if (not active and plan != "free" and rnd.random() < .7) else "active"
        subs.append({"subscription_id": uid, "user_id": uid, "plan": plan, "status": status})

    engine = get_engine(readonly=False)  # seeding is the only writer
    with engine.begin() as conn:
        for stmt in DDL:
            conn.exec_driver_sql(stmt)
        for table, rows in [("users", users), ("events", events), ("orders", orders), ("subscriptions", subs)]:
            if rows:
                cols = list(rows[0])
                conn.exec_driver_sql(
                    f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})"
                    if engine.dialect.name == "sqlite" else
                    f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('%(' + c + ')s' for c in cols)})",
                    rows if engine.dialect.name != "sqlite" else [tuple(r.values()) for r in rows])
    return {"users": len(users), "events": len(events), "orders": len(orders), "subscriptions": len(subs)}


if __name__ == "__main__":
    print(seed())
