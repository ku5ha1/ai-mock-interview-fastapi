import logging
from typing import List
from services.rag.embedding import get_embedding
from services.rag.qdrant_client import client as qdrant_client

logger = logging.getLogger(__name__)

class RAGRetriever:
    def __init__(self, collection_name: str = "docs"):
        self.collection_name = collection_name

    async def retrieve_context(self, query: str, top_k: int = 3) -> List[str]:
        """
        Retrieve most relevant context based on query using Qdrant

        Args:
            query (str): User's question
            top_k (int): Number of chunks to retrieve

        Returns:
            List[str]: Top K similar document chunks
        """
        try:
            # Generate embedding for query
            query_embedding = await get_embedding(query)

            if not query_embedding:
                logger.warning("Empty embedding for query")
                return []

            # Search Qdrant collection
            search_result = qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                limit=top_k
            )
            results = [hit.payload["text"] for hit in search_result if hit.payload and "text" in hit.payload]
            logger.info(f"Retrieved {len(results)} context chunks for query: {query[:100]}...")
            return results

        except Exception as e:
            logger.error(f"Error retrieving context: {str(e)}", exc_info=True)
            return []