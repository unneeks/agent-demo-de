"""The live, pollable multi-agent workflow dashboard's orchestrator.

Unlike `run_cycle()` (one call, one final `CycleReport`), a workflow run has
to be *watched* across many HTTP requests while it progresses -- so this
module is the one place in `orchestrator/` that keeps state across calls,
in a `WorkflowRunner` instance the caller (`webui/`) holds in
`app.state.workflow_runs`.

**Reuses, does not reinvent, the existing multi-turn loop.** In live mode,
each work product is exactly one `agent_runtime.loop.run_agent()` call --
the same function `orchestrator/agent_step.py::run_agents()` already
wraps -- against whichever `AgentLLMClient` backend the caller configured
(`AgentCoreHarnessClient`, `AnthropicAgentClient`, `CopilotCliAgentClient`)
and a real `LocalToolExecutor`. Nothing here talks to a model or a tool
directly.

**Demo mode is a scripted state machine, not a replayed agent run --
a deliberate simplification from the plan this was built against.**
Driving four agents' worth of realistic multi-turn, multi-tool-call
`ReplayAgentClient` fixtures end to end would mean hand-authoring on the
order of thirty scripted conversations for no benefit demo mode actually
needs: demo mode exists to show what the dashboard looks like while
something is running, with zero credentials, not to prove the replay
backend scales to a whole workflow. It progresses each work product
through the same status states a live run would, using the workflow
template's own declared `demo_duration_seconds`/`demo_tokens` (registry
data, not invented Python literals) instead of a real turn count. See
docs/workflow-dashboard.md.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import yaml

from domain.metamodel.base import utc_now
from domain.metamodel.entities.shared.context import ContextPolicy
from domain.metamodel.enums import ApprovalLevel, ContextItemKind, EntityType
from domain.metamodel.registry import MetamodelRegistry

from agent_runtime.approval import ApprovalPolicy, AutomationLevelApprovalPolicy
from agent_runtime.errors import AgentRuntimeError
from agent_runtime.llm import AgentLLMClient
from agent_runtime.loop import run_agent
from agent_runtime.tools import ToolExecutor

WorkProductStatus = Literal["not_started", "in_progress", "awaiting_approval", "completed", "failed"]
AgentSlotStatus = Literal["idle", "running", "waiting_for_approval", "done", "error"]
WorkflowStatus = Literal["running", "completed"]
Mode = Literal["demo", "live"]

#: A small, explicit, overridable $/1K-token table -- an estimate, always
#: labelled as one in the dashboard, same "coarse proxy, honestly labelled"
#: discipline docs/gap-analysis.md already established for maturity
#: inference. Never presented as a real bill.
_DEFAULT_PRICE_PER_1K_TOKENS = 0.006


# -- template shapes, loaded from metamodel-registry/workflow_templates.yaml -----


@dataclass(frozen=True)
class WorkflowWorkProductTemplate:
    key: str
    name: str
    phase_key: str
    task_key: str | None = None
    demo_duration_seconds: float = 30.0
    demo_tokens: int = 10_000


@dataclass(frozen=True)
class WorkflowPhaseTemplate:
    key: str
    name: str


@dataclass(frozen=True)
class WorkflowAgentSlotTemplate:
    key: str
    name: str
    agent_key: str
    mission: str
    context_policy: ContextPolicy
    work_products: tuple[WorkflowWorkProductTemplate, ...]

    @property
    def phase_keys(self) -> tuple[str, ...]:
        seen: list[str] = []
        for wp in self.work_products:
            if wp.phase_key not in seen:
                seen.append(wp.phase_key)
        return tuple(seen)


@dataclass(frozen=True)
class WorkflowTemplate:
    key: str
    name: str
    delivery_model_key: str
    phases: tuple[WorkflowPhaseTemplate, ...]
    agent_slots: tuple[WorkflowAgentSlotTemplate, ...]


class WorkflowTemplateError(AgentRuntimeError):
    """A workflow template references an agent the registry doesn't have,
    or is otherwise malformed."""


def load_workflow_templates(
    registry: MetamodelRegistry, *, path: Path | None = None
) -> dict[str, WorkflowTemplate]:
    """Loads and cross-validates every template against `registry.agents` --
    a template naming an `agent_key` the catalog doesn't have is a real,
    reportable error, not a silent runtime `KeyError` later."""
    source = path or (registry.root / "workflow_templates.yaml")
    raw = yaml.safe_load(source.read_text(encoding="utf-8")) or {}
    templates: dict[str, WorkflowTemplate] = {}
    for entry in raw.get("workflow_templates", []):
        template = _build_template(entry, registry)
        templates[template.key] = template
    return templates


def _build_template(entry: dict[str, Any], registry: MetamodelRegistry) -> WorkflowTemplate:
    phases = tuple(WorkflowPhaseTemplate(key=p["key"], name=p["name"]) for p in entry.get("phases", []))
    phase_keys = {p.key for p in phases}
    slots = tuple(_build_slot(slot_entry, phase_keys, registry) for slot_entry in entry.get("agent_slots", []))
    return WorkflowTemplate(
        key=entry["key"],
        name=entry["name"],
        delivery_model_key=entry["delivery_model_key"],
        phases=phases,
        agent_slots=slots,
    )


def _build_slot(
    entry: dict[str, Any], phase_keys: set[str], registry: MetamodelRegistry
) -> WorkflowAgentSlotTemplate:
    agent_key = entry["agent_key"]
    if agent_key not in registry.agents:
        raise WorkflowTemplateError(f"workflow template agent slot {entry['key']!r} names unknown agent_key {agent_key!r}")
    work_products = tuple(_build_work_product(wp, phase_keys) for wp in entry.get("work_products", []))
    policy = entry["context_policy"]
    context_policy = ContextPolicy(
        id=policy["policy_key"],
        name=policy["policy_key"],
        entity_type=EntityType.CONTEXT_POLICY,
        policy_key=policy["policy_key"],
        max_tokens=policy["max_tokens"],
        allowed_kinds=[ContextItemKind.KNOWLEDGE],
    )
    return WorkflowAgentSlotTemplate(
        key=entry["key"],
        name=entry["name"],
        agent_key=agent_key,
        mission=entry["mission"],
        context_policy=context_policy,
        work_products=work_products,
    )


def _build_work_product(entry: dict[str, Any], phase_keys: set[str]) -> WorkflowWorkProductTemplate:
    phase_key = entry["phase_key"]
    if phase_key not in phase_keys:
        raise WorkflowTemplateError(f"work product {entry['key']!r} names unknown phase_key {phase_key!r}")
    return WorkflowWorkProductTemplate(
        key=entry["key"],
        name=entry["name"],
        phase_key=phase_key,
        task_key=entry.get("task_key"),
        demo_duration_seconds=float(entry.get("demo_duration_seconds", 30.0)),
        demo_tokens=int(entry.get("demo_tokens", 10_000)),
    )


# -- live state, mutated as a run progresses ---------------------------------


@dataclass
class WorkProductState:
    template: WorkflowWorkProductTemplate
    status: WorkProductStatus = "not_started"
    updated_at: datetime | None = None
    tokens: int = 0
    denial_reason: str | None = None


@dataclass
class AgentSlotState:
    template: WorkflowAgentSlotTemplate
    status: AgentSlotStatus = "idle"
    current_activity: str | None = None
    started_at: datetime | None = None
    elapsed_seconds: float = 0.0
    total_tokens: int = 0
    work_products: list[WorkProductState] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class ActivityEvent:
    at: datetime
    agent_key: str
    agent_name: str
    work_product_name: str | None
    message: str


@dataclass(frozen=True)
class WorkflowSnapshot:
    run_id: str
    mode: Mode
    status: WorkflowStatus
    started_at: datetime
    elapsed_seconds: float
    total_tokens: int
    estimated_cost_usd: float
    work_products_done: int
    work_products_total: int
    agents_active: int
    agents_total: int
    phases: list[dict[str, Any]]
    agents: list[dict[str, Any]]
    recent_activity: list[dict[str, Any]]
    human_attention: list[dict[str, Any]]


@dataclass(frozen=True)
class LiveAgentBackend:
    """What `WorkflowRunner` needs to run one agent slot for real: an
    `AgentLLMClient` and a `ToolExecutor`, the automation level, and
    whatever approval a human has granted so far (`NONE` for a fresh run --
    `approve()` rebuilds this with a higher `granted` for a retry).
    Caller-built -- this module never picks a model, a harness ARN or a
    repo path itself."""

    llm_client: AgentLLMClient
    tool_executor: ToolExecutor
    automation_level: Any
    granted: Any = None


class WorkflowRunner:
    """One in-memory, in-process workflow run. Not persisted across a
    process restart -- see docs/workflow-dashboard.md's "what this is not".
    """

    def __init__(
        self,
        *,
        run_id: str,
        template: WorkflowTemplate,
        registry: MetamodelRegistry,
        mode: Mode,
        live_backends: dict[str, LiveAgentBackend] | None = None,
        price_per_1k_tokens: float = _DEFAULT_PRICE_PER_1K_TOKENS,
        now: datetime | None = None,
    ) -> None:
        if mode == "live" and not live_backends:
            raise AgentRuntimeError("live mode requires live_backends for every agent slot")
        self._run_id = run_id
        self._template = template
        self._registry = registry
        self._mode: Mode = mode
        self._live_backends = live_backends or {}
        self._price_per_1k_tokens = price_per_1k_tokens
        self._started_at = now or utc_now()
        self._lock = threading.Lock()
        self._activity: list[ActivityEvent] = []
        self._slots: dict[str, AgentSlotState] = {
            slot.key: AgentSlotState(
                template=slot, work_products=[WorkProductState(template=wp) for wp in slot.work_products]
            )
            for slot in template.agent_slots
        }
        self._threads: list[threading.Thread] = []

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        for slot_key in self._slots:
            thread = threading.Thread(target=self._run_slot, args=(slot_key,), daemon=True)
            self._threads.append(thread)
            thread.start()

    def is_alive(self) -> bool:
        return any(t.is_alive() for t in self._threads)

    # -- the per-slot worker ----------------------------------------------

    def _run_slot(self, slot_key: str) -> None:
        with self._lock:
            slot = self._slots[slot_key]
            slot.status = "running"
            slot.started_at = utc_now()

        for index, wp_state in enumerate(list(self._slots[slot_key].work_products)):
            if not self._run_one_work_product(slot_key, index):
                return  # stopped for approval or failure; slot stays paused here

        with self._lock:
            self._slots[slot_key].status = "done"
            self._slots[slot_key].current_activity = None

    def _run_one_work_product(self, slot_key: str, index: int) -> bool:
        """Returns True to continue to the next work product, False to stop
        this slot's thread (awaiting approval, or failed)."""
        with self._lock:
            slot = self._slots[slot_key]
            wp = slot.work_products[index]
            wp.status = "in_progress"
            wp.updated_at = utc_now()
            slot.current_activity = f"Working on {wp.template.name}"
            self._record(slot, wp.template.name, f"Started {wp.template.name}")

        try:
            if self._mode == "demo":
                elapsed, tokens = self._simulate_demo_work_product(wp.template)
            else:
                elapsed, tokens = self._run_live_work_product(slot.template, wp.template)
        except _ApprovalRequired as denial:
            with self._lock:
                wp.status = "awaiting_approval"
                wp.denial_reason = denial.reason
                slot.status = "waiting_for_approval"
                self._record(slot, wp.template.name, f"Paused: {denial.reason}")
            return False
        except AgentRuntimeError as exc:
            with self._lock:
                wp.status = "failed"
                slot.status = "error"
                slot.error = str(exc)
                self._record(slot, wp.template.name, f"Failed: {exc}")
            return False

        with self._lock:
            wp.status = "completed"
            wp.tokens = tokens
            wp.updated_at = utc_now()
            slot.total_tokens += tokens
            slot.elapsed_seconds += elapsed
            self._record(slot, wp.template.name, f"Completed {wp.template.name}")
        return True

    def _simulate_demo_work_product(self, wp: WorkflowWorkProductTemplate) -> tuple[float, int]:
        # A short, bounded sleep so the dashboard visibly progresses --
        # capped well below the template's own declared duration so a demo
        # run finishes in a reasonable time regardless of what the template
        # says a "real" run would take.
        time.sleep(min(wp.demo_duration_seconds, 3.0) / 10.0)
        return wp.demo_duration_seconds, wp.demo_tokens

    def _run_live_work_product(
        self, slot: WorkflowAgentSlotTemplate, wp: WorkflowWorkProductTemplate
    ) -> tuple[float, int]:
        backend = self._live_backends.get(slot.key)
        if backend is None:
            raise AgentRuntimeError(f"no live backend configured for agent slot {slot.key!r}")
        agent = self._registry.agents[slot.agent_key]
        approval_policy: ApprovalPolicy = AutomationLevelApprovalPolicy(
            automation_level=backend.automation_level, granted=backend.granted or ApprovalLevel.NONE
        )
        task = f"{slot.mission}. Produce the work product: {wp.name}."

        started = time.monotonic()
        report = run_agent(
            agent,
            self._registry,
            task,
            llm_client=backend.llm_client,
            tool_executor=backend.tool_executor,
            context_policy=slot.context_policy,
            approval_policy=approval_policy,
        )
        elapsed = time.monotonic() - started

        for turn in report.turns:
            for record in turn.tool_calls:
                # `not executed` covers both a genuine approval denial and
                # an unresolved (hallucinated) tool name -- `record.error`
                # already says which, so the human deciding whether to
                # "approve and retry" sees the real reason either way.
                if not record.executed:
                    raise _ApprovalRequired(record.error or "approval required")

        tokens = sum(turn.raw.get("usage", {}).get("total_tokens", 0) for turn in report.turns)
        return elapsed, tokens

    def _record(self, slot: AgentSlotState, work_product_name: str | None, message: str) -> None:
        # Caller already holds self._lock.
        self._activity.append(
            ActivityEvent(
                at=utc_now(),
                agent_key=slot.template.agent_key,
                agent_name=slot.template.name,
                work_product_name=work_product_name,
                message=message,
            )
        )

    # -- approve-and-retry, for a work product stuck on an approval gate ----

    def approve(self, slot_key: str, work_product_key: str, *, granted: ApprovalLevel) -> None:
        """Re-runs one denied work product with elevated approval. Not a
        true mid-turn pause/resume of a live model call (nothing in
        `run_agent()` supports that) -- the previous attempt already ended;
        this is a fresh `run_agent()` call for the same work product,
        started at a higher `granted`."""
        with self._lock:
            slot = self._slots[slot_key]
            index = next(i for i, wp in enumerate(slot.work_products) if wp.template.key == work_product_key)
            backend = self._live_backends.get(slot_key)
            if backend is None:
                raise AgentRuntimeError(f"no live backend configured for agent slot {slot_key!r}")

            self._live_backends[slot_key] = LiveAgentBackend(
                llm_client=backend.llm_client,
                tool_executor=backend.tool_executor,
                automation_level=backend.automation_level,
                granted=granted,
            )
            slot.work_products[index].denial_reason = None
            slot.status = "running"

        thread = threading.Thread(target=self._resume_slot, args=(slot_key, index), daemon=True)
        self._threads.append(thread)
        thread.start()

    def _resume_slot(self, slot_key: str, index: int) -> None:
        for i in range(index, len(self._slots[slot_key].work_products)):
            if not self._run_one_work_product(slot_key, i):
                return
        with self._lock:
            self._slots[slot_key].status = "done"
            self._slots[slot_key].current_activity = None

    # -- reading progress -----------------------------------------------

    def snapshot(self) -> WorkflowSnapshot:
        with self._lock:
            now = utc_now()
            agents_payload = []
            all_work_products: list[WorkProductState] = []
            human_attention: list[dict[str, Any]] = []
            total_tokens = 0

            for slot in self._slots.values():
                # slot.elapsed_seconds accumulates only completed work
                # products' real (live) or declared (demo) durations --
                # a slot mid-work-product simply doesn't advance this
                # number until that work product finishes, which is
                # accurate rather than an estimate worth computing.
                total_tokens += slot.total_tokens
                all_work_products.extend(slot.work_products)

                agents_payload.append(
                    {
                        "key": slot.template.key,
                        "name": slot.template.name,
                        "agent_key": slot.template.agent_key,
                        "mission": slot.template.mission,
                        "status": slot.status,
                        "current_activity": slot.current_activity,
                        "elapsed_seconds": round(slot.elapsed_seconds, 1),
                        "total_tokens": slot.total_tokens,
                        "error": slot.error,
                        "work_products": [
                            {
                                "key": wp.template.key,
                                "name": wp.template.name,
                                "status": wp.status,
                                "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
                            }
                            for wp in slot.work_products
                        ],
                    }
                )

                if slot.status == "waiting_for_approval":
                    stuck = next((wp for wp in slot.work_products if wp.status == "awaiting_approval"), None)
                    if stuck is not None:
                        human_attention.append(
                            {
                                "agent_key": slot.template.agent_key,
                                "agent_slot_key": slot.template.key,
                                "work_product_key": stuck.template.key,
                                "work_product_name": stuck.template.name,
                                "reason": stuck.denial_reason,
                                "waiting_since": stuck.updated_at.isoformat() if stuck.updated_at else None,
                            }
                        )

            phases_payload = []
            for phase in self._template.phases:
                phase_wps = [wp for wp in all_work_products if wp.template.phase_key == phase.key]
                done = sum(1 for wp in phase_wps if wp.status == "completed")
                phases_payload.append({"key": phase.key, "name": phase.name, "done": done, "total": len(phase_wps)})

            done_total = sum(1 for wp in all_work_products if wp.status == "completed")
            agents_active = sum(1 for slot in self._slots.values() if slot.status == "running")
            status: WorkflowStatus = "completed" if all(
                slot.status in ("done", "error") for slot in self._slots.values()
            ) else "running"

            return WorkflowSnapshot(
                run_id=self._run_id,
                mode=self._mode,
                status=status,
                started_at=self._started_at,
                elapsed_seconds=round((now - self._started_at).total_seconds(), 1),
                total_tokens=total_tokens,
                estimated_cost_usd=round(total_tokens / 1000 * self._price_per_1k_tokens, 2),
                work_products_done=done_total,
                work_products_total=len(all_work_products),
                agents_active=agents_active,
                agents_total=len(self._slots),
                phases=phases_payload,
                agents=agents_payload,
                recent_activity=[
                    {
                        "at": event.at.isoformat(),
                        "agent_name": event.agent_name,
                        "work_product_name": event.work_product_name,
                        "message": event.message,
                    }
                    for event in reversed(self._activity[-25:])
                ],
                human_attention=human_attention,
            )


class _ApprovalRequired(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def start_workflow_run(
    *,
    run_id: str | None,
    template: WorkflowTemplate,
    registry: MetamodelRegistry,
    mode: Mode,
    live_backends: dict[str, LiveAgentBackend] | None = None,
) -> WorkflowRunner:
    runner = WorkflowRunner(
        run_id=run_id or uuid.uuid4().hex[:12],
        template=template,
        registry=registry,
        mode=mode,
        live_backends=live_backends,
    )
    runner.start()
    return runner


__all__ = [
    "AgentSlotState",
    "LiveAgentBackend",
    "WorkflowAgentSlotTemplate",
    "WorkflowPhaseTemplate",
    "WorkflowRunner",
    "WorkflowSnapshot",
    "WorkflowTemplate",
    "WorkflowTemplateError",
    "WorkflowWorkProductTemplate",
    "load_workflow_templates",
    "start_workflow_run",
]
