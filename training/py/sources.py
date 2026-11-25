"""Pinned third-party sources. Licenses are recorded in THIRD_PARTY_NOTICES.md."""

SOURCES = {
    "nemotron_en": {
        "repo": "nvidia/Nemotron-PII",
        "revision": "b70ffaf5ff39e079776134c5bf4381f00a9fd1ed",
        "files": ["data/train-00000-of-00001.parquet", "data/test-00000-of-00001.parquet"],
        "license": "CC-BY-4.0",
    },
    "openpii": {
        "repo": "ai4privacy/pii-masking-openpii-1.5m",
        "revision": "a785eb528e28be2693c3718a27e066970de5dadb",
        # train.jsonl (4.3 GB) is streamed and only zh / en rows are kept.
        "files": ["data/validation.jsonl", "data/train.jsonl"],
        "license": "CC-BY-4.0",
    },
    "redactionbench": {
        "repo": "RedactionBench/RedactionBench",
        "revision": "77684d7ea74207e6086ae3a05f46ddc69ca753d2",
        # untyped en redaction benchmark scored with its own R-Score; evaluation only
        "files": ["data/documents.ndjson", "score.py", "rscore_v2_product.py", "rscore_v2.py"],
        "license": "CC-BY-4.0",
    },
    "gretel_fin": {
        "repo": "gretelai/synthetic_pii_finance_multilingual",
        "revision": "7b844d16738527a04264f50214cb426a4cea0897",
        "files": ["data/English_train-00000-of-00001.parquet", "data/English_test-00000-of-00001.parquet"],
        "license": "Apache-2.0",
    },
    "pii_bench_zh": {
        "repo": "wan9yu/pii-bench-zh",
        "revision": "c350b94897af668517ff5de237d89f2ce2eaa6f0",
        "files": ["data/pii_bench_zh.jsonl", "data/pii_bench_zh_chat.jsonl"],
        "license": "Apache-2.0 (card: research and evaluation use)",
    },
}
