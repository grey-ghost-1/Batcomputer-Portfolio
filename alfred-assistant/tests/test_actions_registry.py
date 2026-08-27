"""Action registry: catalog, canonical hashing, and payload validation."""

from __future__ import annotations

import pytest
from alfred.actions import registry
from alfred.actions.executors import ActionError
from alfred.schemas import CreateFolderPayload

ALL_ACTION_TYPES = {
    "create_folder",
    "move_file",
    "organize_folder",
    "open_app",
    "open_url",
    "set_clipboard",
}


def test_registry_declares_exactly_the_six_typed_actions():
    assert set(registry.SPECS.keys()) == ALL_ACTION_TYPES


def test_catalog_lists_every_action_with_a_json_schema(settings_factory):
    settings = settings_factory()
    catalog = registry.catalog(settings)
    assert {item["action_type"] for item in catalog} == ALL_ACTION_TYPES
    for item in catalog:
        assert "payload_schema" in item
        assert "properties" in item["payload_schema"]
        assert isinstance(item["description"], str) and item["description"]


def test_catalog_execution_enabled_reflects_desktop_flag(settings_factory):
    disabled = settings_factory(desktop_actions_enabled=False)
    catalog = registry.catalog(disabled)
    by_type = {item["action_type"]: item for item in catalog}
    assert by_type["create_folder"]["execution_enabled"] is False

    enabled = settings_factory(desktop_actions_enabled=True)
    catalog = registry.catalog(enabled)
    by_type = {item["action_type"]: item for item in catalog}
    assert by_type["create_folder"]["execution_enabled"] is True


def test_catalog_set_clipboard_requires_both_desktop_and_clipboard_flags(settings_factory):
    desktop_only = settings_factory(desktop_actions_enabled=True, clipboard_enabled=False)
    by_type = {item["action_type"]: item for item in registry.catalog(desktop_only)}
    assert by_type["set_clipboard"]["execution_enabled"] is False

    both = settings_factory(desktop_actions_enabled=True, clipboard_enabled=True)
    by_type = {item["action_type"]: item for item in registry.catalog(both)}
    assert by_type["set_clipboard"]["execution_enabled"] is True


def test_get_spec_unknown_action_raises_key_error():
    with pytest.raises(KeyError):
        registry.get_spec("delete_everything")


def test_validate_payload_rejects_wrong_shape():
    with pytest.raises(ActionError):
        registry.validate_payload("create_folder", {"name": 12345})


def test_validate_payload_accepts_well_formed_payload():
    model = registry.validate_payload("create_folder", {"name": "Reports"})
    assert isinstance(model, CreateFolderPayload)
    assert model.name == "Reports"
    assert model.root == 0


def test_canonical_payload_is_deterministic_regardless_of_key_order():
    model_a = registry.validate_payload("create_folder", {"root": 0, "name": "X", "parent": "."})
    model_b = registry.validate_payload("create_folder", {"name": "X", "parent": ".", "root": 0})
    assert registry.canonical_payload("create_folder", model_a) == registry.canonical_payload(
        "create_folder", model_b
    )


def test_payload_hash_changes_when_payload_changes():
    model_a = registry.validate_payload("create_folder", {"name": "X"})
    model_b = registry.validate_payload("create_folder", {"name": "Y"})
    hash_a = registry.payload_hash(registry.canonical_payload("create_folder", model_a))
    hash_b = registry.payload_hash(registry.canonical_payload("create_folder", model_b))
    assert hash_a != hash_b


def test_payload_hash_is_a_stable_sha256_hex_digest():
    model = registry.validate_payload("create_folder", {"name": "X"})
    digest = registry.payload_hash(registry.canonical_payload("create_folder", model))
    assert len(digest) == 64
    int(digest, 16)  # must be valid hex


def test_execution_enabled_true_when_no_flags_required(settings_factory):
    settings = settings_factory(desktop_actions_enabled=True)
    spec = registry.get_spec("create_folder")
    assert registry.execution_enabled(settings, spec) is True
