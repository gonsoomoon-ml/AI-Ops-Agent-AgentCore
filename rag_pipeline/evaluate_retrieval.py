"""Bedrock KB 검색 정확도 평가.

데이터셋별 테스트 케이스로 HYBRID 검색 (vector + BM25) 정확도를 평가합니다.

사용법:
    uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator
    uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --verbose
    uv run python rag_pipeline/evaluate_retrieval.py --dataset refrigerator --filter
"""

import argparse
import json
import os
import sys

import boto3
import yaml

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DATASETS_CONFIG = os.path.join(CURRENT_DIR, "datasets.yaml")


def load_dataset_config(dataset_name):
    """datasets.yaml에서 데이터셋 설정 로드."""
    with open(DATASETS_CONFIG) as f:
        config = yaml.safe_load(f)
    datasets = config.get("datasets", {})
    if dataset_name not in datasets:
        available = ", ".join(datasets.keys())
        raise ValueError(f"Unknown dataset: {dataset_name}. Available: {available}")
    return datasets[dataset_name]


# ─── Test Cases ──────────────────────────────────────────────────────────────
# Each test: (query, expected_doc_id, category, description)
# expected_doc_id can be a string or list of acceptable IDs

TEST_CASES = [
    # ── Diagnostics: Error Codes ──────────────────────────────────────────
    ("에러 코드 22E가 뭐야?",
     ["diagnostics-002", "diagnostics-001"], "diagnostics",
     "에러 코드 의미 질문 (22E)"),

    ("84C 에러 원인",
     ["diagnostics-002"], "diagnostics",
     "에러 코드 의미 질문 (84C - 컴프레서)"),

    ("5E 에러 코드 해결 방법",
     ["diagnostics-002", "diagnostics-001"], "diagnostics",
     "에러 코드 해결 질문 (5E)"),

    ("냉장고 디스플레이에 39E가 떠요",
     ["diagnostics-002", "diagnostics-001"], "diagnostics",
     "사용자 자연어 에러 보고 (39E)"),

    ("에러 코드 목록 전체 알려줘",
     ["diagnostics-002"], "diagnostics",
     "에러 코드 전체 목록 요청"),

    # ── Diagnostics: Self-diagnosis ───────────────────────────────────────
    ("자가진단 모드 진입 방법",
     ["diagnostics-003"], "diagnostics",
     "자가진단 모드 진입"),

    ("서비스 모드 어떻게 들어가?",
     ["diagnostics-003", "diagnostics-001"], "diagnostics",
     "서비스 모드 (자연어)"),

    ("센서 로그 확보하는 방법",
     ["diagnostics-004"], "diagnostics",
     "센서 로그 확보"),

    # ── Firmware Update ───────────────────────────────────────────────────
    ("펌웨어 업데이트가 뭐야?",
     ["firmware_update-001"], "firmware_update",
     "OTA 펌웨어 개념 질문"),

    ("펌웨어 업데이트 실패하면 어떻게 해?",
     ["firmware_update-005"], "firmware_update",
     "업데이트 실패 대응"),

    ("Wi-Fi 요구사항이 뭐야? 펌웨어 업데이트하려면",
     ["firmware_update-003"], "firmware_update",
     "Wi-Fi 요구사항"),

    ("자동 업데이트랑 수동 업데이트 차이",
     ["firmware_update-004"], "firmware_update",
     "Auto vs Manual update"),

    ("펌웨어 업데이트하면 설정이 초기화돼?",
     ["firmware_update-009"], "firmware_update",
     "업데이트 후 설정 유지 여부"),

    ("Family Hub 소프트웨어 업데이트",
     ["firmware_update-010"], "firmware_update",
     "Family Hub 디스플레이 업데이트"),

    # ── Glossary ──────────────────────────────────────────────────────────
    ("인버터가 뭐야?",
     ["glossary-001"], "glossary",
     "인버터 정의"),

    ("컴프레서가 뭐야?",
     ["glossary-002"], "glossary",
     "컴프레서 정의"),

    ("냉매가 뭐야?",
     ["glossary-003"], "glossary",
     "냉매 정의"),

    ("비스포크가 뭔가요?",
     ["glossary-006"], "glossary",
     "BESPOKE 정의"),

    ("제상이 뭐야?",
     ["glossary-020"], "glossary",
     "Defrost 정의"),

    ("전환실이 뭐야?",
     ["glossary-021"], "glossary",
     "Convertible Room 정의"),

    ("SmartThings가 뭐야?",
     ["glossary-014"], "glossary",
     "SmartThings 정의"),

    ("Family Hub가 뭐야?",
     ["glossary-013"], "glossary",
     "Family Hub 정의"),

    ("급속냉동이 뭐야?",
     ["glossary-015"], "glossary",
     "Power Freeze 정의"),

    ("R-600a 냉매가 뭐야?",
     ["glossary-022"], "glossary",
     "R-600a 냉매 (구체적 용어)"),

    # ── Model Matching ────────────────────────────────────────────────────
    ("모델번호 체계 설명해줘",
     ["model_matching-002", "glossary-019"], "model_matching",
     "모델번호 체계"),

    ("시리얼번호 구조 알려줘",
     ["model_matching-003"], "model_matching",
     "시리얼번호 구조"),

    ("부품 호환성 확인 방법",
     ["model_matching-004", "service_portal-008"], "model_matching",
     "부품 호환성 매칭"),

    ("명판 위치가 어디야?",
     ["model_matching-007"], "model_matching",
     "Rating Plate 위치"),

    ("색상 코드 체계 알려줘",
     ["model_matching-006"], "model_matching",
     "색상 코드"),

    # ── Product Line ──────────────────────────────────────────────────────
    ("양문형 냉장고가 뭐야?",
     ["product_line-001"], "product_line",
     "Side-by-Side 설명"),

    ("김치냉장고 설명해줘",
     ["product_line-005"], "product_line",
     "김치냉장고"),

    ("비스포크 냉장고 특징",
     ["product_line-004"], "product_line",
     "BESPOKE 냉장고"),

    ("빌트인 냉장고가 뭐야?",
     ["product_line-006"], "product_line",
     "Built-in 냉장고"),

    ("냉장고 종류별 추천",
     ["product_line-012"], "product_line",
     "제품군별 선택 가이드"),

    ("와인셀러 설명해줘",
     ["product_line-010"], "product_line",
     "Wine Cellar"),

    # ── Service Portal ────────────────────────────────────────────────────
    ("서비스 포털 권한 요청 방법",
     ["service_portal-001"], "service_portal",
     "Role 권한 획득"),

    ("부품 주문은 어떻게 해?",
     ["service_portal-004"], "service_portal",
     "부품 주문 절차"),

    ("A/S 접수 방법",
     ["service_portal-005"], "service_portal",
     "A/S 접수"),

    ("보증기간 확인 방법",
     ["service_portal-006"], "service_portal",
     "보증기간 확인"),

    ("서비스 매뉴얼 다운로드",
     ["service_portal-010"], "service_portal",
     "서비스 매뉴얼"),

    ("에러코드 조회 방법 서비스 포털",
     ["service_portal-009"], "service_portal",
     "Service Portal 에러코드 조회"),

    # ── Smart Feature ─────────────────────────────────────────────────────
    ("AI Energy Mode 설명해줘",
     ["smart_feature-003"], "smart_feature",
     "AI Energy Mode"),

    ("식품관리 카메라가 뭐야?",
     ["smart_feature-004"], "smart_feature",
     "Food Camera"),

    ("원격 온도 제어 기능",
     ["smart_feature-006"], "smart_feature",
     "원격 온도 제어"),

    ("도어 열림 알림 기능",
     ["smart_feature-008"], "smart_feature",
     "Door Open Alert"),

    ("필터 교체 알림",
     ["smart_feature-009"], "smart_feature",
     "Filter Replacement Alert"),

    ("휴가모드가 뭐야?",
     ["smart_feature-010"], "smart_feature",
     "Vacation Mode"),

    # ── SmartThings Portal ────────────────────────────────────────────────
    ("SmartThings에서 냉장고 등록 방법",
     ["smartthings_portal-001", "smart_feature-002"], "smartthings_portal",
     "기기 등록"),

    ("SmartThings 알림 설정",
     ["smartthings_portal-002"], "smartthings_portal",
     "알림 설정"),

    ("SmartThings 자동화 설정",
     ["smartthings_portal-007"], "smartthings_portal",
     "Automation 설정"),

    ("SmartThings 앱에서 냉장고가 안 보여요",
     ["smartthings_portal-016"], "smartthings_portal",
     "기기 검색 안 됨 (QnA)"),

    ("SmartThings 연결이 자꾸 끊겨요",
     ["smartthings_portal-017"], "smartthings_portal",
     "연결 끊김 (QnA)"),

    ("SmartThings 계정 변경하고 싶어요",
     ["smartthings_portal-018"], "smartthings_portal",
     "계정 변경 (QnA)"),

    ("SmartThings 온도가 실제랑 달라요",
     ["smartthings_portal-019"], "smartthings_portal",
     "온도 표시 불일치 (QnA)"),

    ("SmartThings 기기 초기화 방법",
     ["smartthings_portal-009"], "smartthings_portal",
     "기기 초기화"),

    # ── Cross-category / Ambiguous ────────────────────────────────────────
    ("에너지 절약하는 방법 알려줘",
     ["smart_feature-003", "glossary-016", "smart_feature-007"], "cross",
     "에너지 절약 (여러 카테고리 가능)"),

    ("냉장고 온도가 이상해요",
     ["smartthings_portal-019", "diagnostics-001", "diagnostics-003"], "cross",
     "온도 이상 (자연어, 모호한 질문)"),

    ("냉장고 Wi-Fi 연결 안돼요",
     ["smartthings_portal-016", "smartthings_portal-017", "firmware_update-003"], "cross",
     "Wi-Fi 문제 (여러 원인 가능)"),
]


def get_kb_id(ds_config):
    """datasets.yaml 또는 SSM에서 KB ID 조회."""
    kb_id = ds_config.get("kb_id", "")
    if kb_id:
        return kb_id

    # Fallback: SSM lookup
    kb_name = ds_config.get("kb_name", "")
    if not kb_name:
        raise ValueError("datasets.yaml에 kb_id 또는 kb_name이 설정되지 않았습니다.")
    ssm = boto3.client("ssm")
    return ssm.get_parameter(Name=f"{kb_name}-kb-id")["Parameter"]["Value"]


def query_kb(client, kb_id, query, num_results=5, category_filter=None):
    """KB에 HYBRID 검색 쿼리 실행. category_filter가 있으면 메타데이터 필터 적용."""
    vector_config = {
        "numberOfResults": num_results,
        "overrideSearchType": "HYBRID",
    }
    if category_filter:
        vector_config["filter"] = {
            "equals": {"key": "category", "value": category_filter}
        }
    response = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": vector_config},
    )
    results = []
    for r in response.get("retrievalResults", []):
        source_uri = r.get("metadata", {}).get("x-amz-bedrock-kb-source-uri", "")
        # Extract doc ID from s3://bucket/doc_id.md
        doc_id = source_uri.split("/")[-1].replace(".md", "") if source_uri else "unknown"
        results.append({
            "doc_id": doc_id,
            "score": r.get("score", 0),
            "text": r.get("content", {}).get("text", "")[:200],
        })
    return results


def evaluate_result(results, expected_ids):
    """결과 평가: top-1, top-3, top-5 정확도."""
    if isinstance(expected_ids, str):
        expected_ids = [expected_ids]

    result_ids = [r["doc_id"] for r in results]

    top1 = result_ids[0] in expected_ids if result_ids else False
    top3 = any(rid in expected_ids for rid in result_ids[:3])
    top5 = any(rid in expected_ids for rid in result_ids[:5])

    return top1, top3, top5


def main():
    parser = argparse.ArgumentParser(description="KB 검색 정확도 평가")
    parser.add_argument("--dataset", default="refrigerator", help="데이터셋 이름")
    parser.add_argument("--verbose", action="store_true", help="상세 출력")
    parser.add_argument("--category", type=str, default=None, help="특정 카테고리만 테스트")
    parser.add_argument("--filter", action="store_true", help="카테고리 메타데이터 필터 적용")
    args = parser.parse_args()

    ds_config = load_dataset_config(args.dataset)
    kb_id = get_kb_id(ds_config)
    client = boto3.client("bedrock-agent-runtime")

    print("=" * 70)
    filter_label = " + Category Filter" if args.filter else ""
    print(f"Bedrock KB 검색 정확도 평가 [{args.dataset}] (HYBRID Search{filter_label})")
    print(f"KB ID: {kb_id}")
    print(f"테스트 케이스: {len(TEST_CASES)}개")
    print("=" * 70)

    # Filter by category if specified
    cases = TEST_CASES
    if args.category:
        cases = [c for c in cases if c[2] == args.category]
        print(f"카테고리 필터: {args.category} ({len(cases)}개)")

    # Run tests
    results_summary = {
        "total": 0,
        "top1_correct": 0,
        "top3_correct": 0,
        "top5_correct": 0,
        "by_category": {},
        "failures": [],
    }

    current_category = None
    for query, expected_ids, category, description in cases:
        if category != current_category:
            current_category = category
            print(f"\n{'─' * 70}")
            print(f"  [{category.upper()}]")
            print(f"{'─' * 70}")
            if category not in results_summary["by_category"]:
                results_summary["by_category"][category] = {
                    "total": 0, "top1": 0, "top3": 0, "top5": 0,
                }

        try:
            cat_filter = category if args.filter and category != "cross" else None
            results = query_kb(client, kb_id, query, category_filter=cat_filter)
        except Exception as e:
            print(f"  ERROR: {query} → {e}")
            results_summary["total"] += 1
            results_summary["by_category"][category]["total"] += 1
            results_summary["failures"].append((query, category, str(e)))
            continue

        top1, top3, top5 = evaluate_result(results, expected_ids)

        results_summary["total"] += 1
        results_summary["by_category"][category]["total"] += 1

        if top1:
            results_summary["top1_correct"] += 1
            results_summary["by_category"][category]["top1"] += 1
        if top3:
            results_summary["top3_correct"] += 1
            results_summary["by_category"][category]["top3"] += 1
        if top5:
            results_summary["top5_correct"] += 1
            results_summary["by_category"][category]["top5"] += 1

        # Status icon
        if top1:
            icon = "OK"
        elif top3:
            icon = "~3"
        elif top5:
            icon = "~5"
        else:
            icon = "XX"
            actual = results[0]["doc_id"] if results else "none"
            results_summary["failures"].append((query, category, f"got {actual}"))

        actual_id = results[0]["doc_id"] if results else "none"
        score = results[0]["score"] if results else 0

        print(f"  [{icon}] {description}")
        print(f"       Q: {query}")
        print(f"       → {actual_id} (score={score:.4f})", end="")
        if not top1:
            exp = expected_ids if isinstance(expected_ids, list) else [expected_ids]
            print(f"  expected: {exp[0]}", end="")
        print()

        if args.verbose and results:
            for i, r in enumerate(results[:3]):
                marker = "*" if r["doc_id"] in (expected_ids if isinstance(expected_ids, list) else [expected_ids]) else " "
                print(f"       {marker}[{i+1}] {r['doc_id']} (score={r['score']:.4f})")

    # Summary
    total = results_summary["total"]
    print(f"\n{'=' * 70}")
    print(f"결과 요약")
    print(f"{'=' * 70}")
    print(f"  전체: {total}개 테스트")
    print(f"  Top-1 정확도: {results_summary['top1_correct']}/{total} ({results_summary['top1_correct']/total*100:.1f}%)")
    print(f"  Top-3 정확도: {results_summary['top3_correct']}/{total} ({results_summary['top3_correct']/total*100:.1f}%)")
    print(f"  Top-5 정확도: {results_summary['top5_correct']}/{total} ({results_summary['top5_correct']/total*100:.1f}%)")

    print(f"\n  카테고리별 Top-1 정확도:")
    for cat, stats in sorted(results_summary["by_category"].items()):
        pct = stats["top1"] / stats["total"] * 100 if stats["total"] else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"    {cat:<25} {stats['top1']:>2}/{stats['total']:<2} ({pct:5.1f}%) {bar}")

    if results_summary["failures"]:
        print(f"\n  실패 목록:")
        for query, cat, detail in results_summary["failures"]:
            print(f"    [{cat}] {query} → {detail}")

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    main()
