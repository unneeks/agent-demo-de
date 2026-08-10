"""`build_agent_context()` -- the first real caller of `engines.context.
assembler.assemble()` (zero callers outside its own test suite through
Phase 6). Reuses `assemble()` unmodified; asserts the bundle it returns is
exactly what `assemble()` itself would produce for the same candidates."""

from __future__ import annotations

from agent_runtime.context import _knowledge_pack_item, _skill_item, build_agent_context, render_system_prompt
from domain.metamodel.enums import ContextItemKind
from engines.context.assembler import assemble

from tests.conftest import make_policy


class TestBuildAgentContext:
    def test_bundle_includes_every_declared_skill_and_knowledge_pack(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        policy = make_policy(max_tokens=100_000)
        bundle = build_agent_context(agent, registry, "run the regression suite", policy=policy)

        included_refs = {item.content_reference for item in bundle.items}
        for skill_key in agent.skills:
            assert f"skill://{skill_key}" in included_refs
        for pack_key in agent.knowledge_packs:
            pack = registry.knowledge_packs[pack_key]
            assert pack.content_reference in included_refs

    def test_every_item_is_context_item_kind_knowledge(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        policy = make_policy(max_tokens=100_000)
        bundle = build_agent_context(agent, registry, "run the regression suite", policy=policy)
        assert bundle.items
        for item in bundle.items:
            assert item.kind is ContextItemKind.KNOWLEDGE

    def test_assemble_is_called_unmodified(self, registry) -> None:
        """The bundle_hash algorithm itself is assemble()'s -- this module
        adds no scoring or ranking logic of its own."""
        agent = registry.agents["regression-agent"]
        policy = make_policy(max_tokens=100_000)
        bundle = build_agent_context(agent, registry, "run the regression suite", now=None, policy=policy)

        # Reconstruct the same candidate set independently and assemble()
        # directly -- the two bundle_hashes must agree bit for bit.
        reference_time = bundle.assembled_at
        candidates = [
            item
            for key in agent.knowledge_packs
            if (item := _knowledge_pack_item(key, registry, reference_time)) is not None
        ] + [
            item for key in agent.skills if (item := _skill_item(key, registry, reference_time)) is not None
        ]
        direct = assemble(policy, candidates, agent_ref=agent.ref(), now=reference_time)
        assert direct.bundle_hash == bundle.bundle_hash


class TestRenderSystemPrompt:
    def test_prompt_names_the_agent_and_the_task(self, registry) -> None:
        agent = registry.agents["regression-agent"]
        policy = make_policy(max_tokens=100_000)
        bundle = build_agent_context(agent, registry, "run the regression suite", policy=policy)
        prompt = render_system_prompt(bundle, agent, "run the regression suite")
        assert agent.name in prompt
        assert "run the regression suite" in prompt
