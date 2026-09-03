import json
from pathlib import Path

from demodirector_contracts.schema import CONTRACT_MODELS, build_contract_schema

ROOT = Path(__file__).resolve().parents[3]
SCHEMA_PATH = ROOT / "packages" / "contracts" / "schema" / "contracts.schema.json"


def test_checked_in_json_schema_matches_pydantic_contracts() -> None:
    checked_in_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    generated_schema = build_contract_schema()

    assert checked_in_schema == generated_schema
    assert set(checked_in_schema["x-contracts"]) == {model.__name__ for model in CONTRACT_MODELS}
    assert all(model.__name__ in checked_in_schema["$defs"] for model in CONTRACT_MODELS)
