"""Entity mapping tests: config validation, source-id resolution, geography."""
from __future__ import annotations

import pytest

import common
from common import lookup_model, model_row, resolve_with_unmatched


def test_config_loads_and_validates():
    companies = common.load_companies()
    models = common.load_models()
    assert {"openai", "deepseek", "mistral"} <= set(companies["company_id"])
    assert set(models["weights_status"]) <= {"open", "closed", "unknown"}
    # every model maps to a known company
    assert set(models["company_id"]) <= set(companies["company_id"])


def test_lookup_by_source_id():
    info = lookup_model("openrouter", "openai/gpt-5")
    assert info is not None
    assert info.model_id == "gpt-5"
    assert info.geography == "US"
    assert info.weights_status == "closed"

    info = lookup_model("openrouter", "z-ai/glm-4.6")
    assert info is not None
    assert info.geography == "China"
    assert info.weights_status == "open"

    info = lookup_model("huggingface", "deepseek-ai/DeepSeek-R1")
    assert info is not None
    assert info.company_id == "deepseek"
    assert info.hq_country == "CN"


def test_unknown_source_id_returns_none():
    assert lookup_model("openrouter", "vendor/nonexistent-model") is None
    resolved, unmatched = resolve_with_unmatched(
        "openrouter", ["openai/gpt-5", "vendor/nonexistent-model"])
    assert resolved.keys() == {"openai/gpt-5"}
    assert unmatched == ["vendor/nonexistent-model"]


def test_geography_classification():
    assert model_row("qwen3-235b").geography == "China"
    assert model_row("mistral-large-2411").geography == "EU"
    assert model_row("command-a").geography == "RoW"  # Cohere: Canada
    assert model_row("grok-4").geography == "US"


def test_duplicate_mapping_is_flagged(sandbox, monkeypatch):
    # a mapping that points at a model_id missing from models.csv -> None
    cfg = sandbox / "config"
    with open(cfg / "model_mapping.csv", "a") as fh:
        fh.write("openrouter,broken/mapping,not-a-model\n")
    common.clear_config_cache()
    assert lookup_model("openrouter", "broken/mapping") is None


def test_mapping_to_missing_model_fails_validation(sandbox):
    with open(sandbox / "config" / "models.csv", "a") as fh:
        fh.write("bad-status,Test Model,openai,partially-open\n")
    common.clear_config_cache()
    with pytest.raises(ValueError, match="weights_status"):
        common.load_models()
