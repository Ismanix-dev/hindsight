"""The provider driven through the Hermes MemoryProvider interface, asserting what it
sends to Hindsight (a recording fake client stands in for the real SDK)."""

import json

import hindsight_hermes as plugin
from conftest import FakeClient


def _retain_item(fake: FakeClient, index: int = 0) -> dict:
    return fake.retains[index]["items"][0]


def _turns_of(fake: FakeClient, index: int = 0) -> list[list[str]]:
    """Message texts per turn in one retain. Content is ``"[" + ",".join(turns) + "]"``
    where each turn is itself a JSON array, so the whole payload is a list of turns."""
    return [[m["content"] for m in turn] for turn in json.loads(_retain_item(fake, index)["content"])]


def test_sync_turn_retains_the_turn(provider):
    instance, fake = provider({"bank_id": "team", "retain_tags": "hermes"})
    instance.sync_turn("what is my name?", "Ada.")
    instance.shutdown()

    assert len(fake.retains) == 1
    call = fake.retains[0]
    assert call["bank_id"] == "team"
    assert call["document_id"] == "session-1"  # stable id + append on a capable API
    item = _retain_item(fake)
    assert item["update_mode"] == "append"
    assert "hermes" in item["tags"] and not any(t.startswith("session:") for t in item["tags"])
    # Session lineage is metadata-only (audit data), never a tag.
    assert item["metadata"]["session_id"] == "session-1"
    messages = json.loads(item["content"][1:-1])
    assert [m["content"] for m in messages] == ["User: what is my name?", "Assistant: Ada."]


def test_retain_every_n_turns_buffers_then_ships_the_batch(provider):
    instance, fake = provider({"retain_every_n_turns": 2})
    instance.sync_turn("one", "1")
    assert fake.retains == []
    instance.sync_turn("two", "2")
    instance.shutdown()

    assert len(fake.retains) == 1
    assert _retain_item(fake)["metadata"]["message_count"] == "4"


def test_auto_retain_off_stores_nothing(provider):
    instance, fake = provider({"auto_retain": False})
    instance.sync_turn("hello", "hi")
    instance.shutdown()
    assert fake.retains == []


def test_recall_tool_queries_the_bank_and_formats_results(provider):
    instance, fake = provider(
        {"bank_id": "team", "recall_budget": "high"}, client=FakeClient(recall_texts=["fact one", "fact two"])
    )
    result = json.loads(instance.handle_tool_call("hindsight_recall", {"query": "who am I?"}))

    assert fake.recalls[0]["bank_id"] == "team"
    assert fake.recalls[0]["budget"] == "high"
    assert fake.recalls[0]["types"] == ["observation"]  # observation-only default
    assert result["result"] == "1. fact one\n2. fact two"
    instance.shutdown()


def test_reflect_tool_uses_reflect(provider):
    instance, fake = provider({}, client=FakeClient(reflect_text="You are Ada."))
    result = json.loads(instance.handle_tool_call("hindsight_reflect", {"query": "who am I?"}))
    assert fake.reflects[0]["query"] == "who am I?"
    assert result["result"] == "You are Ada."
    instance.shutdown()


def test_retain_tool_stores_content_with_per_call_tags(provider):
    instance, fake = provider({"retain_tags": "base"})
    instance.handle_tool_call("hindsight_retain", {"content": "Ada likes tea", "tags": ["drink"]})
    item = _retain_item(fake)
    assert item["content"] == "Ada likes tea"
    assert item["tags"] == ["base", "drink"]
    instance.shutdown()


def test_tool_call_errors_are_reported_not_raised(provider):
    instance, _ = provider({})
    assert instance.handle_tool_call("hindsight_recall", {}).startswith("ERROR:")
    assert instance.handle_tool_call("nope", {"query": "x"}).startswith("ERROR:")
    instance.shutdown()


def test_prefetch_injects_recalled_memories(provider):
    instance, fake = provider({"recall_sync": True}, client=FakeClient(recall_texts=["fact one"]))
    block = instance.prefetch("what do you know?")
    assert "- fact one" in block
    status = instance.recall_status()
    assert status.count == 1 and status.provider_label == "Hindsight"
    instance.shutdown()


def test_context_mode_hides_tools_tools_mode_skips_recall(provider):
    context_only, _ = provider({"memory_mode": "context"})
    assert context_only.get_tool_schemas() == []
    context_only.shutdown()

    tools_only, fake = provider({"memory_mode": "tools", "recall_sync": True})
    assert [t["name"] for t in tools_only.get_tool_schemas()] == [
        "hindsight_retain",
        "hindsight_recall",
        "hindsight_reflect",
        # Halo fork additions (layers 3b/3c): management + knowledge tools.
        "hindsight_list_memories",
        "hindsight_get_memory",
        "hindsight_update_memory",
        "hindsight_invalidate_memory",
        "hindsight_get_knowledge_base_tree",
        "hindsight_search_knowledge_base",
        "hindsight_get_knowledge_page",
        "hindsight_create_knowledge_folder",
        "hindsight_create_knowledge_page",
        "hindsight_update_knowledge_node",
        "hindsight_delete_knowledge_node",
    ]
    assert tools_only.prefetch("anything") == ""
    assert fake.recalls == []
    tools_only.shutdown()


def test_session_switch_starts_a_new_document(provider):
    instance, fake = provider({})
    instance.sync_turn("one", "1")
    instance.on_session_switch("session-2", reset=True)
    instance.sync_turn("two", "2")
    instance.shutdown()

    # The switch flushes the old session's buffer under the old document id first,
    # so the new session's turn can never land in the previous document. In append
    # mode the buffer is already empty here (sync_turn shipped and dropped the turn),
    # so there is nothing left to flush — previously this re-shipped the retained
    # turn under session-1 a second time, duplicating it in the document.
    assert [call["document_id"] for call in fake.retains] == ["session-1", "session-2"]


def test_register_exposes_the_provider_to_hermes():
    registered = []
    plugin.register(type("Ctx", (), {"register_memory_provider": lambda _self, p: registered.append(p)})())
    assert registered and registered[0].name == "hindsight"


def test_append_mode_drops_retained_turns_from_the_buffer(provider):
    """Append retains ship a delta, so keeping every turn would pin the whole session
    in memory on a long-running gateway (hermes-agent #62950).

    Append mode comes from the API capability probe, which the fixture pins on — it is
    not a config key.
    """
    instance, fake = provider({})
    instance.sync_turn("one", "1")
    instance.sync_turn("two", "2")

    # Buffer state is read before shutdown(); retains only land once the writer drains.
    assert instance._session_turns == []
    assert instance._last_retained_turn_count == 0
    instance.shutdown()

    # Each retain still carries only its own un-retained tail, never a replay.
    assert _turns_of(fake, 0) == [["User: one", "Assistant: 1"]]
    assert _turns_of(fake, 1) == [["User: two", "Assistant: 2"]]


def test_overwrite_mode_keeps_every_turn(provider, monkeypatch):
    """Overwrite resends the full session on each retain, so its buffer must NOT be
    cleared — only the append path drops shipped turns."""
    instance, fake = provider({})
    # An API without update_mode='append' support: the fixture pins the probe on, so
    # turn it back off to exercise the overwrite path.
    monkeypatch.setattr(plugin, "_check_api_supports_update_mode_append", lambda *a, **k: False)
    instance.sync_turn("one", "1")
    instance.sync_turn("two", "2")

    assert len(instance._session_turns) == 2  # one buffered entry per turn
    instance.shutdown()

    # The second retain resends the whole session, which is what overwrite means.
    assert _turns_of(fake, 1) == [["User: one", "Assistant: 1"], ["User: two", "Assistant: 2"]]


def test_root_warning_goes_through_the_hosts_warning_callback(provider, monkeypatch):
    """The 'cannot run as root' notice is an automatic startup diagnostic: hosts that
    wire a gated sink must receive it there, not on stderr (hermes-agent cd3de040ab9)."""
    seen = []
    instance, _ = provider({}, warning_callback=seen.append, platform="telegram")
    assert instance._platform == "telegram"

    monkeypatch.setattr(plugin.os, "geteuid", lambda: 0, raising=False)
    instance._mode = "local_embedded"
    instance._start_embedded_daemon()

    assert len(seen) == 1 and "cannot run as root" in seen[0]
    assert instance._mode == "disabled"
    instance.shutdown()


def test_warning_sink_defaults_exist_without_initialize():
    """_start_embedded_daemon reads these directly, and availability probes construct a
    provider without ever calling initialize() — so __init__ must supply both."""
    bare = plugin.HindsightMemoryProvider()
    assert bare._warning_callback is None
    assert bare._platform == "cli"


# -- retain strategy (bank-scoped) ---------------------------------------------


def test_retain_sends_configured_strategy(provider):
    """A configured strategy ships as an item field so the bank resolves that
    retain_strategies entry instead of its default."""
    instance, fake = provider({"strategy": "raz"})
    instance.sync_turn("frage", "antwort")
    instance.shutdown()

    assert _retain_item(fake)["strategy"] == "raz"


def test_absent_strategy_sends_no_key(provider):
    """No configured strategy -> no item key, so the bank default applies."""
    instance, fake = provider({})
    instance.sync_turn("frage", "antwort")
    instance.shutdown()

    assert "strategy" not in _retain_item(fake)


def test_standard_is_normalized_away(provider):
    """``standard`` is the built-in "no named strategy" selector; the server has no
    such key, so it must not be shipped (it would log a warning per retain)."""
    instance, fake = provider({"strategy": "standard"})
    instance.sync_turn("frage", "antwort")
    instance.shutdown()

    assert instance._retain_strategy == ""
    assert "strategy" not in _retain_item(fake)


def test_unknown_strategy_blocks_retain(provider):
    """An unknown key fails loudly and aborts every retain instead of silently
    falling back to the bank default."""
    instance, fake = provider({"strategy": "bogus"})
    instance.sync_turn("frage", "antwort")
    instance.shutdown()

    assert fake.retains == []
    assert "unknown retain strategy" in instance._retain_strategy_error


def test_bank_defined_strategy_is_accepted(provider):
    """A strategy that exists on the bank works without a client change: the bank
    widens the built-in list (union), resolved on the shipping path."""
    instance, fake = provider(
        {"strategy": "bibelforschung"},
        client=FakeClient(retain_strategies={"bibelforschung": {"retain_mission": "x"}}),
    )
    instance.sync_turn("frage", "antwort")
    instance.shutdown()

    assert _retain_item(fake)["strategy"] == "bibelforschung"
    assert fake.bank_config_calls  # the bank was actually consulted


def test_standard_survives_a_bank_that_defines_only_raz(provider):
    """Regression: the built-in list is the UNION with the bank keys, not a
    replacement. Otherwise the bank's first own strategy would invalidate
    ``standard`` and break every other profile's retain."""
    instance, fake = provider(
        {"strategy": "standard"},
        client=FakeClient(retain_strategies={"raz": {"retain_mission": "x"}}),
    )
    instance.sync_turn("frage", "antwort")
    instance.shutdown()

    assert fake.retains  # standard stayed valid
    assert "strategy" not in _retain_item(fake)
