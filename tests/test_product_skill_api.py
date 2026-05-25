from memory_garden.product import MemoryPatch
from memory_garden.providers import (
    FakeEmbeddingProvider,
    FakeLLMProvider,
    FakeRerankerProvider,
    ProviderPolicy,
    ProviderRegistry,
)
from memory_garden.sdk import MemoryGarden
from memory_garden.skill import SkillConfig


def test_skill_product_api_exposes_full_memory_workflow(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill()
        skill.configure_providers(
            ProviderRegistry(
                policy=ProviderPolicy(allow_raw_user_text=True),
                embedding=FakeEmbeddingProvider(),
                reranker=FakeRerankerProvider(),
            )
        )

        proposals = skill.propose_memory("remember: prefer detailed release checklists")
        assert proposals

        card = skill.approve_memory_proposal(proposals[0].id)
        assert card.id

        updated = skill.update_memory(card.id, MemoryPatch(tags=["release", "checklist"]))
        assert updated.tags == ["release", "checklist"]

        hits = skill.retrieve_memories("release checklist")
        assert hits.hits[0].memory.id == card.id
        assert hits.provider_used == "fake-reranker"

        brief = skill.build_memory_brief("release checklist")
        assert card.id in brief.source_memory_ids

        plan = skill.plan_memory_forget(memory_id=card.id)
        executed, proof = skill.execute_memory_forget(plan.id)
        assert executed.status == "executed"
        assert proof.proven is True
    finally:
        garden.close()


def test_as_skill_reuses_default_instance_and_preserves_provider_configuration(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        registry = ProviderRegistry(
            policy=ProviderPolicy(allow_raw_user_text=True),
            llm=FakeLLMProvider(),
        )
        skill = garden.as_skill()
        skill.configure_providers(registry)

        same_skill = garden.as_skill()

        assert same_skill is skill
        assert same_skill.product.providers.llm is registry.llm
        assert same_skill.propose_memory("remember: prefer detailed release checklists")[0].source == "fake-llm"
    finally:
        garden.close()


def test_new_skill_instances_inherit_garden_level_provider_configuration(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        registry = ProviderRegistry(
            policy=ProviderPolicy(allow_raw_user_text=True),
            llm=FakeLLMProvider(),
        )
        garden.as_skill().configure_providers(registry)

        another_skill = garden.as_skill(SkillConfig())

        assert another_skill.product.providers.llm is registry.llm
        assert another_skill.propose_memory("remember: prefer detailed release checklists")[0].source == "fake-llm"
    finally:
        garden.close()


def test_with_fake_providers_does_not_enable_remote_policy(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        skill = garden.as_skill().with_fake_providers()

        policy = skill.product.providers.policy
        assert policy.allow_raw_user_text is True
        assert policy.allow_remote_llm is False
        assert policy.allow_remote_embeddings is False
        assert policy.allow_remote_rerank is False
        assert skill.propose_memory("remember: fake provider remains local")[0].source == "fake-llm"
    finally:
        garden.close()


def test_skill_with_openai_and_deepseek_explicitly_opt_into_remote(tmp_path, monkeypatch):
    import memory_garden.skill as skill_module

    class _RemoteProvider:
        name = "test-provider"
        is_remote = True

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(skill_module, "OpenAICompatibleLLMProvider", _RemoteProvider)
    monkeypatch.setattr(skill_module, "OpenAICompatibleEmbeddingProvider", _RemoteProvider)
    monkeypatch.setattr(skill_module, "DeepSeekLLMProvider", _RemoteProvider)

    openai_garden = MemoryGarden.local(tmp_path / "openai")
    deepseek_garden = MemoryGarden.local(tmp_path / "deepseek")
    try:
        openai_policy = openai_garden.as_skill().with_openai(api_key="test-key").product.providers.policy
        deepseek_policy = deepseek_garden.as_skill().with_deepseek(api_key="test-key").product.providers.policy

        for policy in (openai_policy, deepseek_policy):
            assert policy.allow_raw_user_text is True
            assert policy.allow_remote_llm is True
            assert policy.allow_remote_embeddings is True
            assert policy.allow_remote_rerank is True
    finally:
        openai_garden.close()
        deepseek_garden.close()
