from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    description: str
    customers: int
    accounts_per_customer: int
    transactions_per_account: int
    force_memory_error: bool
    risk_multiplier: float
    average_balance: int


SCENARIOS: dict[str, ScenarioDefinition] = {
    "baseline": ScenarioDefinition(
        name="baseline",
        description="Healthy nightly retail banking pipeline with moderate volume.",
        customers=120,
        accounts_per_customer=2,
        transactions_per_account=12,
        force_memory_error=False,
        risk_multiplier=1.0,
        average_balance=4200,
    ),
    "memory_stress": ScenarioDefinition(
        name="memory_stress",
        description="Large nightly reconciliation batch that overwhelms the transformation worker memory.",
        customers=1200,
        accounts_per_customer=4,
        transactions_per_account=40,
        force_memory_error=True,
        risk_multiplier=1.4,
        average_balance=9600,
    ),
    "fraud_spike": ScenarioDefinition(
        name="fraud_spike",
        description="Suspicious transaction burst for high-risk banking accounts.",
        customers=350,
        accounts_per_customer=3,
        transactions_per_account=28,
        force_memory_error=False,
        risk_multiplier=2.5,
        average_balance=6100,
    ),
}
