"""
Create or delete a Bedrock Knowledge Base for any dataset in datasets.yaml.

Improves on the original under_development/knowledge_base.py:
  1. OpenSearch index mapping — adds `keyword` subfields for filterable metadata
  2. Chunking strategy — uses NONE (documents pre-chunked by RAG pipeline)
  3. Reads all config from datasets.yaml (consistent with other pipeline scripts)

Usage:
  uv run python rag_pipeline/create_kb.py --dataset bridge --mode create
  uv run python rag_pipeline/create_kb.py --dataset refrigerator --mode create
  uv run python rag_pipeline/create_kb.py --dataset bridge --mode delete

After creation, update rag_pipeline/datasets.yaml with the printed kb_id, ds_id, s3_bucket values.
"""

import argparse
import json
import os
import pprint
import sys

import boto3
import yaml
from opensearchpy import RequestError
from retrying import retry

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "under_development"))
from knowledge_base import (
    KnowledgeBasesForAmazonBedrock,
    interactive_sleep,
)

pp = pprint.PrettyPrinter(indent=2)

DATASETS_CONFIG = os.path.join(os.path.dirname(__file__), "datasets.yaml")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_dataset_config(dataset_name: str) -> dict:
    """datasets.yaml에서 데이터셋 설정 로드."""
    with open(DATASETS_CONFIG) as f:
        config = yaml.safe_load(f)
    datasets = config.get("datasets", {})
    if dataset_name not in datasets:
        available = ", ".join(datasets.keys())
        raise ValueError(f"Unknown dataset: {dataset_name}. Available: {available}")
    return datasets[dataset_name]


class ImprovedKnowledgeBase(KnowledgeBasesForAmazonBedrock):
    """
    Extends KnowledgeBasesForAmazonBedrock with:
      - Correct OpenSearch index mapping (keyword subfields for metadata filtering)
      - NONE chunking strategy (documents are pre-chunked by RAG pipeline)
      - Configurable embedding dimension (default 1024)
    """

    def create_vector_index(self, index_name: str):
        """
        Create OpenSearch Serverless vector index with keyword subfields
        on metadata fields so that Bedrock metadata filtering works.

        Bedrock internally queries `category.keyword`, `doc_id.keyword`, etc.
        Without the `.keyword` subfield, filter queries silently return no results.
        """
        body_json = {
            "settings": {
                "index.knn": "true",
                "number_of_shards": 1,
                "knn.algo_param.ef_search": 512,
                "number_of_replicas": 0,
            },
            "mappings": {
                "properties": {
                    "vector": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "name": "hnsw",
                            "engine": "faiss",
                            "space_type": "l2",
                        },
                    },
                    "text": {"type": "text"},
                    "text-metadata": {"type": "text"},
                    # ── Filterable metadata fields ──
                    "category": {
                        "type": "text",
                        "fields": {
                            "keyword": {"type": "keyword", "ignore_above": 256}
                        },
                    },
                }
            },
        }

        try:
            response = self.oss_client.indices.create(
                index=index_name, body=json.dumps(body_json)
            )
            print("\nCreating index with keyword subfields:")
            pp.pprint(response)
            interactive_sleep(60)
        except RequestError as e:
            print(
                f"Error creating index: {e.error}\n"
                "If the index already exists, delete it first and re-run."
            )

    @retry(wait_random_min=1000, wait_random_max=2000, stop_max_attempt_number=7)
    def create_knowledge_base(
        self,
        collection_arn: str,
        index_name: str,
        bucket_name: str,
        embedding_model: str,
        kb_name: str,
        kb_description: str,
        bedrock_kb_execution_role: str,
    ):
        """
        Create Knowledge Base with NONE chunking (documents are pre-chunked).
        """
        opensearch_serverless_configuration = {
            "collectionArn": collection_arn,
            "vectorIndexName": index_name,
            "fieldMapping": {
                "vectorField": "vector",
                "textField": "text",
                "metadataField": "text-metadata",
            },
        }

        # NONE chunking — documents are already chunked by RAG pipeline
        chunking_strategy_configuration = {
            "chunkingStrategy": "NONE",
        }

        s3_configuration = {
            "bucketArn": f"arn:aws:s3:::{bucket_name}",
        }

        embedding_model_arn = (
            f"arn:aws:bedrock:{self.region_name}::foundation-model/{embedding_model}"
        )
        print(f"Embedding model ARN: {embedding_model_arn}")

        try:
            create_kb_response = self.bedrock_agent_client.create_knowledge_base(
                name=kb_name,
                description=kb_description,
                roleArn=bedrock_kb_execution_role["Role"]["Arn"],
                knowledgeBaseConfiguration={
                    "type": "VECTOR",
                    "vectorKnowledgeBaseConfiguration": {
                        "embeddingModelArn": embedding_model_arn
                    },
                },
                storageConfiguration={
                    "type": "OPENSEARCH_SERVERLESS",
                    "opensearchServerlessConfiguration": opensearch_serverless_configuration,
                },
            )
            kb = create_kb_response["knowledgeBase"]
            pp.pprint(kb)
        except self.bedrock_agent_client.exceptions.ConflictException:
            kbs = self.bedrock_agent_client.list_knowledge_bases(maxResults=100)
            kb_id = None
            for kb in kbs["knowledgeBaseSummaries"]:
                if kb["name"] == kb_name:
                    kb_id = kb["knowledgeBaseId"]
            response = self.bedrock_agent_client.get_knowledge_base(
                knowledgeBaseId=kb_id
            )
            kb = response["knowledgeBase"]
            pp.pprint(kb)

        # Create DataSource with NONE chunking
        try:
            create_ds_response = self.bedrock_agent_client.create_data_source(
                name=kb_name,
                description=kb_description,
                knowledgeBaseId=kb["knowledgeBaseId"],
                dataDeletionPolicy="RETAIN",
                dataSourceConfiguration={
                    "type": "S3",
                    "s3Configuration": s3_configuration,
                },
                vectorIngestionConfiguration={
                    "chunkingConfiguration": chunking_strategy_configuration
                },
            )
            ds = create_ds_response["dataSource"]
            pp.pprint(ds)
        except self.bedrock_agent_client.exceptions.ConflictException:
            ds_id = self.bedrock_agent_client.list_data_sources(
                knowledgeBaseId=kb["knowledgeBaseId"], maxResults=100
            )["dataSourceSummaries"][0]["dataSourceId"]
            get_ds_response = self.bedrock_agent_client.get_data_source(
                dataSourceId=ds_id, knowledgeBaseId=kb["knowledgeBaseId"]
            )
            ds = get_ds_response["dataSource"]
            pp.pprint(ds)
        return kb, ds


def main():
    parser = argparse.ArgumentParser(
        description="Bedrock Knowledge Base 생성/삭제 (datasets.yaml 기반)"
    )
    parser.add_argument(
        "--dataset", required=True, help="데이터셋 이름 (e.g. refrigerator, bridge)"
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["create", "delete"],
        help="create or delete the KB",
    )
    args = parser.parse_args()

    ds_config = load_dataset_config(args.dataset)
    kb_name = ds_config.get("kb_name") or f"ops-{args.dataset}-kb"
    kb_description = ds_config["description"]
    embedding_model = ds_config.get("embedding_model", "cohere.embed-multilingual-v3")
    upload_dir = os.path.join(PROJECT_ROOT, ds_config["yaml_dir"], "bedrock_upload")

    kb = ImprovedKnowledgeBase()
    ssm_client = boto3.client("ssm")

    if args.mode == "create":
        print(f"Creating KB for dataset: {args.dataset}")
        print(f"  KB name        : {kb_name}")
        print(f"  Description    : {kb_description}")
        print(f"  Embedding model: {embedding_model}")
        print(f"  Upload dir     : {upload_dir}")
        print()

        kb_id, ds_id = kb.create_or_retrieve_knowledge_base(
            kb_name=kb_name,
            kb_description=kb_description,
            embedding_model=embedding_model,
        )
        s3_bucket = kb.get_data_bucket_name()

        print("\n" + "=" * 80)
        print(f"[{args.dataset}] KB created successfully!")
        print(f"  Knowledge Base ID : {kb_id}")
        print(f"  Data Source ID    : {ds_id}")
        print(f"  S3 Bucket         : {s3_bucket}")
        print("=" * 80)

        # Upload documents to S3
        print(f"\nUploading {upload_dir} to S3...")
        kb.upload_directory(upload_dir, s3_bucket)

        # Sync (ingest) data
        print("\nStarting ingestion job...")
        kb.synchronize_data(kb_id, ds_id)

        # Store KB ID in SSM Parameter Store
        ssm_client.put_parameter(
            Name=f"{kb_name}-kb-id",
            Description=f"{kb_name} kb id",
            Value=kb_id,
            Type="String",
            Overwrite=True,
        )

        # Print datasets.yaml update instructions
        print("\n" + "=" * 80)
        print(f"ACTION REQUIRED: Update rag_pipeline/datasets.yaml [{args.dataset}]:")
        print(f'    s3_bucket: "{s3_bucket}"')
        print(f'    kb_id: "{kb_id}"')
        print(f'    ds_id: "{ds_id}"')
        print(f'    kb_name: "{kb_name}"')
        print("=" * 80)

    elif args.mode == "delete":
        if not kb_name:
            print(f"Error: kb_name not set in datasets.yaml for {args.dataset}")
            sys.exit(1)
        print(f"Deleting KB: {kb_name}")
        kb.delete_kb(kb_name)
        try:
            ssm_client.delete_parameter(Name=f"{kb_name}-kb-id")
        except ssm_client.exceptions.ParameterNotFound:
            pass


if __name__ == "__main__":
    main()
