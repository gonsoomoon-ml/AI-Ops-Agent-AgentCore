"""Markdown → YAML 변환 스크립트.

Raw markdown 파일을 구조화된 YAML로 변환합니다.

사용법:
    uv run python rag_pipeline/convert_md_to_yaml.py --dataset refrigerator
    uv run python rag_pipeline/convert_md_to_yaml.py --dataset bridge
"""

import argparse
import re
from pathlib import Path

import yaml

# ========== 경로 설정 ==========
PROJECT_ROOT = Path(__file__).parent.parent
DATASETS_CONFIG = Path(__file__).parent / "datasets.yaml"


def load_dataset_config(dataset_name: str) -> dict:
    """datasets.yaml에서 데이터셋 설정 로드."""
    with open(DATASETS_CONFIG) as f:
        config = yaml.safe_load(f)
    datasets = config.get("datasets", {})
    if dataset_name not in datasets:
        available = ", ".join(datasets.keys())
        raise ValueError(f"Unknown dataset: {dataset_name}. Available: {available}")
    return datasets[dataset_name]


def slugify(name: str) -> str:
    """파일 이름을 category ID로 변환 (예: 'Firmware Update' → 'firmware_update')."""
    return name.lower().replace(" ", "_").replace("-", "_")


def extract_error_codes(text: str) -> list[str]:
    """텍스트에서 에러 코드 추출 (예: 5E, 22E, 84C)."""
    codes = re.findall(r'\b(\d{1,3}[A-Z])\b', text)
    return sorted(set(codes))


def extract_keywords(text: str) -> list[str]:
    """텍스트에서 키워드 추출."""
    keywords = set()

    # 영어 기술 용어 (2단어 이상 또는 CamelCase)
    english_terms = re.findall(r'[A-Z][a-z]+(?:\s[A-Z][a-z]+)+', text)
    keywords.update(english_terms)

    # 영어 단일 기술 용어 (3글자 이상 대문자 포함)
    single_terms = re.findall(r'\b([A-Z][a-zA-Z]{2,})\b', text)
    stopwords = {
        "The", "This", "That", "What", "How", "When", "Where", "Which",
        "From", "With", "Into", "About", "Each", "Auto", "Manual",
    }
    for term in single_terms:
        if term not in stopwords:
            keywords.add(term)

    # 괄호 안의 용어 (한글/영어 모두)
    paren_terms = re.findall(r'\(([^)]{2,30})\)', text)
    keywords.update(paren_terms)

    # 한국어 기술 키워드 (주요 명사구)
    ko_patterns = [
        r'([\uac00-\ud7a3]{2,6}(?:센서|모터|모듈|히터|보드|패널|알고리즘|프로토콜|서버|클라이언트|포털))',
        r'([\uac00-\ud7a3]{2,4}(?:실|기|실))',
        r'(에러\s*코드)',
        r'(펌웨어\s*업데이트)',
        r'(자가\s*진단)',
    ]
    for pattern in ko_patterns:
        matches = re.findall(pattern, text)
        keywords.update(matches)

    return sorted(keywords)


def generate_question_variants(title: str) -> list[str]:
    """제목에서 질문 변형 생성."""
    variants = []
    clean_title = title.strip()

    if clean_title.endswith("?") or "무엇" in clean_title or "어떻게" in clean_title:
        variants.append(clean_title.rstrip("?"))

    desc_match = re.search(r'(.+?)에?\s*대한\s*설명', clean_title)
    if desc_match:
        subject = desc_match.group(1).strip()
        variants.append(f"{subject}이 뭐야?")
        variants.append(f"{subject} 설명해줘")

    method_match = re.search(r'(.+?)\s*방법', clean_title)
    if method_match:
        action = method_match.group(1).strip()
        variants.append(f"{action} 어떻게 해?")
        variants.append(f"{action} 방법 알려줘")

    if "목록" in clean_title:
        variants.append(clean_title.replace("목록", "알려줘"))

    if not variants:
        variants.append(f"{clean_title} 알려줘")
        variants.append(f"{clean_title}에 대해 설명해줘")

    return variants


def parse_md_entry(raw_block: str) -> dict | None:
    """단일 마크다운 항목 파싱."""
    title_match = re.search(r'\*\*title\*\*:\s*(.+)', raw_block)
    contents_match = re.search(r'\*\*contents\*\*:\s*(.+)', raw_block)
    urls_match = re.search(r'\*\*urls\*\*:\s*(.+)', raw_block)
    sheet_match = re.search(r'\*\*sheet\*\*:\s*(.+)', raw_block)
    row_match = re.search(r'\*\*row\*\*:\s*(\d+)', raw_block)

    if not title_match or not contents_match:
        return None

    title = title_match.group(1).strip()
    contents = contents_match.group(1).strip()
    url = urls_match.group(1).strip() if urls_match else ""
    sheet = sheet_match.group(1).strip() if sheet_match else ""
    row = int(row_match.group(1)) if row_match else 0

    error_codes = extract_error_codes(contents)
    keywords = extract_keywords(f"{title} {contents}")
    question_variants = generate_question_variants(title)

    return {
        "title": title,
        "answer": contents,
        "url": url,
        "sheet": sheet,
        "row": row,
        "error_codes": error_codes,
        "keywords": keywords,
        "question_variants": question_variants,
    }


def parse_md_file(filepath: Path) -> list[dict]:
    """마크다운 파일에서 모든 항목 파싱."""
    text = filepath.read_text(encoding="utf-8")
    blocks = re.split(r'\n\n---\n', text)

    entries = []
    for block in blocks:
        block = block.strip()
        if not block or "**title**" not in block:
            continue
        entry = parse_md_entry(block)
        if entry:
            entries.append(entry)

    return entries


def convert_all(dataset_name: str):
    """모든 마크다운 파일을 YAML로 변환."""
    ds_config = load_dataset_config(dataset_name)
    input_dir = PROJECT_ROOT / ds_config["raw_dir"]
    output_dir = PROJECT_ROOT / ds_config["yaml_dir"]

    if not input_dir.exists():
        print(f"ERROR: 입력 디렉토리가 없습니다: {input_dir}")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    index_data = {
        "version": "1.0",
        "dataset": dataset_name,
        "description": ds_config.get("description", ""),
        "categories": [],
    }

    total_entries = 0
    all_keywords: set[str] = set()

    md_files = sorted(input_dir.glob("*.md"))
    print(f"데이터셋: {dataset_name}")
    print(f"입력: {input_dir}")
    print(f"출력: {output_dir}")
    print(f"입력 파일: {len(md_files)}개")

    for md_file in md_files:
        category_name = md_file.stem
        category_id = slugify(category_name)

        entries = parse_md_file(md_file)
        if not entries:
            print(f"  [SKIP] {md_file.name}: 항목 없음")
            continue

        for i, entry in enumerate(entries, start=1):
            entry["id"] = f"{category_id}-{i:03d}"

        category_data = {
            "category_id": category_id,
            "category_name": category_name,
            "entry_count": len(entries),
            "entries": entries,
        }

        output_path = output_dir / f"{category_id}.yaml"
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                category_data,
                f,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

        cat_keywords = set()
        for entry in entries:
            cat_keywords.update(entry.get("keywords", []))
            all_keywords.update(entry.get("keywords", []))

        index_data["categories"].append({
            "id": category_id,
            "name": category_name,
            "entry_count": len(entries),
            "top_keywords": sorted(cat_keywords)[:20],
        })

        total_entries += len(entries)
        print(f"  [OK] {category_id}.yaml: {len(entries)}개 항목")

    index_data["total_entries"] = total_entries
    index_path = output_dir / "index.yaml"
    with open(index_path, "w", encoding="utf-8") as f:
        yaml.dump(
            index_data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"\n완료: {total_entries}개 항목 → {output_dir}")
    print(f"인덱스: {index_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Markdown → YAML 변환")
    parser.add_argument(
        "--dataset",
        default="refrigerator",
        help="데이터셋 이름 (datasets.yaml에 정의된 이름)",
    )
    args = parser.parse_args()
    convert_all(args.dataset)
