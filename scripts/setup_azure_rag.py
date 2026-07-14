import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from azure_rag.config import AppConfig
from azure_rag.search_pipeline import setup_pipeline


def main() -> None:
    result = setup_pipeline(AppConfig.from_env())
    last = (result["indexer_status"].get("lastResult") or {})
    print("Indexer status:", last.get("status", "unknown"))
    if last.get("errorMessage"):
        print("Indexer error:", last["errorMessage"])


if __name__ == "__main__":
    main()
