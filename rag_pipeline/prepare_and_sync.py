"""YAML 데이터를 Bedrock KB 형식으로 변환하고 S3에 업로드 + 동기화.

data/RAG/<dataset>_yaml/*.yaml → .md + .metadata.json 쌍 생성 → S3 업로드 → KB 동기화.

사용법:
    # 변환 + 업로드 + 동기화 (전체)
    uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator

    # 변환만 (로컬 파일 생성)
    uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode prepare

    # 업로드 + 동기화만 (이미 변환된 파일)
    uv run python rag_pipeline/prepare_and_sync.py --dataset refrigerator --mode sync
"""

import argparse
import json
import os
import re
import shutil
import sys
import time

import boto3
import yaml

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.join(CURRENT_DIR, "..")
DATASETS_CONFIG = os.path.join(CURRENT_DIR, "datasets.yaml")


# ── Module-level state (set by main() based on --dataset) ──────────────────
_yaml_dir = None
_enriched_dir = None
_output_dir = None
_category_names = {}
_ds_config = {}


def load_dataset_config(dataset_name):
    """datasets.yaml에서 데이터셋 설정 로드."""
    with open(DATASETS_CONFIG) as f:
        config = yaml.safe_load(f)
    datasets = config.get("datasets", {})
    if dataset_name not in datasets:
        available = ", ".join(datasets.keys())
        raise ValueError(f"Unknown dataset: {dataset_name}. Available: {available}")
    return datasets[dataset_name]


def load_yaml_entries(yaml_dir):
    """모든 YAML 카테고리 파일에서 엔트리를 로드."""
    with open(os.path.join(yaml_dir, "index.yaml")) as f:
        index = yaml.safe_load(f)

    all_entries = []
    for cat in index["categories"]:
        cat_path = os.path.join(yaml_dir, f"{cat['id']}.yaml")
        with open(cat_path) as f:
            data = yaml.safe_load(f)
        for entry in data["entries"]:
            entry["category_id"] = data["category_id"]
            entry["category_name"] = data["category_name"]
            all_entries.append(entry)

    return all_entries


def extract_title_terms(title: str) -> tuple[str, str]:
    """제목에서 한국어 핵심 용어와 영어 용어를 추출."""
    ko_term = ""
    en_term = ""

    m = re.match(r'^(.+?)\(([^)]+)\)', title)
    if m:
        ko_term = m.group(1).strip()
        en_term = m.group(2).strip()
    else:
        m2 = re.match(r'^([A-Za-z][A-Za-z\s]+?)에서\s+(.+)', title)
        if m2:
            en_term = m2.group(1).strip()
            ko_term = m2.group(2).strip()
        else:
            ko_term = title
            for suffix in ["에 대한 설명", "에 대한 상세 설명", "이 무엇인가요?",
                           "가 무엇인가요?", "에 대해", "방법", "설명"]:
                if ko_term.endswith(suffix):
                    ko_term = ko_term[:-len(suffix)].strip()
                    break

    if not en_term:
        en_matches = re.findall(r'[A-Z][a-zA-Z-]+(?:\s[A-Z][a-zA-Z-]+)*', title)
        if en_matches:
            en_term = en_matches[0]

    return ko_term, en_term


def strip_korean_particles(word: str) -> str:
    """한국어 조사/어미 제거."""
    particles = [
        "으로서는", "으로서", "에서는", "으로는", "이라는",
        "에서", "으로", "에는", "에게", "까지", "부터", "마다",
        "에도", "와는", "과는", "이나", "이란",
        "는", "은", "를", "을", "가", "이", "의", "에", "와", "과",
        "도", "만", "로", "며",
    ]
    for p in particles:
        if word.endswith(p) and len(word) > len(p) + 1:
            return word[:-len(p)]
    return word


def extract_korean_nouns_from_answer(answer: str) -> list[str]:
    """답변에서 한국어 핵심 명사/용어를 추출 (NLP-free)."""
    nouns = set()

    for m in re.finditer(r'([\uac00-\ud7a3]{2,10})\([A-Za-z]', answer):
        nouns.add(m.group(1))

    tech_suffixes = (
        "기능", "모드", "센서", "모터", "필터", "히터", "패널", "모듈",
        "방식", "기술", "장치", "시스템", "서비스", "포털", "코드",
        "업데이트", "알림", "진단", "제어", "설정", "관리", "보관",
        "냉동", "냉장", "냉각", "냉매", "제상", "보증", "온도",
        "컴프레서", "인버터", "냉장고", "식품", "카메라",
    )
    for suffix in tech_suffixes:
        for m in re.finditer(rf'([\uac00-\ud7a3]{{0,6}}{suffix})', answer):
            term = m.group(1)
            if len(term) >= 2:
                nouns.add(term)

    ko_words_raw = re.findall(r'([\uac00-\ud7a3]{2,8})', answer)
    ko_words = [strip_korean_particles(w) for w in ko_words_raw]
    ko_words = [w for w in ko_words if len(w) >= 2]

    from collections import Counter
    freq = Counter(ko_words)
    stopwords = {
        "있습니다", "됩니다", "합니다", "입니다", "습니다", "않습니다",
        "있으며", "않는", "필요합니다", "바랍니다", "경우입니다",
        "있어", "됩니", "합니",
        "통해", "따라", "위해", "하여", "수행", "발생",
        "작동", "작동하", "가동", "지원", "적용", "채택",
        "표시", "확인", "안내", "선택", "진행",
        "경우", "대한", "것이", "이며", "에서", "으로",
        "위한", "기반", "자동", "가능", "제공", "사용",
        "방법", "기존", "일반", "정상", "전체", "해당",
        "다음", "같습니다", "이상", "또는", "약간", "별도",
        "주로", "크게", "약", "후에", "시에", "정도",
        "감지된", "단선", "단락", "단락이",
    }
    for word, count in freq.items():
        if count >= 2 and word not in stopwords:
            nouns.add(word)

    return sorted(nouns)


def has_final_consonant(char: str) -> bool:
    """한글 문자가 받침(종성)이 있는지 확인."""
    if not char or not ('\uac00' <= char <= '\ud7a3'):
        return False
    code = ord(char) - 0xAC00
    return (code % 28) != 0


def generate_rich_question_variants(title: str, ko_term: str, en_term: str,
                                     error_codes: list[str]) -> list[str]:
    """다양한 자연어 질문 변형 생성 (regex fallback)."""
    variants = []

    if ko_term:
        clean_ko = re.sub(r'^QnA\.\s*', '', ko_term)
        variants.append(f"{clean_ko} 알려줘")
        if not clean_ko.endswith("?"):
            variants.append(f"{clean_ko}에 대해 설명해줘")

        if "무엇" in title or "설명" in title:
            last_char = clean_ko[-1] if clean_ko else ""
            if has_final_consonant(last_char):
                variants.append(f"{clean_ko}이 뭐야?")
            else:
                variants.append(f"{clean_ko}가 뭐야?")
            variants.append(f"{clean_ko} 뭐야?")

        if "방법" in title or "절차" in title or "어떻게" in title:
            variants.append(f"{clean_ko} 어떻게 해?")

    if en_term:
        variants.append(f"{en_term}이 뭐야?")
        variants.append(f"{en_term} 설명해줘")

    if ko_term and en_term and ko_term != en_term:
        variants.append(f"{ko_term}({en_term}) 설명해줘")

    for code in error_codes[:3]:
        variants.append(f"에러 코드 {code} 의미")
        variants.append(f"{code} 에러 원인")

    clean_title = re.sub(r'^QnA\.\s*', '', title).rstrip("?").strip()
    if clean_title not in variants:
        variants.append(clean_title)

    seen = set()
    unique = []
    for v in variants:
        v_clean = v.strip()
        if v_clean and v_clean not in seen:
            seen.add(v_clean)
            unique.append(v_clean)

    return unique[:8]


def load_enrichment(entry_id):
    """LLM enrichment 캐시에서 로드. 없으면 None 반환."""
    path = os.path.join(_enriched_dir, f"{entry_id}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def entry_to_md(entry):
    """엔트리를 가중 구조 마크다운으로 변환.

    LLM enrichment 캐시가 있으면 사용, 없으면 regex fallback.
    """
    title = entry["title"]
    answer = entry["answer"]
    error_codes = entry.get("error_codes", [])
    category_ko = _category_names.get(entry["category_name"], entry["category_name"])

    # LLM v3 enrichment: BM25-optimized templates + discriminative nouns/keywords
    # Falls back to regex if LLM cache missing
    enriched = load_enrichment(entry["id"])
    if enriched:
        ko_term = enriched.get("ko_core_term", "")
        en_term = enriched.get("en_core_term", "")
        ko_nouns = enriched.get("ko_nouns", [])
        variants = enriched.get("question_variants", [])
        all_keywords = enriched.get("search_keywords", [])
    else:
        ko_term, en_term = extract_title_terms(title)
        ko_nouns = extract_korean_nouns_from_answer(answer)
        variants = generate_rich_question_variants(title, ko_term, en_term, error_codes)
        all_keywords = entry.get("keywords", [])

    # ── Build blockquote (key terms for embedding weight) ────────
    blockquote_terms = []
    if ko_term:
        blockquote_terms.append(ko_term)
    if en_term:
        blockquote_terms.append(en_term)
    for noun in ko_nouns[:8]:
        if noun not in blockquote_terms:
            blockquote_terms.append(noun)
    for code in error_codes:
        if code not in blockquote_terms:
            blockquote_terms.append(code)
    blockquote_terms.append(category_ko)

    # ── Assemble markdown ────────────────────────────────────────
    lines = []

    lines.append(f"# {title}")
    lines.append("")

    if blockquote_terms:
        lines.append(f"> {', '.join(blockquote_terms)}")
        lines.append("")

    if variants:
        lines.append("## 관련 질문")
        for v in variants:
            lines.append(f"- {v}")
        lines.append("")

    lines.append("## 답변")
    lines.append("")
    lines.append(answer)
    lines.append("")

    if all_keywords:
        lines.append("## 핵심 키워드")
        lines.append(", ".join(all_keywords))
        lines.append("")

    return "\n".join(lines)


def entry_to_metadata(entry):
    """엔트리를 Bedrock KB 메타데이터 JSON으로 변환."""
    error_codes = entry.get("error_codes", [])
    keywords = entry.get("keywords", [])

    attrs = {
        "doc_id": entry["id"],
        "category": entry["category_id"],
        "document_type": "qa",
        "has_error_codes": bool(error_codes),
    }

    if error_codes:
        attrs["error_codes"] = ", ".join(error_codes)

    if keywords:
        attrs["keywords_ko"] = ", ".join(keywords[:15])

    return {"metadataAttributes": attrs}


def prepare_files(entries):
    """모든 엔트리를 .md + .metadata.json 파일로 변환."""
    os.makedirs(_output_dir, exist_ok=True)

    for entry in entries:
        entry_id = entry["id"]

        md_path = os.path.join(_output_dir, f"{entry_id}.md")
        with open(md_path, "w") as f:
            f.write(entry_to_md(entry))

        meta_path = os.path.join(_output_dir, f"{entry_id}.md.metadata.json")
        with open(meta_path, "w") as f:
            json.dump(entry_to_metadata(entry), f, ensure_ascii=False, indent=2)

    print(f"  생성 완료: {len(entries)}개 엔트리 → {_output_dir}")
    print(f"  파일 수: {len(entries) * 2} (.md + .metadata.json)")


def upload_and_sync():
    """S3에 업로드하고 KB 동기화."""
    kb_id = _ds_config.get("kb_id", "")
    ds_id = _ds_config.get("ds_id", "")
    s3_bucket = _ds_config.get("s3_bucket", "")

    if not kb_id or not ds_id or not s3_bucket:
        # Fallback: try SSM lookup
        kb_name = _ds_config.get("kb_name", "")
        if not kb_name:
            print("  ERROR: datasets.yaml에 kb_id, ds_id, s3_bucket이 설정되지 않았습니다.")
            return

        ssm = boto3.client("ssm")
        try:
            kb_id = ssm.get_parameter(Name=f"{kb_name}-kb-id")["Parameter"]["Value"]
        except Exception:
            print(f"  ERROR: KB ID를 찾을 수 없습니다 (SSM: {kb_name}-kb-id)")
            return

        bedrock_agent = boto3.client("bedrock-agent")
        ds_list = bedrock_agent.list_data_sources(knowledgeBaseId=kb_id)
        ds_id = ds_list["dataSourceSummaries"][0]["dataSourceId"]

        ds_info = bedrock_agent.get_data_source(knowledgeBaseId=kb_id, dataSourceId=ds_id)
        bucket_arn = ds_info["dataSource"]["dataSourceConfiguration"]["s3Configuration"]["bucketArn"]
        s3_bucket = bucket_arn.split(":::")[-1]

    print(f"  KB ID: {kb_id}")
    print(f"  DS ID: {ds_id}")
    print(f"  S3 Bucket: {s3_bucket}")

    # Clear existing S3 objects
    s3 = boto3.client("s3")
    print("\n  기존 S3 객체 삭제 중...")
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=s3_bucket):
        if "Contents" in page:
            objects = [{"Key": obj["Key"]} for obj in page["Contents"]]
            s3.delete_objects(Bucket=s3_bucket, Delete={"Objects": objects})
            print(f"    삭제: {len(objects)}개 객체")

    # Upload new files
    print(f"\n  새 파일 업로드 중...")
    upload_count = 0
    for filename in sorted(os.listdir(_output_dir)):
        filepath = os.path.join(_output_dir, filename)
        s3.upload_file(filepath, s3_bucket, filename)
        upload_count += 1
    print(f"    업로드 완료: {upload_count}개 파일")

    # Sync KB
    print(f"\n  KB 동기화 시작...")
    bedrock_agent = boto3.client("bedrock-agent")
    response = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=kb_id,
        dataSourceId=ds_id,
    )
    job_id = response["ingestionJob"]["ingestionJobId"]
    print(f"    Job ID: {job_id}")

    # Wait for sync
    while True:
        job = bedrock_agent.get_ingestion_job(
            knowledgeBaseId=kb_id,
            dataSourceId=ds_id,
            ingestionJobId=job_id,
        )
        status = job["ingestionJob"]["status"]
        stats = job["ingestionJob"]["statistics"]
        scanned = stats["numberOfDocumentsScanned"]
        indexed = stats["numberOfNewDocumentsIndexed"] + stats["numberOfModifiedDocumentsIndexed"]
        failed = stats["numberOfDocumentsFailed"]

        if status in ("COMPLETE", "FAILED", "STOPPED"):
            break
        sys.stdout.write(f"\r    상태: {status} | 스캔: {scanned} | 인덱싱: {indexed} | 실패: {failed}")
        sys.stdout.flush()
        time.sleep(2)

    print(f"\n\n  동기화 완료!")
    print(f"    상태: {status}")
    print(f"    스캔: {stats['numberOfDocumentsScanned']}")
    print(f"    신규 인덱싱: {stats['numberOfNewDocumentsIndexed']}")
    print(f"    수정 인덱싱: {stats['numberOfModifiedDocumentsIndexed']}")
    print(f"    삭제: {stats['numberOfDocumentsDeleted']}")
    print(f"    실패: {stats['numberOfDocumentsFailed']}")


def main():
    global _yaml_dir, _enriched_dir, _output_dir, _category_names, _ds_config

    parser = argparse.ArgumentParser(description="YAML → Bedrock KB 변환 및 동기화")
    parser.add_argument("--dataset", default="refrigerator", help="데이터셋 이름")
    parser.add_argument(
        "--mode",
        default="all",
        choices=["prepare", "sync", "all"],
        help="실행 모드: prepare (파일 생성만), sync (업로드+동기화만), all (전체)",
    )
    args = parser.parse_args()

    _ds_config = load_dataset_config(args.dataset)
    _yaml_dir = os.path.join(PROJECT_ROOT, _ds_config["yaml_dir"])
    _enriched_dir = os.path.join(_yaml_dir, "enriched")
    _output_dir = os.path.join(_yaml_dir, "bedrock_upload")
    _category_names = _ds_config.get("category_names", {})

    if not os.path.exists(_yaml_dir):
        print(f"ERROR: YAML 디렉토리가 없습니다: {_yaml_dir}")
        print(f"먼저 convert_md_to_yaml.py --dataset {args.dataset} 를 실행하세요.")
        return

    print("=" * 60)
    print(f"YAML → Bedrock KB 변환 및 동기화 [{args.dataset}]")
    print("=" * 60)

    entries = load_yaml_entries(_yaml_dir)
    print(f"\n데이터셋: {args.dataset}")
    print(f"총 {len(entries)}개 엔트리 로드")

    if args.mode in ("prepare", "all"):
        print(f"\n[Step 1] 파일 변환")
        prepare_files(entries)

    if args.mode in ("sync", "all"):
        print(f"\n[Step 2] S3 업로드 + KB 동기화")
        upload_and_sync()

    print(f"\n{'=' * 60}")
    print("완료!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
