from azure_rag.config import AppConfig
from azure_rag.search_pipeline import setup_pipeline


def main():
    result = setup_pipeline(AppConfig.from_env())
    last = (result["indexer_status"].get("lastResult") or {})
    print("Indexer status:", last.get("status", "unknown"))


if __name__ == "__main__":
    main()
