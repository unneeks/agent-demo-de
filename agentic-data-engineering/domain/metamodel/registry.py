"""Loading and cross-validating the YAML registries.

The registries are the half of the metamodel that evolves without a code change:
capability catalogs, the four-level role chain, the relationship vocabulary,
platform bindings, and whole delivery models.

The cross-validation is the point. A role demanding a capability nobody defined,
a delivery task pointing at a checklist that does not exist, a phase graph with
a cycle, or two roles both accountable for the same task -- these are errors
that otherwise surface much later as an empty query result or an unsatisfiable
process. Here they fail at load, all of them reported at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from domain.metamodel.base import EntityRef
from domain.metamodel.entities.delivery import (
    AcceptanceCriterion,
    ApprovalGate,
    Checklist,
    ChecklistItem,
    Control,
    DeliveryContract,
    DeliveryInput,
    DeliveryModel,
    DeliveryOutput,
    DeliveryPhase,
    DeliveryTask,
    EvidenceRequirement,
    Methodology,
    RaciAssignment,
    Standard,
    Template,
)
from domain.metamodel.entities.evaluation import EvaluationMetric, EvaluationScenario, EvaluationSuite
from domain.metamodel.entities.organization import (
    Agent,
    DeliveryCapabilityDeclaration,
    DeliveryRole,
    EngineeringResponsibility,
    EngineeringRole,
    KnowledgePack,
    Skill,
    Tool,
    ToolAction,
)
from domain.metamodel.entities.shared import Platform, TechnologyBinding
from domain.metamodel.enums import (
    ActionClass,
    ApprovalLevel,
    AutomationLevel,
    CompletionRule,
    EntityType,
    ProvenanceState,
    RaciLetter,
)
from domain.metamodel.relationships import RelationshipTypeSpec
from domain.metamodel.version import METAMODEL_VERSION

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "metamodel-registry"

#: Registry-supplied delivery models are hand-written and reviewed, so they load
#: as HUMAN_VERIFIED -- which is what permits their gates to block. A model
#: produced by the assimilation engine would load as INFERRED and its gates
#: would be advisory until a human verified them. See ADR-0009.
_REGISTRY_PROVENANCE: dict[str, Any] = {
    "provenance": ProvenanceState.HUMAN_VERIFIED,
    "human_verified_by": "metamodel-registry",
}


class RegistryError(Exception):
    """A registry file is malformed, or the registries contradict each other."""


@dataclass(frozen=True)
class CapabilitySpec:
    """One entry in a capability catalog (technical or delivery)."""

    key: str
    name: str
    category: str | None = None
    description: str | None = None
    detection_hints: tuple[str, ...] = ()
    #: Delivery capabilities only: what must exist in the model to credit it.
    evidenced_by: tuple[str, ...] = ()
    realized_by_roles: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProvenanceRule:
    """What a provenance state requires and permits."""

    key: ProvenanceState
    name: str
    rank: int
    description: str = ""
    requires_confidence: bool = False
    requires_discoverer: bool = False
    requires_human: bool = False
    may_drive_automated_action: bool = False
    may_be_cited_as_fact: bool = False
    may_block: bool = False


@dataclass
class LoadedDeliveryModel:
    """One fully constructed delivery model and everything it references."""

    model: DeliveryModel
    methodology: Methodology | None = None
    phases: dict[str, DeliveryPhase] = field(default_factory=dict)
    tasks: dict[str, DeliveryTask] = field(default_factory=dict)
    inputs: dict[str, DeliveryInput] = field(default_factory=dict)
    outputs: dict[str, DeliveryOutput] = field(default_factory=dict)
    checklists: dict[str, Checklist] = field(default_factory=dict)
    checklist_items: dict[str, ChecklistItem] = field(default_factory=dict)
    criteria: dict[str, AcceptanceCriterion] = field(default_factory=dict)
    gates: dict[str, ApprovalGate] = field(default_factory=dict)
    evidence_requirements: dict[str, EvidenceRequirement] = field(default_factory=dict)
    standards: dict[str, Standard] = field(default_factory=dict)
    templates: dict[str, Template] = field(default_factory=dict)
    controls: dict[str, Control] = field(default_factory=dict)
    raci: list[RaciAssignment] = field(default_factory=list)
    contracts: dict[str, DeliveryContract] = field(default_factory=dict)

    def items_for(self, checklist_key: str) -> list[ChecklistItem]:
        """Items belonging to one checklist, in declared order."""
        return sorted(
            (i for i in self.checklist_items.values() if i.checklist_key == checklist_key),
            key=lambda i: i.sequence,
        )

    def contract_for(self, task_key: str) -> DeliveryContract | None:
        return next((c for c in self.contracts.values() if c.task_key == task_key), None)

    def phases_in_order(self) -> list[DeliveryPhase]:
        return sorted(self.phases.values(), key=lambda p: p.sequence)


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RegistryError(f"registry file not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RegistryError(f"{path.name} is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise RegistryError(f"{path.name} must contain a mapping at the top level")
    return loaded


@dataclass
class MetamodelRegistry:
    """The loaded, cross-validated registries.

    Construct with :meth:`load`. ``validate()`` runs automatically and raises
    :class:`RegistryError` listing *every* problem found rather than stopping at
    the first -- fixing registry data one error per run is miserable.
    """

    root: Path
    declared_version: str
    capabilities: dict[str, CapabilitySpec] = field(default_factory=dict)
    delivery_capabilities: dict[str, CapabilitySpec] = field(default_factory=dict)
    responsibilities: dict[str, EngineeringResponsibility] = field(default_factory=dict)
    engineering_roles: dict[str, EngineeringRole] = field(default_factory=dict)
    delivery_roles: dict[str, DeliveryRole] = field(default_factory=dict)
    skills: dict[str, Skill] = field(default_factory=dict)
    tools: dict[str, Tool] = field(default_factory=dict)
    knowledge_packs: dict[str, KnowledgePack] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    evaluation_metrics: dict[str, EvaluationMetric] = field(default_factory=dict)
    evaluation_scenarios: dict[str, EvaluationScenario] = field(default_factory=dict)
    evaluation_suites: dict[str, EvaluationSuite] = field(default_factory=dict)
    relationship_types: dict[str, RelationshipTypeSpec] = field(default_factory=dict)
    platforms: dict[str, Platform] = field(default_factory=dict)
    technology_bindings: list[TechnologyBinding] = field(default_factory=list)
    provenance_rules: dict[ProvenanceState, ProvenanceRule] = field(default_factory=dict)
    approval_matrix: dict[AutomationLevel, dict[ActionClass, ApprovalLevel]] = field(
        default_factory=dict
    )
    risk_examples: list[dict[str, str]] = field(default_factory=list)
    delivery_process_kinds: dict[str, str] = field(default_factory=dict)
    delivery_models: dict[str, LoadedDeliveryModel] = field(default_factory=dict)

    # -- loading ----------------------------------------------------------

    @classmethod
    def load(cls, root: Path | str | None = None, *, validate: bool = True) -> MetamodelRegistry:
        base = Path(root) if root else DEFAULT_REGISTRY_PATH
        registry = cls(
            root=base,
            declared_version=str(_read_yaml(base / "metamodel.version.yaml").get("version", "")),
        )
        registry._load_capabilities(base / "capabilities.yaml")
        registry._load_delivery_capabilities(base / "delivery_capabilities.yaml")
        registry._load_relationship_types(base / "relationship_types.yaml")
        registry._load_responsibilities(base / "engineering_responsibilities.yaml")
        registry._load_engineering_roles(base / "engineering_roles.yaml")
        registry._load_delivery_roles(base / "delivery_roles.yaml")
        registry._load_skills(base / "skills.yaml")
        registry._load_tools(base / "tools.yaml")
        registry._load_knowledge_packs(base / "knowledge_packs.yaml")
        registry._load_agents(base / "agents.yaml")
        registry._load_evaluation_metrics(base / "evaluation_metrics.yaml")
        registry._load_evaluation_scenarios(base / "evaluation_scenarios.yaml")
        registry._load_evaluation_suites(base / "evaluation_suites.yaml")
        registry._load_platforms(base / "platforms.yaml")
        registry._load_provenance(base / "provenance.yaml")
        registry._load_risk(base / "risk.yaml")

        models_dir = base / "delivery-models"
        if models_dir.is_dir():
            for path in sorted(models_dir.glob("*.yaml")):
                loaded = registry._load_delivery_model(path)
                registry.delivery_models[loaded.model.model_key] = loaded

        if validate:
            registry.validate()
        return registry

    def _load_capabilities(self, path: Path) -> None:
        for entry in _read_yaml(path).get("capabilities", []):
            spec = CapabilitySpec(
                key=entry["key"],
                name=entry.get("name", entry["key"]),
                category=entry.get("category"),
                description=entry.get("description"),
                detection_hints=tuple(entry.get("detection_hints", [])),
            )
            if spec.key in self.capabilities:
                raise RegistryError(f"duplicate capability key {spec.key!r} in {path.name}")
            self.capabilities[spec.key] = spec

    def _load_delivery_capabilities(self, path: Path) -> None:
        for entry in _read_yaml(path).get("delivery_capabilities", []):
            spec = CapabilitySpec(
                key=entry["key"],
                name=entry.get("name", entry["key"]),
                category=entry.get("category"),
                description=entry.get("description"),
                evidenced_by=tuple(entry.get("evidenced_by", [])),
                realized_by_roles=tuple(entry.get("realized_by_roles", [])),
            )
            if spec.key in self.delivery_capabilities:
                raise RegistryError(
                    f"duplicate delivery capability key {spec.key!r} in {path.name}"
                )
            self.delivery_capabilities[spec.key] = spec

    def _load_relationship_types(self, path: Path) -> None:
        for entry in _read_yaml(path).get("relationship_types", []):
            try:
                spec = RelationshipTypeSpec(**entry)
            except ValidationError as exc:
                raise RegistryError(
                    f"{path.name}: relationship type {entry.get('key')!r} is invalid: {exc}"
                ) from exc
            if spec.key in self.relationship_types:
                raise RegistryError(f"duplicate relationship type {spec.key!r} in {path.name}")
            self.relationship_types[spec.key] = spec

    def _load_responsibilities(self, path: Path) -> None:
        for entry in _read_yaml(path).get("engineering_responsibilities", []):
            key = entry["key"]
            self.responsibilities[key] = EngineeringResponsibility(
                id=key,
                name=entry.get("name", key),
                entity_type=EntityType.ENGINEERING_RESPONSIBILITY,
                responsibility_key=key,
                statement=entry.get("statement", key),
                required_capability_keys=entry.get("required_capabilities", []),
                required_delivery_capability_keys=entry.get("required_delivery_capabilities", []),
                fulfilled_by_role_keys=entry.get("fulfilled_by_roles", []),
                risk_level=entry.get("risk_level", "MEDIUM"),
                delegable_to_agent=entry.get("delegable_to_agent", True),
            )

    def _load_engineering_roles(self, path: Path) -> None:
        for entry in _read_yaml(path).get("engineering_roles", []):
            key = entry["key"]
            try:
                self.engineering_roles[key] = EngineeringRole(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.ENGINEERING_ROLE,
                    role_key=key,
                    mission=entry.get("mission", key),
                    responsibilities=entry.get("responsibilities", []),
                    required_capabilities=entry.get("required_capabilities", []),
                    required_delivery_capabilities=entry.get("required_delivery_capabilities", []),
                    required_skills=entry.get("required_skills", []),
                    required_knowledge=entry.get("required_knowledge", []),
                    required_tools=entry.get("required_tools", []),
                    kpis=entry.get("kpis", []),
                    evaluation_criteria=entry.get("evaluation_criteria", []),
                    minimum_evaluation_score=entry.get("minimum_evaluation_score", 0.8),
                    minimum_delivery_conformance=entry.get("minimum_delivery_conformance", 0.9),
                    risk_level=entry.get("risk_level", "MEDIUM"),
                    automation_level=entry.get("automation_level", "ASSISTED"),
                    default_approval_level=entry.get("default_approval_level", "SINGLE_REVIEWER"),
                )
            except ValidationError as exc:
                raise RegistryError(f"{path.name}: role {key!r} is invalid: {exc}") from exc

    def _load_delivery_roles(self, path: Path) -> None:
        for entry in _read_yaml(path).get("delivery_roles", []):
            key = entry["key"]
            self.delivery_roles[key] = DeliveryRole(
                id=key,
                name=entry.get("name", key),
                entity_type=EntityType.DELIVERY_ROLE,
                role_key=key,
                responsibility_keys=entry.get("responsibilities", []),
                approves_gate_keys=entry.get("approves_gates", []),
                accountable_for_task_keys=entry.get("accountable_for_tasks", []),
                is_segregated=entry.get("is_segregated", False),
                incompatible_with=entry.get("incompatible_with", []),
                **_REGISTRY_PROVENANCE,
            )

    def _load_skills(self, path: Path) -> None:
        for entry in _read_yaml(path).get("skills", []):
            key = entry["key"]
            try:
                self.skills[key] = Skill(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.SKILL,
                    skill_key=key,
                    inputs=entry.get("inputs", {}),
                    outputs=entry.get("outputs", {}),
                    preconditions=entry.get("preconditions", []),
                    postconditions=entry.get("postconditions", []),
                    dependencies=entry.get("dependencies", []),
                    required_tools=entry.get("required_tools", []),
                    required_knowledge=entry.get("required_knowledge", []),
                    risk_level=entry.get("risk_level", "LOW"),
                    deterministic=entry.get("deterministic", False),
                    idempotent=entry.get("idempotent", True),
                    timeout_seconds=entry.get("timeout_seconds", 300),
                    discharges_checklist_items=entry.get("discharges_checklist_items", []),
                )
            except ValidationError as exc:
                raise RegistryError(f"{path.name}: skill {key!r} is invalid: {exc}") from exc

    def _load_tools(self, path: Path) -> None:
        for entry in _read_yaml(path).get("tools", []):
            key = entry["key"]
            try:
                actions = [ToolAction(**action) for action in entry.get("actions", [])]
                self.tools[key] = Tool(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.TOOL,
                    tool_key=key,
                    provider=entry.get("provider"),
                    category=entry.get("category"),
                    platform_key=entry.get("platform_key"),
                    actions=actions,
                    authentication=entry.get("authentication"),
                    required_permissions=entry.get("required_permissions", []),
                    cost_profile=entry.get("cost_profile"),
                    rate_limits=entry.get("rate_limits", {}),
                    security_constraints=entry.get("security_constraints", []),
                    auditable=entry.get("auditable", True),
                )
            except ValidationError as exc:
                raise RegistryError(f"{path.name}: tool {key!r} is invalid: {exc}") from exc

    def _load_knowledge_packs(self, path: Path) -> None:
        for entry in _read_yaml(path).get("knowledge_packs", []):
            key = entry["key"]
            try:
                self.knowledge_packs[key] = KnowledgePack(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.KNOWLEDGE_PACK,
                    knowledge_key=key,
                    scope=entry.get("scope"),
                    source=entry.get("source"),
                    content_reference=entry["content_reference"],
                    authority=entry.get("authority"),
                    trust_level=entry.get("trust_level", "MEDIUM"),
                    freshness_days=entry.get("freshness_days"),
                    index_reference=entry.get("index_reference"),
                    knowledge_kind=entry.get("knowledge_kind", "reference"),
                )
            except ValidationError as exc:
                raise RegistryError(
                    f"{path.name}: knowledge pack {key!r} is invalid: {exc}"
                ) from exc

    def _load_agents(self, path: Path) -> None:
        for entry in _read_yaml(path).get("agents", []):
            key = entry["key"]
            delivery = entry.get("delivery", {})
            try:
                self.agents[key] = Agent(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.AGENT,
                    agent_key=key,
                    role_key=entry["role_key"],
                    mission=entry.get("mission"),
                    capabilities=entry.get("capabilities", []),
                    delivery_capabilities=entry.get("delivery_capabilities", []),
                    skills=entry.get("skills", []),
                    tools=entry.get("tools", []),
                    knowledge_packs=entry.get("knowledge_packs", []),
                    policies=entry.get("policies", []),
                    delivery=DeliveryCapabilityDeclaration(
                        supported_phase_keys=delivery.get("supported_phases", []),
                        supported_task_keys=delivery.get("supported_tasks", []),
                        supported_checklist_keys=delivery.get("supported_checklists", []),
                        supported_artifact_kinds=delivery.get("supported_artifact_kinds", []),
                        supported_gate_keys=delivery.get("supported_gates", []),
                        produces_evidence_keys=delivery.get("produces_evidence", []),
                    ),
                    execution_model=entry.get("execution_model", "PLANNER_EXECUTOR"),
                    model_provider=entry.get("model_provider"),
                    model_name=entry.get("model_name"),
                    external_provider=entry.get("external_provider"),
                    status=entry.get("status", "DRAFT"),
                )
            except ValidationError as exc:
                raise RegistryError(f"{path.name}: agent {key!r} is invalid: {exc}") from exc

    def _load_evaluation_metrics(self, path: Path) -> None:
        for entry in _read_yaml(path).get("evaluation_metrics", []):
            key = entry["key"]
            try:
                self.evaluation_metrics[key] = EvaluationMetric(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.EVALUATION_METRIC,
                    metric_key=key,
                    dimension=entry.get("dimension", "technical"),
                    threshold=entry["threshold"],
                    higher_is_better=entry.get("higher_is_better", True),
                    weight=entry.get("weight", 1.0),
                    unit=entry.get("unit"),
                    blocking=entry.get("blocking", True),
                )
            except ValidationError as exc:
                raise RegistryError(
                    f"{path.name}: evaluation metric {key!r} is invalid: {exc}"
                ) from exc

    def _load_evaluation_scenarios(self, path: Path) -> None:
        for entry in _read_yaml(path).get("evaluation_scenarios", []):
            key = entry["key"]
            try:
                self.evaluation_scenarios[key] = EvaluationScenario(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.EVALUATION_SCENARIO,
                    scenario_key=key,
                    inputs=entry.get("inputs", {}),
                    expected_behavior=entry.get("expected_behavior"),
                    expected_output=entry.get("expected_output"),
                    expects_refusal=entry.get("expects_refusal", False),
                    expects_gate_respected=entry.get("expected_gate_respected"),
                    metric_keys=entry.get("metric_keys", []),
                    tags=entry.get("tags", []),
                )
            except ValidationError as exc:
                raise RegistryError(
                    f"{path.name}: evaluation scenario {key!r} is invalid: {exc}"
                ) from exc

    def _load_evaluation_suites(self, path: Path) -> None:
        for entry in _read_yaml(path).get("evaluation_suites", []):
            key = entry["key"]
            try:
                self.evaluation_suites[key] = EvaluationSuite(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.EVALUATION_SUITE,
                    suite_key=key,
                    level=entry["level"],
                    scenario_refs=[
                        EntityRef(type=EntityType.EVALUATION_SCENARIO, id=s)
                        for s in entry.get("scenarios", [])
                    ],
                    metric_refs=[
                        EntityRef(type=EntityType.EVALUATION_METRIC, id=m)
                        for m in entry.get("metrics", [])
                    ],
                    passing_score=entry.get("passing_score", 0.8),
                    passing_delivery_score=entry.get("passing_delivery_score", 0.9),
                    applies_to=entry.get("applies_to", []),
                )
            except ValidationError as exc:
                raise RegistryError(
                    f"{path.name}: evaluation suite {key!r} is invalid: {exc}"
                ) from exc

    def _load_platforms(self, path: Path) -> None:
        data = _read_yaml(path)
        for entry in data.get("platforms", []):
            key = entry["key"]
            self.platforms[key] = Platform(
                id=key,
                name=entry.get("name", key),
                entity_type=EntityType.PLATFORM,
                platform_key=key,
                vendor=entry.get("vendor"),
                regions=entry.get("regions", []),
            )
        for entry in data.get("technology_bindings", []):
            binding_id = f"{entry['capability_key']}@{entry['platform_key']}"
            try:
                self.technology_bindings.append(
                    TechnologyBinding(
                        id=binding_id,
                        name=binding_id,
                        entity_type=EntityType.TECHNOLOGY_BINDING,
                        capability_key=entry["capability_key"],
                        platform_key=entry["platform_key"],
                        technologies=entry["technologies"],
                        detection_hints=entry.get("detection_hints", []),
                        notes=entry.get("notes"),
                        maturity=entry.get("maturity"),
                    )
                )
            except ValidationError as exc:
                raise RegistryError(
                    f"{path.name}: technology binding {binding_id!r} is invalid: {exc}"
                ) from exc

    def _load_provenance(self, path: Path) -> None:
        for entry in _read_yaml(path).get("provenance_states", []):
            try:
                state = ProvenanceState(entry["key"])
            except ValueError as exc:
                raise RegistryError(
                    f"{path.name}: unknown provenance state {entry['key']!r}"
                ) from exc
            self.provenance_rules[state] = ProvenanceRule(
                key=state,
                name=entry.get("name", state.value),
                description=entry.get("description", ""),
                rank=int(entry.get("rank", 0)),
                requires_confidence=bool(entry.get("requires_confidence", False)),
                requires_discoverer=bool(entry.get("requires_discoverer", False)),
                requires_human=bool(entry.get("requires_human", False)),
                may_drive_automated_action=bool(entry.get("may_drive_automated_action", False)),
                may_be_cited_as_fact=bool(entry.get("may_be_cited_as_fact", False)),
                may_block=bool(entry.get("may_block", False)),
            )

    def _load_risk(self, path: Path) -> None:
        data = _read_yaml(path)
        for level_name, mapping in (data.get("approval_matrix") or {}).items():
            try:
                level = AutomationLevel(level_name)
            except ValueError as exc:
                raise RegistryError(f"{path.name}: unknown automation level {level_name!r}") from exc
            resolved: dict[ActionClass, ApprovalLevel] = {}
            for action_name, approval_name in mapping.items():
                try:
                    resolved[ActionClass(action_name)] = ApprovalLevel(approval_name)
                except ValueError as exc:
                    raise RegistryError(
                        f"{path.name}: approval_matrix[{level_name}][{action_name}] = "
                        f"{approval_name!r} is not a known action/approval"
                    ) from exc
            self.approval_matrix[level] = resolved
        self.risk_examples = list(data.get("examples", []))
        self.delivery_process_kinds = {
            entry["key"]: entry.get("name", entry["key"])
            for entry in data.get("delivery_process_kinds", [])
        }

    # -- delivery model loading -------------------------------------------

    def _load_delivery_model(self, path: Path) -> LoadedDeliveryModel:  # noqa: C901
        """Construct a full delivery model from one YAML file."""
        data = _read_yaml(path)
        spec = data.get("model") or {}
        model_key = spec.get("key")
        if not model_key:
            raise RegistryError(f"{path.name}: delivery model has no key")

        def ref(entity_type: EntityType, key: str) -> EntityRef:
            return EntityRef(type=entity_type, id=key)

        try:
            model = DeliveryModel(
                id=model_key,
                name=spec.get("name", model_key),
                entity_type=EntityType.DELIVERY_MODEL,
                model_key=model_key,
                applies_to=spec.get("applies_to", []),
                owner=spec.get("owner"),
                delivery_capability_keys=spec.get("delivery_capabilities", []),
                **_REGISTRY_PROVENANCE,
            )
            loaded = LoadedDeliveryModel(model=model)

            if method := data.get("methodology"):
                loaded.methodology = Methodology(
                    id=method["key"],
                    name=method.get("name", method["key"]),
                    entity_type=EntityType.METHODOLOGY,
                    methodology_key=method["key"],
                    style=method.get("style"),
                    principles=method.get("principles", []),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("evidence_requirements", []):
                key = entry["key"]
                loaded.evidence_requirements[key] = EvidenceRequirement(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.EVIDENCE_REQUIREMENT,
                    requirement_key=key,
                    evidence_kind=entry["evidence_kind"],
                    mandatory=entry.get("mandatory", True),
                    validation_method=entry.get("validation_method", "DOCUMENT_REVIEW"),
                    retention_days=entry.get("retention_days"),
                    acceptance_pattern=entry.get("acceptance_pattern"),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("standards", []):
                key = entry["key"]
                loaded.standards[key] = Standard(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.STANDARD,
                    standard_key=key,
                    statement=entry["statement"],
                    category=entry.get("category"),
                    authority=entry.get("authority"),
                    validation_method=entry.get("validation_method", "HUMAN_REVIEW"),
                    validation_reference=entry.get("validation_reference"),
                    blocking=entry.get("blocking", False),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("templates", []):
                key = entry["key"]
                loaded.templates[key] = Template(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.TEMPLATE,
                    template_key=key,
                    artifact_kind=entry["artifact_kind"],
                    content_reference=entry["content_reference"],
                    required_sections=entry.get("required_sections", []),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("controls", []):
                key = entry["key"]
                loaded.controls[key] = Control(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.CONTROL,
                    control_key=key,
                    statement=entry["statement"],
                    control_family=entry.get("control_family"),
                    regulatory_reference=entry.get("regulatory_reference"),
                    risk_level=entry.get("risk_level", "MEDIUM"),
                    implemented_by=[
                        ref(EntityType.DELIVERY_TASK, k) for k in entry.get("implemented_by", [])
                    ],
                    evidence_requirement_refs=[
                        ref(EntityType.EVIDENCE_REQUIREMENT, k)
                        for k in entry.get("evidence_requirements", [])
                    ],
                    blocking=entry.get("blocking", False),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("checklists", []):
                key = entry["key"]
                for index, item in enumerate(entry.get("items", [])):
                    item_key = item["key"]
                    loaded.checklist_items[item_key] = ChecklistItem(
                        id=item_key,
                        name=item.get("description", item_key)[:512],
                        entity_type=EntityType.CHECKLIST_ITEM,
                        item_key=item_key,
                        checklist_key=key,
                        sequence=index,
                        description=item.get("description"),
                        mandatory=item.get("mandatory", True),
                        validation_method=item.get("validation_method", "HUMAN_REVIEW"),
                        validation_reference=item.get("validation_reference"),
                        evidence_required=item.get("evidence_required", False),
                        blocking=item.get("blocking", False),
                        **_REGISTRY_PROVENANCE,
                    )
                loaded.checklists[key] = Checklist(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.CHECKLIST,
                    checklist_key=key,
                    applies_to=entry.get("applies_to", []),
                    item_refs=[
                        ref(EntityType.CHECKLIST_ITEM, i["key"]) for i in entry.get("items", [])
                    ],
                    completion_rule=CompletionRule(entry.get("completion_rule", "ALL_MANDATORY")),
                    completion_threshold=entry.get("completion_threshold"),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("acceptance_criteria", []):
                key = entry["key"]
                loaded.criteria[key] = AcceptanceCriterion(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.ACCEPTANCE_CRITERION,
                    criterion_key=key,
                    condition=entry["condition"],
                    validation_method=entry.get("validation_method", "HUMAN_REVIEW"),
                    validation_reference=entry.get("validation_reference"),
                    severity=entry.get("severity", "MEDIUM"),
                    applies_to=entry.get("applies_to", []),
                    evidence_required=entry.get("evidence_required", True),
                    blocking=entry.get("blocking", False),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("gates", []):
                key = entry["key"]
                loaded.gates[key] = ApprovalGate(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.APPROVAL_GATE,
                    gate_key=key,
                    phase_keys=entry.get("phases", []),
                    required_artifact_kinds=entry.get("required_artifact_kinds", []),
                    required_checklist_refs=[
                        ref(EntityType.CHECKLIST, k) for k in entry.get("required_checklists", [])
                    ],
                    required_evaluation_refs=[
                        ref(EntityType.EVALUATION_SUITE, k)
                        for k in entry.get("required_evaluations", [])
                    ],
                    required_evidence_refs=[
                        ref(EntityType.EVIDENCE_REQUIREMENT, k)
                        for k in entry.get("required_evidence", [])
                    ],
                    required_role_keys=entry.get("required_roles", []),
                    minimum_traceability=entry.get("minimum_traceability", 0.0),
                    risk_level=entry.get("risk_level", "MEDIUM"),
                    blocking=entry.get("blocking", False),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("tasks", []):
                key = entry["key"]
                input_refs, output_refs = [], []
                for spec_in in entry.get("inputs", []):
                    in_key = spec_in["key"]
                    loaded.inputs[in_key] = DeliveryInput(
                        id=in_key,
                        name=spec_in.get("name", in_key),
                        entity_type=EntityType.DELIVERY_INPUT,
                        input_key=in_key,
                        input_kind=spec_in["kind"],
                        mandatory=spec_in.get("mandatory", True),
                        source_phase_key=spec_in.get("source_phase"),
                        satisfied_by_artifact_kind=spec_in.get("artifact_kind"),
                        **_REGISTRY_PROVENANCE,
                    )
                    input_refs.append(ref(EntityType.DELIVERY_INPUT, in_key))
                for spec_out in entry.get("outputs", []):
                    out_key = spec_out["key"]
                    loaded.outputs[out_key] = DeliveryOutput(
                        id=out_key,
                        name=spec_out.get("name", out_key),
                        entity_type=EntityType.DELIVERY_OUTPUT,
                        output_key=out_key,
                        output_kind=spec_out["kind"],
                        mandatory=spec_out.get("mandatory", True),
                        artifact_kind=spec_out.get("artifact_kind"),
                        template_ref=(
                            ref(EntityType.TEMPLATE, spec_out["template"])
                            if spec_out.get("template")
                            else None
                        ),
                        evidence_requirement_refs=[
                            ref(EntityType.EVIDENCE_REQUIREMENT, k)
                            for k in spec_out.get("evidence", [])
                        ],
                        **_REGISTRY_PROVENANCE,
                    )
                    output_refs.append(ref(EntityType.DELIVERY_OUTPUT, out_key))

                loaded.tasks[key] = DeliveryTask(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.DELIVERY_TASK,
                    task_key=key,
                    phase_keys=entry.get("phases", []),
                    purpose=entry.get("purpose"),
                    input_refs=input_refs,
                    output_refs=output_refs,
                    required_skill_keys=entry.get("skills", []),
                    required_tool_keys=entry.get("tools", []),
                    delivery_role_keys=entry.get("delivery_roles", []),
                    checklist_refs=[
                        ref(EntityType.CHECKLIST, k) for k in entry.get("checklists", [])
                    ],
                    acceptance_criterion_refs=[
                        ref(EntityType.ACCEPTANCE_CRITERION, k)
                        for k in entry.get("acceptance_criteria", [])
                    ],
                    approval_gate_refs=[
                        ref(EntityType.APPROVAL_GATE, k) for k in entry.get("gates", [])
                    ],
                    evidence_requirement_refs=[
                        ref(EntityType.EVIDENCE_REQUIREMENT, k) for k in entry.get("evidence", [])
                    ],
                    standard_refs=[
                        ref(EntityType.STANDARD, k) for k in entry.get("standards", [])
                    ],
                    risk_level=entry.get("risk_level", "MEDIUM"),
                    automatable=entry.get("automatable", True),
                    **_REGISTRY_PROVENANCE,
                )

            for entry in data.get("phases", []):
                key = entry["key"]
                loaded.phases[key] = DeliveryPhase(
                    id=key,
                    name=entry.get("name", key),
                    entity_type=EntityType.DELIVERY_PHASE,
                    phase_key=key,
                    model_key=model_key,
                    sequence=entry.get("sequence", 0),
                    purpose=entry.get("purpose"),
                    task_refs=[ref(EntityType.DELIVERY_TASK, k) for k in entry.get("tasks", [])],
                    approval_gate_refs=[
                        ref(EntityType.APPROVAL_GATE, k) for k in entry.get("gates", [])
                    ],
                    entry_criteria=entry.get("entry_criteria", []),
                    exit_criteria=entry.get("exit_criteria", []),
                    depends_on_phase_keys=entry.get("depends_on", []),
                    **_REGISTRY_PROVENANCE,
                )
            model.phase_refs = [ref(EntityType.DELIVERY_PHASE, k) for k in loaded.phases]

            for entry in data.get("raci", []):
                task_key = entry["task"]
                subject = ref(EntityType.DELIVERY_TASK, task_key)
                pairs = [(entry["accountable"], RaciLetter.ACCOUNTABLE)]
                pairs += [(r, RaciLetter.RESPONSIBLE) for r in entry.get("responsible", [])]
                pairs += [(r, RaciLetter.CONSULTED) for r in entry.get("consulted", [])]
                pairs += [(r, RaciLetter.INFORMED) for r in entry.get("informed", [])]
                for role_key, letter in pairs:
                    loaded.raci.append(
                        RaciAssignment(
                            id=f"{task_key}:{role_key}:{letter.value}",
                            name=f"{role_key} {letter.value} for {task_key}",
                            entity_type=EntityType.RACI_ASSIGNMENT,
                            subject_ref=subject,
                            delivery_role_key=role_key,
                            letter=letter,
                            **_REGISTRY_PROVENANCE,
                        )
                    )

            # A contract is derived from each task that has controls: it is the
            # executable projection of the task, not a separately authored thing.
            for task in loaded.tasks.values():
                if not task.mandatory_control_refs:
                    continue
                contract_key = f"contract.{task.task_key.removeprefix('task.')}"
                artifact_kinds = [
                    loaded.outputs[o.id].artifact_kind
                    for o in task.output_refs
                    if loaded.outputs.get(o.id) and loaded.outputs[o.id].artifact_kind
                ]
                loaded.contracts[contract_key] = DeliveryContract(
                    id=contract_key,
                    name=f"{task.name} Contract",
                    entity_type=EntityType.DELIVERY_CONTRACT,
                    contract_key=contract_key,
                    task_key=task.task_key,
                    delivery_model_key=model_key,
                    input_refs=list(task.input_refs),
                    output_refs=list(task.output_refs),
                    required_artifact_kinds=artifact_kinds,
                    required_skill_keys=list(task.required_skill_keys),
                    required_tool_keys=list(task.required_tool_keys),
                    checklist_refs=list(task.checklist_refs),
                    acceptance_criterion_refs=list(task.acceptance_criterion_refs),
                    evidence_requirement_refs=list(task.evidence_requirement_refs),
                    approval_gate_refs=list(task.approval_gate_refs),
                    delivery_role_keys=list(task.delivery_role_keys),
                    risk_level=task.risk_level,
                    automatable=task.automatable,
                    **_REGISTRY_PROVENANCE,
                )

        except ValidationError as exc:
            raise RegistryError(f"{path.name}: delivery model is invalid: {exc}") from exc

        return loaded

    # -- lookups ------------------------------------------------------------

    def relationship_type(self, key: str) -> RelationshipTypeSpec | None:
        return self.relationship_types.get(key)

    def capability(self, key: str) -> CapabilitySpec | None:
        return self.capabilities.get(key)

    def delivery_capability(self, key: str) -> CapabilitySpec | None:
        return self.delivery_capabilities.get(key)

    def role(self, key: str) -> EngineeringRole | None:
        return self.engineering_roles.get(key)

    def delivery_role(self, key: str) -> DeliveryRole | None:
        return self.delivery_roles.get(key)

    def responsibility(self, key: str) -> EngineeringResponsibility | None:
        return self.responsibilities.get(key)

    def delivery_model(self, key: str) -> LoadedDeliveryModel | None:
        return self.delivery_models.get(key)

    def bindings_for(
        self, capability_key: str, platform_key: str | None = None
    ) -> list[TechnologyBinding]:
        """Technology bindings realizing a capability, optionally on one platform.

        Platform-neutral bindings are always included: dbt realizes
        ``transformation`` regardless of which cloud it runs on.
        """
        return [
            b
            for b in self.technology_bindings
            if b.capability_key == capability_key
            and (platform_key is None or b.platform_key in (platform_key, "neutral"))
        ]

    def required_approval(
        self, action_class: ActionClass, automation_level: AutomationLevel
    ) -> ApprovalLevel:
        """The approval an action demands at a given automation level.

        Defaults to maker-checker when the matrix is silent: an unlisted
        combination is an unreviewed policy decision, and the safe reading of
        that is 'ask two humans'.
        """
        return self.approval_matrix.get(automation_level, {}).get(
            action_class, ApprovalLevel.MAKER_CHECKER
        )

    def roles_fulfilling(self, responsibility_key: str) -> list[EngineeringRole]:
        """Engineering roles that can fulfil a responsibility."""
        return [
            role
            for role in self.engineering_roles.values()
            if responsibility_key in role.responsibilities
        ]

    def resolve_role_chain(self, delivery_role_key: str) -> dict[str, list[str]]:
        """Walk DeliveryRole → Responsibility → EngineeringRole.

        The four-level chain made queryable. The fourth level (Agent) is
        resolved at composition time, not here.
        """
        delivery_role = self.delivery_roles.get(delivery_role_key)
        if delivery_role is None:
            return {}
        chain: dict[str, list[str]] = {}
        for responsibility_key in delivery_role.responsibility_keys:
            chain[responsibility_key] = sorted(
                role.role_key for role in self.roles_fulfilling(responsibility_key)
            )
        return chain

    @cached_property
    def capability_keys(self) -> frozenset[str]:
        return frozenset(self.capabilities)

    @cached_property
    def delivery_capability_keys(self) -> frozenset[str]:
        return frozenset(self.delivery_capabilities)

    # -- validation ---------------------------------------------------------

    def validate(self) -> None:  # noqa: C901
        """Cross-check every registry, reporting all problems at once."""
        errors: list[str] = []

        if self.declared_version != METAMODEL_VERSION:
            errors.append(
                f"metamodel.version.yaml declares {self.declared_version!r} but "
                f"domain/metamodel/version.py declares {METAMODEL_VERSION!r}; "
                "the contract and the code must agree"
            )

        known_entity_types = set(EntityType)
        for key, spec in self.relationship_types.items():
            for endpoint in (*spec.source_types, *spec.target_types):
                if endpoint not in known_entity_types:
                    errors.append(
                        f"relationship type {key!r} references unknown entity type {endpoint!r}"
                    )

        # --- the four-level role chain -----------------------------------
        for key, responsibility in self.responsibilities.items():
            for capability in responsibility.required_capability_keys:
                if capability not in self.capabilities:
                    errors.append(
                        f"responsibility {key!r} requires unknown capability {capability!r}"
                    )
            for capability in responsibility.required_delivery_capability_keys:
                if capability not in self.delivery_capabilities:
                    errors.append(
                        f"responsibility {key!r} requires unknown delivery capability "
                        f"{capability!r}"
                    )
            for role_key in responsibility.fulfilled_by_role_keys:
                if role_key not in self.engineering_roles:
                    errors.append(
                        f"responsibility {key!r} is fulfilled by unknown engineering role "
                        f"{role_key!r}"
                    )

        for key, role in self.engineering_roles.items():
            for capability in role.required_capabilities:
                if capability not in self.capabilities:
                    errors.append(f"role {key!r} requires unknown capability {capability!r}")
            for capability in role.required_delivery_capabilities:
                if capability not in self.delivery_capabilities:
                    errors.append(
                        f"role {key!r} requires unknown delivery capability {capability!r}"
                    )
            for responsibility_key in role.responsibilities:
                if responsibility_key not in self.responsibilities:
                    errors.append(
                        f"role {key!r} claims unknown responsibility {responsibility_key!r}"
                    )

        for key, delivery_role in self.delivery_roles.items():
            for responsibility_key in delivery_role.responsibility_keys:
                if responsibility_key not in self.responsibilities:
                    errors.append(
                        f"delivery role {key!r} is accountable for unknown responsibility "
                        f"{responsibility_key!r}"
                    )
            for other in delivery_role.incompatible_with:
                if other not in self.delivery_roles:
                    errors.append(
                        f"delivery role {key!r} is incompatible with unknown role {other!r}"
                    )

        # A non-delegable responsibility fulfilled by an engineering role is a
        # contradiction: it says a human must answer for it while naming the
        # software that would.
        for key, responsibility in self.responsibilities.items():
            if not responsibility.delegable_to_agent and responsibility.fulfilled_by_role_keys:
                errors.append(
                    f"responsibility {key!r} is marked delegable_to_agent=false but names "
                    f"engineering roles {responsibility.fulfilled_by_role_keys}; a "
                    "non-delegable accountability cannot be assigned to an agent-implemented role"
                )

        # --- the marketplace catalog ---------------------------------------
        # Deliberately not symmetric: an EngineeringRole's required skill/tool/
        # knowledge keys are NOT checked against these catalogs. The worked
        # catalog only covers the roles staffed in the MVP; checking the
        # other direction would force populating catalog entries for every
        # unstaffed role too. See ADR-0014.
        for key, skill in self.skills.items():
            for tool in skill.required_tools:
                if tool not in self.tools:
                    errors.append(f"skill {key!r} requires unknown tool {tool!r}")
            for pack in skill.required_knowledge:
                if pack not in self.knowledge_packs:
                    errors.append(f"skill {key!r} requires unknown knowledge pack {pack!r}")

        for key, agent in self.agents.items():
            if agent.role_key not in self.engineering_roles:
                errors.append(
                    f"agent {key!r} implements unknown engineering role {agent.role_key!r}"
                )
            for capability in agent.capabilities:
                if capability not in self.capabilities:
                    errors.append(f"agent {key!r} declares unknown capability {capability!r}")
            for capability in agent.delivery_capabilities:
                if capability not in self.delivery_capabilities:
                    errors.append(
                        f"agent {key!r} declares unknown delivery capability {capability!r}"
                    )
            for skill_key in agent.skills:
                if skill_key not in self.skills:
                    errors.append(f"agent {key!r} declares unknown skill {skill_key!r}")
            for tool_key in agent.tools:
                if tool_key not in self.tools:
                    errors.append(f"agent {key!r} declares unknown tool {tool_key!r}")
            for pack in agent.knowledge_packs:
                if pack not in self.knowledge_packs:
                    errors.append(f"agent {key!r} declares unknown knowledge pack {pack!r}")

        # --- the evaluation catalog ------------------------------------------
        # Deliberately not checked: EvaluationSuite.applies_to against roles/
        # tasks -- its semantics are level-dependent (a workflow-level suite's
        # applies_to names task keys, an agent-level suite's names role keys)
        # and the field is untyped list[str], so one generic check would be
        # wrong for one level or the other. See ADR-0015.
        for key, suite in self.evaluation_suites.items():
            for ref_ in suite.scenario_refs:
                if ref_.id not in self.evaluation_scenarios:
                    errors.append(
                        f"evaluation suite {key!r} references unknown scenario {ref_.id!r}"
                    )
            for ref_ in suite.metric_refs:
                if ref_.id not in self.evaluation_metrics:
                    errors.append(
                        f"evaluation suite {key!r} references unknown metric {ref_.id!r}"
                    )

        for key, scenario in self.evaluation_scenarios.items():
            for metric_key in scenario.metric_keys:
                if metric_key not in self.evaluation_metrics:
                    errors.append(
                        f"evaluation scenario {key!r} references unknown metric {metric_key!r}"
                    )

        # --- platform bindings --------------------------------------------
        platform_keys = set(self.platforms)
        seen_bindings: set[str] = set()
        for binding in self.technology_bindings:
            if binding.platform_key not in platform_keys:
                errors.append(
                    f"technology binding {binding.binding_key!r} targets unknown platform "
                    f"{binding.platform_key!r}"
                )
            if binding.capability_key not in self.capabilities:
                errors.append(
                    f"technology binding {binding.binding_key!r} realizes unknown capability "
                    f"{binding.capability_key!r}"
                )
            if binding.binding_key in seen_bindings:
                errors.append(f"duplicate technology binding {binding.binding_key!r}")
            seen_bindings.add(binding.binding_key)

        # --- provenance and approvals -------------------------------------
        missing_states = set(ProvenanceState) - set(self.provenance_rules)
        if missing_states:
            errors.append(
                f"provenance.yaml is missing rules for {sorted(s.value for s in missing_states)}"
            )
        inferred = self.provenance_rules.get(ProvenanceState.INFERRED)
        if inferred is not None and inferred.may_block:
            errors.append(
                "provenance.yaml permits INFERRED facts to block delivery; extracted text must "
                "never silently become enforced policy"
            )

        for level in AutomationLevel:
            if level not in self.approval_matrix:
                errors.append(f"risk.yaml approval_matrix has no entry for {level.value}")
                continue
            missing_actions = set(ActionClass) - set(self.approval_matrix[level])
            if missing_actions:
                errors.append(
                    f"risk.yaml approval_matrix[{level.value}] is missing "
                    f"{sorted(a.value for a in missing_actions)}"
                )

        for level, mapping in self.approval_matrix.items():
            approval = mapping.get(ActionClass.DESTRUCTIVE)
            if approval in (ApprovalLevel.NONE, ApprovalLevel.SAMPLED_QA):
                errors.append(
                    f"risk.yaml approval_matrix[{level.value}][DESTRUCTIVE] = {approval.value}; "
                    "destructive actions always require an explicit human approval"
                )

        for loaded in self.delivery_models.values():
            errors.extend(self._validate_delivery_model(loaded))

        if errors:
            raise RegistryError(
                f"{len(errors)} registry problem(s) found:\n  - " + "\n  - ".join(errors)
            )

    def _validate_delivery_model(self, loaded: LoadedDeliveryModel) -> list[str]:  # noqa: C901
        """Check one delivery model's internal consistency."""
        errors: list[str] = []
        model_key = loaded.model.model_key

        def missing(kind: str, owner: str, key: str) -> str:
            return f"delivery model {model_key!r}: {owner} references unknown {kind} {key!r}"

        for capability in loaded.model.delivery_capability_keys:
            if capability not in self.delivery_capabilities:
                errors.append(missing("delivery capability", "the model", capability))

        for task_key, task in loaded.tasks.items():
            for ref_ in task.checklist_refs:
                if ref_.id not in loaded.checklists:
                    errors.append(missing("checklist", f"task {task_key}", ref_.id))
            for ref_ in task.acceptance_criterion_refs:
                if ref_.id not in loaded.criteria:
                    errors.append(missing("acceptance criterion", f"task {task_key}", ref_.id))
            for ref_ in task.approval_gate_refs:
                if ref_.id not in loaded.gates:
                    errors.append(missing("gate", f"task {task_key}", ref_.id))
            for ref_ in task.evidence_requirement_refs:
                if ref_.id not in loaded.evidence_requirements:
                    errors.append(missing("evidence requirement", f"task {task_key}", ref_.id))
            for ref_ in task.standard_refs:
                if ref_.id not in loaded.standards:
                    errors.append(missing("standard", f"task {task_key}", ref_.id))
            for role_key in task.delivery_role_keys:
                if role_key not in self.delivery_roles:
                    errors.append(missing("delivery role", f"task {task_key}", role_key))
            for phase_key in task.phase_keys:
                if phase_key not in loaded.phases:
                    errors.append(missing("phase", f"task {task_key}", phase_key))

        for gate_key, gate in loaded.gates.items():
            for ref_ in gate.required_checklist_refs:
                if ref_.id not in loaded.checklists:
                    errors.append(missing("checklist", f"gate {gate_key}", ref_.id))
            for ref_ in gate.required_evidence_refs:
                if ref_.id not in loaded.evidence_requirements:
                    errors.append(missing("evidence requirement", f"gate {gate_key}", ref_.id))
            for ref_ in gate.required_evaluation_refs:
                if ref_.id not in self.evaluation_suites:
                    errors.append(missing("evaluation suite", f"gate {gate_key}", ref_.id))
            for role_key in gate.required_role_keys:
                if role_key not in self.delivery_roles:
                    errors.append(missing("delivery role", f"gate {gate_key}", role_key))
            # A gate nobody is empowered to approve can never be passed.
            for role_key in gate.required_role_keys:
                role = self.delivery_roles.get(role_key)
                if role is not None and gate_key not in role.approves_gate_keys:
                    errors.append(
                        f"delivery model {model_key!r}: gate {gate_key!r} requires approval from "
                        f"{role_key!r}, but that role does not list the gate in approves_gates"
                    )

        # The forward direction of the check above: a role that claims it may
        # approve a gate must be claiming a gate that actually exists. Without
        # this, `approves_gate_keys: [gate.typo]` loads silently and the role
        # simply never has anything to approve -- a dangling reference that
        # looks, at a glance, like real authority. Delivery roles are loaded
        # once globally rather than per model (registry.py:_load_delivery_roles),
        # so this check is only sound while a single delivery model is loaded;
        # it will need scoping by model_key if a second one is ever added.
        for role_key, delivery_role in self.delivery_roles.items():
            for gate_key in delivery_role.approves_gate_keys:
                if gate_key not in loaded.gates:
                    errors.append(
                        f"delivery model {model_key!r}: delivery role {role_key!r} claims it "
                        f"approves gate {gate_key!r}, which does not exist"
                    )

        for checklist_key, checklist in loaded.checklists.items():
            for ref_ in checklist.item_refs:
                if ref_.id not in loaded.checklist_items:
                    errors.append(missing("checklist item", f"checklist {checklist_key}", ref_.id))
            for applies in checklist.applies_to:
                if applies not in loaded.tasks and applies not in loaded.phases:
                    errors.append(
                        missing("task or phase", f"checklist {checklist_key} applies_to", applies)
                    )

        # Phase dependency graph must be acyclic -- a cycle makes the model
        # unsatisfiable, and it is far cheaper to catch here than at run time.
        errors.extend(self._detect_phase_cycles(loaded))

        # Exactly one accountable role per task. Two is an unresolvable
        # escalation; zero means nobody answers for it.
        accountable: dict[str, list[str]] = {}
        for assignment in loaded.raci:
            if assignment.letter is RaciLetter.ACCOUNTABLE:
                accountable.setdefault(assignment.subject_ref.id, []).append(
                    assignment.delivery_role_key
                )
        for subject, roles in accountable.items():
            if len(roles) > 1:
                errors.append(
                    f"delivery model {model_key!r}: {subject!r} has {len(roles)} accountable "
                    f"roles {sorted(roles)}; exactly one role must be accountable"
                )
        for assignment in loaded.raci:
            if assignment.delivery_role_key not in self.delivery_roles:
                errors.append(
                    missing("delivery role", "a RACI assignment", assignment.delivery_role_key)
                )

        return errors

    @staticmethod
    def _detect_phase_cycles(loaded: LoadedDeliveryModel) -> list[str]:
        """Depth-first cycle detection over ``depends_on_phase_keys``."""
        errors: list[str] = []
        phases = loaded.phases
        for key, phase in phases.items():
            for dependency in phase.depends_on_phase_keys:
                if dependency not in phases:
                    errors.append(
                        f"delivery model {loaded.model.model_key!r}: phase {key!r} depends on "
                        f"unknown phase {dependency!r}"
                    )

        WHITE, GREY, BLACK = 0, 1, 2
        colour = dict.fromkeys(phases, WHITE)

        def visit(node: str, path: list[str]) -> None:
            colour[node] = GREY
            for dependency in phases[node].depends_on_phase_keys:
                if dependency not in phases:
                    continue
                if colour[dependency] == GREY:
                    cycle = " -> ".join([*path, node, dependency])
                    errors.append(
                        f"delivery model {loaded.model.model_key!r}: phase dependency cycle "
                        f"{cycle}; the model is unsatisfiable"
                    )
                elif colour[dependency] == WHITE:
                    visit(dependency, [*path, node])
            colour[node] = BLACK

        for key in phases:
            if colour[key] == WHITE:
                visit(key, [])

        return errors
