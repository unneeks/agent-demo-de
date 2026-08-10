"""Checklist evaluation.

Turns a set of per-item results into a checklist outcome, applying the
completion rule the checklist declares. Pure and deterministic -- no I/O, no
model call.

Two rules that look small and are not:

* **A waiver must be attributed.** ``ChecklistItemResult`` already refuses a
  WAIVED status with no waiver; here an *expired* waiver stops counting, so a
  temporary exception cannot quietly become permanent.
* **NOT_APPLICABLE is excluded from the denominator, WAIVED is not.** A control
  that never applied should not depress the score; a control that applied and
  was waived should be visible in it. Treating them the same is how a process
  ends up with a 100% completion rate and no assurance.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from domain.metamodel.base import EntityRef, MetamodelModel, utc_now
from domain.metamodel.entities.delivery import Checklist, ChecklistItem, ChecklistItemResult
from domain.metamodel.enums import ChecklistItemStatus, CompletionRule


class ItemOutcome(MetamodelModel):
    """The resolved state of one item after evaluation."""

    item_key: str
    status: ChecklistItemStatus
    mandatory: bool
    blocking: bool
    counts_as_satisfied: bool
    detail: str | None = None


class ChecklistOutcome(MetamodelModel):
    """The result of evaluating one checklist on one occasion."""

    checklist_key: str
    complete: bool
    completion: float = Field(ge=0.0, le=1.0)
    rule: CompletionRule
    items: list[ItemOutcome] = Field(default_factory=list)
    #: Mandatory items that are not satisfied. These are what blocks a gate.
    outstanding: list[str] = Field(default_factory=list)
    waived: list[str] = Field(default_factory=list)
    not_applicable: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=utc_now)

    @property
    def has_blocking_failures(self) -> bool:
        return any(
            item.blocking and not item.counts_as_satisfied for item in self.items
        )

    def summary(self) -> str:
        return (
            f"{self.checklist_key}: {self.completion:.0%} "
            f"({'complete' if self.complete else 'incomplete'})"
            + (f", {len(self.outstanding)} outstanding" if self.outstanding else "")
            + (f", {len(self.waived)} waived" if self.waived else "")
        )


def evaluate_checklist(
    checklist: Checklist,
    items: list[ChecklistItem],
    results: list[ChecklistItemResult],
    *,
    now: datetime | None = None,
) -> ChecklistOutcome:
    """Evaluate a checklist against the results recorded for its items.

    Items with no recorded result are treated as ``PENDING`` -- unevaluated is
    not the same as passed, and defaulting the other way is how checklists stop
    meaning anything.
    """
    reference = now or utc_now()
    by_key = {r.item_key: r for r in results}

    outcomes: list[ItemOutcome] = []
    for item in sorted(items, key=lambda i: i.sequence):
        result = by_key.get(item.item_key)
        status = result.status if result else ChecklistItemStatus.PENDING
        detail = None

        satisfied = status is ChecklistItemStatus.PASS

        if status is ChecklistItemStatus.WAIVED and result is not None:
            waiver = result.waiver
            if waiver is not None and waiver.expires_at and waiver.expires_at < reference:
                # An expired waiver is no waiver. Without this a temporary
                # exception silently becomes a permanent one.
                satisfied = False
                detail = f"waiver expired {waiver.expires_at.date()}"
            else:
                satisfied = True
                detail = f"waived by {waiver.approver}" if waiver else None

        if status is ChecklistItemStatus.NOT_APPLICABLE:
            satisfied = True
            detail = "not applicable"

        if item.evidence_required and satisfied and status is ChecklistItemStatus.PASS:
            if result is None or not result.evidence_refs:
                satisfied = False
                detail = "passed but produced no evidence, which the item requires"

        outcomes.append(
            ItemOutcome(
                item_key=item.item_key,
                status=status,
                mandatory=item.mandatory,
                blocking=item.blocking,
                counts_as_satisfied=satisfied,
                detail=detail,
            )
        )

    # NOT_APPLICABLE items leave the denominator; waived ones stay in it.
    scoreable = [o for o in outcomes if o.status is not ChecklistItemStatus.NOT_APPLICABLE]
    satisfied_count = sum(1 for o in scoreable if o.counts_as_satisfied)
    completion = satisfied_count / len(scoreable) if scoreable else 1.0

    outstanding = [o.item_key for o in outcomes if o.mandatory and not o.counts_as_satisfied]

    if checklist.completion_rule is CompletionRule.ALL:
        complete = all(o.counts_as_satisfied for o in outcomes)
    elif checklist.completion_rule is CompletionRule.ALL_MANDATORY:
        complete = not outstanding
    else:  # PERCENTAGE
        threshold = checklist.completion_threshold or 1.0
        # A percentage rule still cannot excuse an unmet mandatory item;
        # otherwise "90% complete" could mean every optional item passed and
        # every mandatory one failed.
        complete = completion >= threshold and not outstanding

    return ChecklistOutcome(
        checklist_key=checklist.checklist_key,
        complete=complete,
        completion=completion,
        rule=checklist.completion_rule,
        items=outcomes,
        outstanding=outstanding,
        waived=[o.item_key for o in outcomes if o.status is ChecklistItemStatus.WAIVED],
        not_applicable=[
            o.item_key for o in outcomes if o.status is ChecklistItemStatus.NOT_APPLICABLE
        ],
        evaluated_at=reference,
    )


def machine_evaluable_share(items: list[ChecklistItem]) -> float:
    """Fraction of items an agent could discharge without a human.

    Used when composing: a checklist that is 10% machine-evaluable is not a
    candidate for automation however capable the agent, and saying so up front
    is more useful than discovering it at run time.
    """
    if not items:
        return 0.0
    return sum(1 for i in items if i.is_machine_evaluable) / len(items)


def unevaluated_items(
    items: list[ChecklistItem], results: list[ChecklistItemResult]
) -> list[EntityRef]:
    """Items with no recorded result, as refs -- for reporting what is missing."""
    from domain.metamodel.enums import EntityType

    evaluated = {r.item_key for r in results}
    return [
        EntityRef(type=EntityType.CHECKLIST_ITEM, id=i.item_key)
        for i in items
        if i.item_key not in evaluated
    ]
