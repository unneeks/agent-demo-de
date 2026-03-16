from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from random import Random

from simulator.paths import CURRENT_JOB_METADATA, GENERATED_SEEDS_DIR, RUNTIME_DIR, SCENARIO_STATE
from simulator.scenarios import SCENARIOS, ScenarioDefinition


def _write_csv(path, fieldnames, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _build_customers(scenario: ScenarioDefinition, rng: Random) -> list[dict[str, object]]:
    segments = ["retail", "wealth", "small_business"]
    risk_bands = ["low", "medium", "high"]
    rows = []
    for customer_id in range(1, scenario.customers + 1):
        rows.append(
            {
                "customer_id": customer_id,
                "customer_name": f"Customer {customer_id:04d}",
                "segment": segments[customer_id % len(segments)],
                "risk_band": risk_bands[(customer_id + 1) % len(risk_bands)],
                "kyc_score": round(72 + rng.random() * 25, 2),
            }
        )
    return rows


def _build_accounts(scenario: ScenarioDefinition, rng: Random) -> list[dict[str, object]]:
    rows = []
    account_id = 100000
    products = ["checking", "savings", "loan"]
    for customer_id in range(1, scenario.customers + 1):
        for _ in range(scenario.accounts_per_customer):
            rows.append(
                {
                    "account_id": account_id,
                    "customer_id": customer_id,
                    "product_type": products[account_id % len(products)],
                    "balance": round(max(200, rng.gauss(scenario.average_balance, scenario.average_balance * 0.35)), 2),
                    "status": "active",
                }
            )
            account_id += 1
    return rows


def _build_transactions(scenario: ScenarioDefinition, accounts: list[dict[str, object]], rng: Random) -> list[dict[str, object]]:
    rows = []
    now = datetime(2026, 3, 16, 1, 0, tzinfo=timezone.utc)
    transaction_id = 500000
    for account in accounts:
        for idx in range(scenario.transactions_per_account):
            amount = round(abs(rng.gauss(180 * scenario.risk_multiplier, 90)), 2)
            rows.append(
                {
                    "transaction_id": transaction_id,
                    "account_id": account["account_id"],
                    "txn_ts": (now - timedelta(minutes=idx * 3)).isoformat(),
                    "txn_type": "card" if transaction_id % 2 == 0 else "transfer",
                    "amount": amount,
                    "merchant_category": "travel" if transaction_id % 7 == 0 else "retail",
                    "is_high_risk": "true" if amount > 420 * scenario.risk_multiplier else "false",
                }
            )
            transaction_id += 1
    return rows


def _build_loans(scenario: ScenarioDefinition, rng: Random) -> list[dict[str, object]]:
    rows = []
    loan_id = 900000
    for customer_id in range(1, max(10, scenario.customers // 4) + 1):
        rows.append(
            {
                "loan_id": loan_id,
                "customer_id": customer_id,
                "loan_type": "mortgage" if loan_id % 2 == 0 else "personal",
                "principal_balance": round(abs(rng.gauss(85000, 42000)), 2),
                "days_past_due": int(rng.random() * 12 * scenario.risk_multiplier),
            }
        )
        loan_id += 1
    return rows


def generate_dataset(scenario_name: str) -> dict[str, object]:
    if scenario_name not in SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario_name}'. Available scenarios: {', '.join(sorted(SCENARIOS))}")

    scenario = SCENARIOS[scenario_name]
    rng = Random(f"banking-demo::{scenario.name}")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_SEEDS_DIR.mkdir(parents=True, exist_ok=True)

    customers = _build_customers(scenario, rng)
    accounts = _build_accounts(scenario, rng)
    transactions = _build_transactions(scenario, accounts, rng)
    loans = _build_loans(scenario, rng)

    _write_csv(
        GENERATED_SEEDS_DIR / "bank_customers.csv",
        ["customer_id", "customer_name", "segment", "risk_band", "kyc_score"],
        customers,
    )
    _write_csv(
        GENERATED_SEEDS_DIR / "bank_accounts.csv",
        ["account_id", "customer_id", "product_type", "balance", "status"],
        accounts,
    )
    _write_csv(
        GENERATED_SEEDS_DIR / "bank_transactions.csv",
        ["transaction_id", "account_id", "txn_ts", "txn_type", "amount", "merchant_category", "is_high_risk"],
        transactions,
    )
    _write_csv(
        GENERATED_SEEDS_DIR / "bank_loans.csv",
        ["loan_id", "customer_id", "loan_type", "principal_balance", "days_past_due"],
        loans,
    )

    scenario_payload = {
        "scenario": scenario.name,
        "description": scenario.description,
        "force_memory_error": scenario.force_memory_error,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "row_counts": {
            "customers": len(customers),
            "accounts": len(accounts),
            "transactions": len(transactions),
            "loans": len(loans),
        },
    }
    SCENARIO_STATE.write_text(json.dumps(scenario_payload, indent=2), encoding="utf-8")

    metadata = {
        "job_name": "nightly_bank_customer_360",
        "owner": "banking-data-platform@demo.local",
        "schedule": "*/1 * * * *",
        "domain": "banking",
        "scenario": scenario.name,
        "upstream_dependencies": [
            "seed.bank_customers",
            "seed.bank_accounts",
            "seed.bank_transactions",
            "seed.bank_loans",
        ],
        "downstream_tables": [
            "mart.customer_360",
            "mart.account_activity",
        ],
        "runtime": {
            "executor_memory_gb": 4,
            "retry_policy": "continuous retry on next sensor loop",
            "dbt_project": "dbt_demo",
        },
        "summary": scenario.description,
    }
    CURRENT_JOB_METADATA.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return scenario_payload


def cli() -> None:
    parser = argparse.ArgumentParser(description="Generate banking demo datasets for the dbt pipeline.")
    parser.add_argument("scenario", choices=sorted(SCENARIOS), help="Dataset scenario to generate.")
    args = parser.parse_args()
    payload = generate_dataset(args.scenario)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    cli()
