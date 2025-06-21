from docx import Document
import os
import logging
from typing import List, Dict, Any
from services.llm.utils import is_valid_for_embedding

logger = logging.getLogger(__name__)

def load_docx_files(data_dir: str, chunk_size: int = 7500) -> List[Dict[str, str]]:
    """
    Load all .docx files from a directory and split large texts into chunks.
    
    Args:
        data_dir (str): Path to folder containing .docx files
        chunk_size (int): Max token size per chunk for embedding compatibility
    
    Returns:
        List[Dict]: List of document chunks with 'source' and 'text'
    """
    documents = []
    
    if not os.path.exists(data_dir):
        logger.error(f"Document directory does not exist: {data_dir}")
        raise FileNotFoundError(f"Directory not found: {data_dir}")

    logger.info(f"Loading .docx files from {data_dir}")
    
    for filename in os.listdir(data_dir):
        if filename.endswith(".docx"):
            file_path = os.path.join(data_dir, filename)
            try:
                # Load document
                doc = Document(file_path)
                full_text = "\n".join([para.text for para in doc.paragraphs])

                # Split into chunks if needed
                words = full_text.split()
                num_chunks = (len(words) // chunk_size) + 1

                logger.info(f"Processing {filename} - splitting into {num_chunks} chunks")
                
                for i in range(0, len(words), chunk_size):
                    chunk = " ".join(words[i:i + chunk_size])
                    
                    if not is_valid_for_embedding(chunk):
                        logger.warning(f"Skipping oversized chunk from {filename}")
                        continue
                    
                    documents.append({
                        "source": f"{filename}-chunk{i//chunk_size}",
                        "text": chunk
                    })

                logger.info(f"Loaded {num_chunks} chunks from {filename}")
            except Exception as e:
                logger.warning(f"Error reading {filename}: {str(e)}")
    
    logger.info(f"Successfully loaded {len(documents)} document chunks")
    return documents