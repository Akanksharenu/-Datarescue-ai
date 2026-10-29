from app.services import synthetic


def test_same_seed_same_data():
    a = synthetic.generate_transactions(seed=42)
    b = synthetic.generate_transactions(seed=42)
    assert a == b
    assert len(a) == 1000
    assert a[0]["source_id"] == "TX000001"


def test_different_seed_different_amounts():
    a = synthetic.generate_transactions(seed=42)
    b = synthetic.generate_transactions(seed=43)
    assert [r["source_id"] for r in a] == [r["source_id"] for r in b]  # IDs stay stable
    assert [r["amount_cents"] for r in a] != [r["amount_cents"] for r in b]


def test_all_rows_inside_business_day():
    rows = synthetic.generate_transactions()
    assert {r["occurred_at"].date() for r in rows} == {synthetic.BUSINESS_DATE}


def test_rename_field_replaces_key():
    renamed = synthetic.rename_field(synthetic.generate_transactions())
    assert all("amount" in r and "amount_cents" not in r for r in renamed)


def test_pick_ids_is_deterministic_and_unique():
    rows = synthetic.generate_transactions()
    assert synthetic.pick_ids(rows, 280, 43) == synthetic.pick_ids(rows, 280, 43)
    assert len(set(synthetic.pick_ids(rows, 280, 43))) == 280
