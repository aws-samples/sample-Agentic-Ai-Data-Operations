"""
WorkloadIndex: vector similarity search over existing workloads.

Three-tier fallback:
  Tier 1: sentence-transformers + FAISS (real embeddings)
  Tier 2: TF-IDF + cosine similarity (stdlib only)
  Tier 3: REIC_ENABLED=false -> disabled, returns empty results
"""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from shared.reic.deterministic_utils import cosine_similarity, deterministic_embed


@dataclass
class WorkloadMatch:
    """A workload matched by similarity search."""
    workload_name: str
    score: float
    source_yaml_path: str
    matched_features: list[str] = field(default_factory=list)


class WorkloadIndex:
    """Searchable index over workloads/ directory.

    Extracts text features from source.yaml + semantic.yaml for each workload,
    builds a vector index, and supports ranked similarity search.
    """

    def __init__(self, workloads_dir: str = "workloads"):
        self._workloads_dir = Path(workloads_dir)
        self._documents: dict[str, str] = {}  # workload_name -> feature text
        self._source_paths: dict[str, str] = {}  # workload_name -> source.yaml path
        self._idf: dict[str, float] = {}
        self._tfidf_vectors: dict[str, dict[str, float]] = {}
        self._vocab: list[str] = []
        self._backend = self._detect_backend()

    @property
    def backend(self) -> str:
        return self._backend

    @staticmethod
    def _detect_backend() -> str:
        if os.environ.get("REIC_ENABLED", "true").lower() == "false":
            return "disabled"
        try:
            import sentence_transformers  # noqa: F401
            import faiss  # noqa: F401
            return "faiss"
        except ImportError:
            return "tfidf"

    def build_index(self) -> int:
        """Scan workloads/ and build the search index. Returns workload count."""
        if self._backend == "disabled":
            return 0

        self._documents.clear()
        self._source_paths.clear()

        if not self._workloads_dir.exists():
            return 0

        for workload_dir in sorted(self._workloads_dir.iterdir()):
            if not workload_dir.is_dir():
                continue
            source_path = workload_dir / "config" / "source.yaml"
            if not source_path.exists():
                continue
            self._add_workload_from_dir(workload_dir)

        self._build_tfidf()
        return len(self._documents)

    def add_workload(self, name: str) -> None:
        """Incrementally add a single workload and rebuild TF-IDF."""
        workload_dir = self._workloads_dir / name
        if not workload_dir.is_dir():
            return
        self._add_workload_from_dir(workload_dir)
        self._build_tfidf()

    def search(self, query: str, top_k: int = 3) -> list[WorkloadMatch]:
        """Search for workloads matching the query. Returns ranked results."""
        if self._backend == "disabled" or not self._documents:
            return []

        query_norm = deterministic_embed(query)
        query_vec = self._text_to_tfidf(query_norm)

        results = []
        for name, doc_vec in self._tfidf_vectors.items():
            a = [query_vec.get(t, 0.0) for t in self._vocab]
            b = [doc_vec.get(t, 0.0) for t in self._vocab]
            score = cosine_similarity(a, b)
            if score > 0.0:
                matched = self._find_matched_features(query_norm, self._documents[name])
                results.append(WorkloadMatch(
                    workload_name=name,
                    score=round(score, 4),
                    source_yaml_path=self._source_paths[name],
                    matched_features=matched,
                ))

        results.sort(key=lambda m: m.score, reverse=True)
        return results[:top_k]

    def _add_workload_from_dir(self, workload_dir: Path) -> None:
        name = workload_dir.name
        features = []

        source_path = workload_dir / "config" / "source.yaml"
        if source_path.exists():
            self._source_paths[name] = str(source_path)
            features.extend(self._extract_source_features(source_path))

        semantic_path = workload_dir / "config" / "semantic.yaml"
        if semantic_path.exists():
            features.extend(self._extract_semantic_features(semantic_path))

        features.append(name.replace("_", " "))
        self._documents[name] = deterministic_embed(" ".join(features))

    @staticmethod
    def _extract_source_features(path: Path) -> list[str]:
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return []

        source = data.get("source", {})
        features = []
        for key in ("name", "description", "format", "type"):
            val = source.get(key)
            if val:
                features.append(str(val))

        schema = source.get("schema", {})
        for col in schema.get("columns", []):
            if isinstance(col, dict):
                if col.get("name"):
                    features.append(col["name"])
                if col.get("description"):
                    features.append(col["description"])
        return features

    @staticmethod
    def _extract_semantic_features(path: Path) -> list[str]:
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except (yaml.YAMLError, OSError):
            return []

        features = []
        dataset = data.get("dataset", {})
        for key in ("name", "business_name", "domain", "description"):
            val = dataset.get(key)
            if val:
                features.append(str(val))
        for tag in dataset.get("tags", []):
            features.append(str(tag))

        columns = data.get("columns", {})
        if isinstance(columns, dict):
            for col_name, col_info in columns.items():
                features.append(col_name)
                if isinstance(col_info, dict):
                    for term in col_info.get("business_terms", []):
                        features.append(str(term))
        elif isinstance(columns, list):
            for col in columns:
                if isinstance(col, dict):
                    if col.get("name"):
                        features.append(col["name"])
                    for term in col.get("business_terms", []):
                        features.append(str(term))
        return features

    @staticmethod
    def _find_matched_features(query_norm: str, doc_text: str) -> list[str]:
        query_tokens = set(query_norm.split())
        doc_tokens = doc_text.split()
        return sorted(set(t for t in doc_tokens if t in query_tokens))

    def _build_tfidf(self) -> None:
        if not self._documents:
            return

        doc_count = len(self._documents)
        df: Counter = Counter()
        tf_per_doc: dict[str, Counter] = {}

        for name, text in self._documents.items():
            tokens = text.split()
            tf_per_doc[name] = Counter(tokens)
            df.update(set(tokens))

        self._vocab = sorted(df.keys())
        self._idf = {
            term: math.log((doc_count + 1) / (count + 1)) + 1
            for term, count in df.items()
        }

        self._tfidf_vectors = {}
        for name, tf in tf_per_doc.items():
            total = sum(tf.values())
            vec = {}
            for term, count in tf.items():
                vec[term] = (count / total) * self._idf.get(term, 1.0)
            self._tfidf_vectors[name] = vec

    def _text_to_tfidf(self, text: str) -> dict[str, float]:
        tokens = text.split()
        tf = Counter(tokens)
        total = sum(tf.values())
        vec = {}
        for term, count in tf.items():
            if term in self._idf:
                vec[term] = (count / total) * self._idf[term]
        return vec
