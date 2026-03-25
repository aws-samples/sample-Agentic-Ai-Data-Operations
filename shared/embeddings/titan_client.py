"""
AWS Bedrock Titan Embeddings Client

Generates 1024-dimensional embeddings for semantic search using amazon.titan-embed-text-v1.
"""

import boto3
import json
from typing import List, Optional, Dict, Any
from botocore.exceptions import ClientError


class TitanEmbeddingsClient:
    """Generate embeddings using AWS Bedrock Titan model."""

    def __init__(self, region: str = 'us-east-1', model_id: str = 'amazon.titan-embed-text-v1'):
        """
        Initialize Bedrock Titan client.

        Args:
            region: AWS region
            model_id: Titan embeddings model ID

        Raises:
            ValueError: If Bedrock not available in region
        """
        self.region = region
        self.model_id = model_id

        try:
            self.bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)
        except Exception as e:
            raise ValueError(
                f"Failed to initialize Bedrock client in region '{region}': {e}"
            ) from e

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate 1024-dimensional embedding for a text string.

        Args:
            text: Input text to embed (max ~8,000 tokens)

        Returns:
            List of 1024 floats (embedding vector)

        Raises:
            ValueError: If text is empty or API call fails

        Example:
            >>> client = TitanEmbeddingsClient()
            >>> embedding = client.generate_embedding("portfolio market value")
            >>> len(embedding)
            1024
            >>> isinstance(embedding[0], float)
            True
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Truncate if too long (Titan has ~8K token limit)
        max_chars = 30000  # Approximate 8K tokens
        if len(text) > max_chars:
            text = text[:max_chars]

        body = json.dumps({"inputText": text})

        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=body
            )

            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding')

            if not embedding:
                raise ValueError("No embedding returned from Titan model")

            return embedding

        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            raise ValueError(
                f"Bedrock API error ({error_code}): {error_message}"
            ) from e

    def batch_generate(
        self,
        texts: List[str],
        batch_size: int = 10,
        verbose: bool = False
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (with batching).

        Args:
            texts: List of text strings to embed
            batch_size: Number of texts to process per batch (rate limiting)
            verbose: Print progress

        Returns:
            List of embeddings (same order as input texts)

        Example:
            >>> client = TitanEmbeddingsClient()
            >>> texts = ["revenue", "profit margin", "customer count"]
            >>> embeddings = client.batch_generate(texts)
            >>> len(embeddings)
            3
            >>> len(embeddings[0])
            1024
        """
        embeddings = []

        for i, text in enumerate(texts):
            try:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)

                if verbose and (i + 1) % batch_size == 0:
                    print(f"Processed {i + 1}/{len(texts)} embeddings")

            except Exception as e:
                # Log error but continue with next text
                print(f"Warning: Failed to embed text {i}: {e}")
                # Return zero vector as fallback
                embeddings.append([0.0] * 1024)

        return embeddings

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Compute cosine similarity between two embedding vectors.

        Args:
            vec1: First embedding vector
            vec2: Second embedding vector

        Returns:
            Cosine similarity score (0.0 to 1.0)

        Example:
            >>> client = TitanEmbeddingsClient()
            >>> emb1 = client.generate_embedding("revenue")
            >>> emb2 = client.generate_embedding("sales")
            >>> similarity = client.cosine_similarity(emb1, emb2)
            >>> 0.8 < similarity < 1.0  # "revenue" and "sales" are semantically similar
            True
        """
        if len(vec1) != len(vec2):
            raise ValueError(f"Vector dimensions must match: {len(vec1)} != {len(vec2)}")

        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))

        # Magnitudes
        magnitude1 = sum(a * a for a in vec1) ** 0.5
        magnitude2 = sum(b * b for b in vec2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)

    def find_most_similar(
        self,
        query_embedding: List[float],
        candidate_embeddings: List[List[float]],
        top_k: int = 5
    ) -> List[tuple[int, float]]:
        """
        Find most similar embeddings to a query.

        Args:
            query_embedding: Query embedding vector
            candidate_embeddings: List of candidate embeddings to compare
            top_k: Number of top results to return

        Returns:
            List of (index, similarity_score) tuples, sorted by similarity

        Example:
            >>> client = TitanEmbeddingsClient()
            >>> query = client.generate_embedding("monthly revenue")
            >>> candidates = [
            ...     client.generate_embedding("revenue by month"),
            ...     client.generate_embedding("customer count"),
            ...     client.generate_embedding("total sales per period")
            ... ]
            >>> results = client.find_most_similar(query, candidates, top_k=2)
            >>> results[0][0] in [0, 2]  # Index 0 or 2 should be most similar
            True
        """
        similarities = []

        for i, candidate in enumerate(candidate_embeddings):
            similarity = self.cosine_similarity(query_embedding, candidate)
            similarities.append((i, similarity))

        # Sort by similarity (descending)
        similarities.sort(key=lambda x: x[1], reverse=True)

        return similarities[:top_k]

    def embed_with_prefix(
        self,
        text: str,
        prefix: str = ""
    ) -> List[float]:
        """
        Generate embedding with optional prefix for context.

        Args:
            text: Text to embed
            prefix: Prefix to add for context (e.g., "table:", "column:", "query:")

        Returns:
            Embedding vector

        Example:
            >>> client = TitanEmbeddingsClient()
            >>> table_emb = client.embed_with_prefix("positions", prefix="table:")
            >>> column_emb = client.embed_with_prefix("positions", prefix="column:")
            >>> # Different prefixes produce different embeddings
            >>> table_emb != column_emb
            True
        """
        if prefix:
            full_text = f"{prefix} {text}"
        else:
            full_text = text

        return self.generate_embedding(full_text)
