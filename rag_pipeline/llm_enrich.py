"""LLM 기반 YAML 엔트리 enrichment.

regex 대신 Claude를 사용하여 한국어 핵심 용어, 질문 변형, 키워드를 추출합니다.
결과는 data/RAG/<dataset>_yaml/enriched/ 에 JSON으로 캐싱됩니다.

사용법:
    # 전체 enrichment (캐시에 없는 항목만 처리)
    uv run python rag_pipeline/llm_enrich.py --dataset refrigerator

    # 강제 재생성 (캐시 무시)
    uv run python rag_pipeline/llm_enrich.py --dataset refrigerator --force

    # 특정 카테고리만
    uv run python rag_pipeline/llm_enrich.py --dataset refrigerator --category glossary

    # dry-run (프롬프트만 확인)
    uv run python rag_pipeline/llm_enrich.py --dataset refrigerator --dry-run --category glossary
"""

import argparse
import json
import os
import re
import sys
import time

import boto3
import yaml

# Add project root to path for prompt template imports
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(CURRENT_DIR, "..")
sys.path.insert(0, os.path.join(PROJECT_ROOT, "src"))

from ops_agent.prompts.template import PromptTemplateLoader

DATASETS_CONFIG = os.path.join(CURRENT_DIR, "datasets.yaml")

# Bedrock model
MODEL_ID = "global.anthropic.claude-sonnet-4-5-20250929-v1:0"
AWS_REGION = "us-east-1"

# Load prompt template from src/ops_agent/prompts/kb_enrichment.md
_loader = PromptTemplateLoader()
_template = _loader.load("kb_enrichment")


def load_dataset_config(dataset_name):
    """datasets.yaml에서 데이터셋 설정 로드."""
    with open(DATASETS_CONFIG) as f:
        config = yaml.safe_load(f)
    datasets = config.get("datasets", {})
    if dataset_name not in datasets:
        available = ", ".join(datasets.keys())
        raise ValueError(f"Unknown dataset: {dataset_name}. Available: {available}")
    return datasets[dataset_name]


def load_yaml_entries(yaml_dir, category_filter=None):
    """모든 YAML 카테고리 파일에서 엔트리를 로드."""
    with open(os.path.join(yaml_dir, "index.yaml")) as f:
        index = yaml.safe_load(f)

    all_entries = []
    for cat in index["categories"]:
        if category_filter and cat["id"] != category_filter:
            continue
        cat_path = os.path.join(yaml_dir, f"{cat['id']}.yaml")
        with open(cat_path) as f:
            data = yaml.safe_load(f)
        for entry in data["entries"]:
            entry["category_id"] = data["category_id"]
            entry["category_name"] = data["category_name"]
            all_entries.append(entry)

    return all_entries


def call_bedrock(prompt, client):
    """Bedrock Claude API 호출."""
    response = client.converse(
        modelId=MODEL_ID,
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        inferenceConfig={"temperature": 0.0, "maxTokens": 1024},
    )
    return response["output"]["message"]["content"][0]["text"]


def parse_llm_response(text):
    """LLM 응답에서 JSON 추출."""
    text = text.strip()

    # Remove markdown code fence if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    # Fix unescaped backslashes BEFORE JSON parsing
    # (e.g. Windows paths like Phone\Download\log)
    text = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', text)

    # Fix trailing commas in arrays/objects (e.g. ["a", "b",] → ["a", "b"])
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # Extract first complete JSON object using raw_decode (ignores trailing text)
    # If parsing fails due to bad escapes, fix them iteratively at the reported position
    start = text.find("{")
    if start != -1:
        for _ in range(10):  # max 10 escape fixes
            try:
                decoder = json.JSONDecoder()
                result, _ = decoder.raw_decode(text, start)
                return result
            except json.JSONDecodeError as e:
                if "bad escape" in str(e) and e.pos is not None:
                    # Double the backslash at the exact failing position
                    text = text[: e.pos] + "\\" + text[e.pos :]
                else:
                    break

    return json.loads(text)


def enrich_entry(entry, client, stop_words, siblings=None, total_docs=107, dry_run=False):
    """단일 엔트리에 대해 LLM enrichment 실행."""
    sibling_str = "없음"
    if siblings:
        sibling_titles = [f"- {s['id']}: {s['title']}" for s in siblings if s['id'] != entry['id']]
        sibling_str = "\n".join(sibling_titles[:10]) if sibling_titles else "없음"

    prompt = _template.render(
        title=entry["title"],
        category=entry["category_name"],
        answer=entry["answer"][:1500].replace("\\", "\\\\"),
        keywords=", ".join(entry.get("keywords", [])),
        error_codes=", ".join(entry.get("error_codes", [])) or "없음",
        siblings=sibling_str,
        total_docs=str(total_docs),
        stop_words=stop_words,
    )

    if dry_run:
        print(f"\n{'='*60}")
        print(f"Entry: {entry['id']}")
        print(f"{'='*60}")
        print(prompt[:500])
        print("...")
        return None

    response_text = call_bedrock(prompt, client)
    enriched = parse_llm_response(response_text)

    # Validate required fields
    required = ["ko_core_term", "en_core_term", "ko_nouns", "question_variants", "search_keywords"]
    for field in required:
        if field not in enriched:
            raise ValueError(f"Missing field: {field}")

    return enriched


def main():
    parser = argparse.ArgumentParser(description="LLM 기반 엔트리 enrichment")
    parser.add_argument("--dataset", default="refrigerator", help="데이터셋 이름")
    parser.add_argument("--force", action="store_true", help="캐시 무시하고 전체 재생성")
    parser.add_argument("--category", type=str, default=None, help="특정 카테고리만 처리")
    parser.add_argument("--dry-run", action="store_true", help="프롬프트만 확인 (API 호출 안함)")
    args = parser.parse_args()

    ds_config = load_dataset_config(args.dataset)
    yaml_dir = os.path.join(PROJECT_ROOT, ds_config["yaml_dir"])
    enriched_dir = os.path.join(yaml_dir, "enriched")
    stop_words = ds_config.get("stop_words", "")

    if not os.path.exists(yaml_dir):
        print(f"ERROR: YAML 디렉토리가 없습니다: {yaml_dir}")
        print(f"먼저 convert_md_to_yaml.py --dataset {args.dataset} 를 실행하세요.")
        return

    if not stop_words:
        print(f"WARNING: stop_words가 설정되지 않았습니다 (datasets.yaml → {args.dataset})")
        print("  LLM enrichment 품질이 저하될 수 있습니다. datasets.yaml에 stop_words를 설정하세요.")

    entries = load_yaml_entries(yaml_dir, category_filter=args.category)
    os.makedirs(enriched_dir, exist_ok=True)

    # Group entries by category for sibling context
    by_category = {}
    for entry in entries:
        cat = entry["category_id"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(entry)

    total_docs = len(entries)

    print("=" * 60)
    print(f"LLM Enrichment v3 (Model: {MODEL_ID})")
    print(f"데이터셋: {args.dataset}")
    print(f"엔트리: {total_docs}개, 카테고리: {len(by_category)}개")
    print(f"캐시 디렉토리: {enriched_dir}")
    print(f"강제 재생성: {args.force}")
    print("=" * 60)

    if args.dry_run:
        for entry in entries[:3]:
            siblings = by_category.get(entry["category_id"], [])
            enrich_entry(entry, None, stop_words, siblings=siblings, total_docs=total_docs, dry_run=True)
        print(f"\n[dry-run] 처음 3개 엔트리의 프롬프트만 표시했습니다.")
        return

    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    success = 0
    skipped = 0
    failed = 0

    for i, entry in enumerate(entries):
        entry_id = entry["id"]
        cache_path = os.path.join(enriched_dir, f"{entry_id}.json")

        # Skip if cached (unless --force)
        if os.path.exists(cache_path) and not args.force:
            skipped += 1
            continue

        try:
            siblings = by_category.get(entry["category_id"], [])
            enriched = enrich_entry(entry, client, stop_words, siblings=siblings, total_docs=total_docs)

            # Save to cache
            with open(cache_path, "w") as f:
                json.dump(enriched, f, ensure_ascii=False, indent=2)

            success += 1
            print(f"  [{i+1}/{len(entries)}] {entry_id}: {enriched['ko_core_term']} / {enriched['en_core_term']}")

        except Exception as e:
            failed += 1
            print(f"  [{i+1}/{len(entries)}] {entry_id}: FAILED — {e}")

        # Rate limiting: ~5 calls/sec to avoid throttling
        time.sleep(0.2)

    print(f"\n{'=' * 60}")
    print(f"완료: 성공={success}, 스킵={skipped}, 실패={failed}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
