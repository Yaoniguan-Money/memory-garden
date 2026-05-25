import json
import sys
from argparse import Namespace
from io import StringIO

from memory_garden.__main__ import _providers_from_args, main
from memory_garden.product import ProductMemorySystem
from memory_garden.sdk import MemoryGarden
from memory_garden.soil import reindex_garden


def _run_cli(args):
    old = sys.stdout
    try:
        sys.stdout = StringIO()
        rc = main(args)
        output = sys.stdout.getvalue()
    finally:
        sys.stdout = old
    return rc, output


def _json_cli(args):
    rc, output = _run_cli(args)
    assert rc == 0, output
    return json.loads(output)


def test_product_cli_remember_retrieve_inspect_and_forget(tmp_path):
    path = str(tmp_path / "garden")

    remembered = _json_cli(["remember", "remember: prefer dark mode dashboards", "--path", path, "--mode", "trusted"])
    memory_id = remembered["approved_memory_ids"][0]

    memories = _json_cli(["memories", "--path", path])
    assert memories[0]["id"] == memory_id

    retrieved = _json_cli(["retrieve", "dark dashboard", "--path", path])
    assert retrieved["hits"][0]["memory"]["id"] == memory_id
    assert retrieved["hits"][0]["applicability_score"] > 0

    strategy = _json_cli(["strategy", memory_id, "--path", path])
    assert strategy["layer"] == "preference"
    assert strategy["maturity"] in {"observed", "stable", "canonical"}

    applicability = _json_cli(["applicability", memory_id, "dark dashboard", "--path", path])
    assert applicability["allowed"] is True

    inspected = _json_cli(["inspect", memory_id, "--path", path])
    assert inspected["memory"]["id"] == memory_id
    assert inspected["versions"]
    assert inspected["strategy"]["memory_id"] == memory_id

    updated = _json_cli(["update-memory", memory_id, "--path", path, "--title", "Dark dashboards", "--tags", "ui,dashboard"])
    assert updated["title"] == "Dark dashboards"
    assert updated["tags"] == ["ui", "dashboard"]

    archived = _json_cli(["archive-memory", memory_id, "--path", path])
    assert archived["lifecycle"] == "pruned"

    restored = _json_cli(["restore-memory", memory_id, "--path", path])
    assert restored["lifecycle"] == "sprout"

    reinforced = _json_cli(["reinforce-memory", memory_id, "--path", path])
    assert reinforced["use_count"] >= 1

    decay = _json_cli(["decay-memories", "--path", path])
    assert isinstance(decay, list)

    abstractions = _json_cli(["plan-abstractions", "--path", path])
    assert isinstance(abstractions, list)

    plan = _json_cli(["forget-plan", "--memory-id", memory_id, "--path", path])
    assert plan["memory_id"] == memory_id

    executed = _json_cli(["forget-exec", plan["id"], "--path", path])
    assert executed["plan"]["status"] == "executed"
    assert executed["proof"]["proven"] is True


def test_product_cli_proposal_inbox_approve_reject_and_provider_policy(tmp_path):
    path = str(tmp_path / "garden")

    proposals = _json_cli(["propose", "remember: prefer compact lists", "--path", path])
    proposal_id = proposals[0]["id"]

    inbox = _json_cli(["inbox", "--path", path])
    assert any(item["id"] == proposal_id for item in inbox)

    approved = _json_cli(["approve", proposal_id, "--path", path])
    assert approved["id"]

    rejected_prop = _json_cli(["propose", "remember: temporary rejected note", "--path", path])[0]
    rejected = _json_cli(["reject", rejected_prop["id"], "--path", path, "--reason", "not durable"])
    assert rejected["status"] == "rejected"
    assert rejected["metadata"]["reject_reason"] == "not durable"

    providers = _json_cli(["providers"])
    assert "LLMProvider" in providers["provider_interfaces"]
    assert providers["default_policy"]["remote_llm"] == "blocked"


def test_cli_provider_constructor_explicitly_opts_into_remote(monkeypatch):
    import memory_garden.providers as providers_module

    class _RemoteLLM:
        name = "test-llm"
        is_remote = True

        def __init__(self, **_kwargs):
            pass

    class _RemoteEmbedding:
        name = "test-embedding"
        is_remote = True

        def __init__(self, **_kwargs):
            pass

    monkeypatch.setattr(providers_module, "OpenAICompatibleLLMProvider", _RemoteLLM)
    monkeypatch.setattr(providers_module, "OpenAICompatibleEmbeddingProvider", _RemoteEmbedding)

    providers = _providers_from_args(
        Namespace(
            provider="openai",
            api_key="test-key",
            model=None,
            base_url=None,
        )
    )

    assert providers.policy.allow_raw_user_text is True
    assert providers.policy.allow_remote_llm is True
    assert providers.policy.allow_remote_embeddings is True
    assert providers.policy.allow_remote_rerank is True


def test_cli_search_can_filter_by_project_scope(tmp_path):
    path = str(tmp_path / "garden")
    garden = MemoryGarden.local(path)
    try:
        product = ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)
        atlas = product.remember(
            "remember: project search notes prefer rollback details",
            mode="trusted",
            metadata={"project_id": "atlas"},
        )["approved_memory_ids"][0]
        zephyr = product.remember(
            "remember: project search notes prefer customer details",
            mode="trusted",
            metadata={"project_id": "zephyr"},
        )["approved_memory_ids"][0]
        reindex_garden(garden.home.root, dry_run=False)
    finally:
        garden.close()

    rc, output = _run_cli(["search", "search notes", "--path", path, "--project", "atlas"])

    assert rc == 0
    assert "rollback details" in output
    assert "customer details" not in output
