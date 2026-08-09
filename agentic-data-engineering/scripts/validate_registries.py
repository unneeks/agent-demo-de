#!/usr/bin/env python3
"""Validate the YAML registries and report what was loaded.

The registries are data, edited by people who may never run the test suite.
This is the CI entry point that stops a malformed or internally inconsistent
registry -- including a whole delivery model -- from being merged.

Usage:
    python scripts/validate_registries.py
    python scripts/validate_registries.py --quiet     # exit code only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from domain.metamodel.enums import ActionClass, AutomationLevel  # noqa: E402
from domain.metamodel.registry import MetamodelRegistry, RegistryError  # noqa: E402
from engines.composition import resolve_catalog  # noqa: E402
from engines.gates import machine_evaluable_share  # noqa: E402


def main() -> int:  # noqa: C901
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-path", default=None, help="Override the registry directory.")
    parser.add_argument("--quiet", action="store_true", help="Suppress the summary.")
    args = parser.parse_args()

    try:
        registry = MetamodelRegistry.load(args.registry_path)
    except RegistryError as exc:
        print(f"registry validation FAILED\n\n{exc}", file=sys.stderr)
        return 1

    if args.quiet:
        return 0

    print(f"registry OK (metamodel {registry.declared_version})")
    print(f"  technical capabilities  {len(registry.capabilities)}")
    print(f"  delivery capabilities   {len(registry.delivery_capabilities)}")
    print(f"  responsibilities        {len(registry.responsibilities)}")
    print(f"  engineering roles       {len(registry.engineering_roles)}")
    print(f"  delivery roles          {len(registry.delivery_roles)}")
    print(f"  skills                  {len(registry.skills)}")
    print(f"  tools                   {len(registry.tools)}")
    print(f"  knowledge packs         {len(registry.knowledge_packs)}")
    print(f"  agents                  {len(registry.agents)}")
    print(f"  evaluation metrics      {len(registry.evaluation_metrics)}")
    print(f"  evaluation scenarios    {len(registry.evaluation_scenarios)}")
    print(f"  evaluation suites       {len(registry.evaluation_suites)}")
    print(f"  relationship types      {len(registry.relationship_types)}")
    print(f"  platforms               {len(registry.platforms)}")
    print(f"  technology bindings     {len(registry.technology_bindings)}")

    cross = [s for s in registry.relationship_types.values() if s.is_cross_twin]
    print(f"  cross-twin edge types   {len(cross)}")

    print("\nmarketplace resolution:")
    for role_key, resolution in sorted(resolve_catalog(registry).items()):
        marker = "staffable" if resolution.is_staffable else "unstaffed"
        print(
            f"  {role_key:28} {len(resolution.matches)} match(es), "
            f"{len(resolution.near_misses)} near-miss(es) -- {marker}"
        )

    print("\napproval matrix:")
    header = "  " + "".ljust(24) + "".join(a.value.ljust(18) for a in ActionClass)
    print(header)
    for level in AutomationLevel:
        row = "  " + level.value.ljust(24)
        row += "".join(
            registry.required_approval(action, level).value.ljust(18) for action in ActionClass
        )
        print(row)

    mismatches = []
    for example in registry.risk_examples:
        actual = registry.required_approval(
            ActionClass(example["action_class"]), AutomationLevel.ASSISTED
        )
        if actual.value != example["expected_approval"]:
            mismatches.append(
                f"{example['action']}: expected {example['expected_approval']}, got {actual.value}"
            )
    if mismatches:
        print("\nrisk.yaml examples disagree with the approval matrix:", file=sys.stderr)
        for mismatch in mismatches:
            print(f"  - {mismatch}", file=sys.stderr)
        return 1
    print(f"\n{len(registry.risk_examples)} worked risk examples agree with the matrix")

    for key, loaded in registry.delivery_models.items():
        print(f"\ndelivery model: {loaded.model.name} ({key})")
        print(f"  phases      {len(loaded.phases)}")
        print(f"  tasks       {len(loaded.tasks)}")
        print(f"  contracts   {len(loaded.contracts)}")
        print(f"  checklists  {len(loaded.checklists)} ({len(loaded.checklist_items)} items)")
        print(f"  criteria    {len(loaded.criteria)}")
        print(f"  gates       {len(loaded.gates)}")
        print(f"  evidence    {len(loaded.evidence_requirements)}")

        print("  phase order:")
        for phase in loaded.phases_in_order():
            depends = (
                f" after {', '.join(phase.depends_on_phase_keys)}"
                if phase.depends_on_phase_keys
                else ""
            )
            print(f"    {phase.sequence}. {phase.name}{depends}")

        # How much of this model an agent could actually discharge unattended.
        # A model that is mostly human review is not a candidate for automation
        # however good the agents are, and saying so is more useful than
        # discovering it during composition.
        print("  automatability by checklist:")
        for checklist_key in sorted(loaded.checklists):
            items = loaded.items_for(checklist_key)
            share = machine_evaluable_share(items)
            print(f"    {checklist_key:28} {share:>5.0%} machine-evaluable ({len(items)} items)")

        blocking_inferred = [
            item.item_key
            for item in loaded.checklist_items.values()
            if item.blocking and not item.is_factual
        ]
        if blocking_inferred:
            print(
                f"    WARNING: {len(blocking_inferred)} blocking item(s) rest on inferred "
                "provenance",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
