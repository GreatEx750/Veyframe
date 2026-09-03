from pathlib import Path

from demodirector_contracts.schema import write_contract_schema

ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    write_contract_schema(ROOT / "packages" / "contracts" / "schema" / "contracts.schema.json")
