from llama_index.core import VectorStoreIndex, Document, StorageContext, load_index_from_storage
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.text_splitter import TokenTextSplitter
import os
from typing import List
from llm_utils import get_llm

embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
llm = get_llm()

def create_schema_document(schema_text: str, schema_id: str = "default") -> Document:
    return Document(text=schema_text, metadata={"type": "schema", "schema_id": schema_id})

def index_schema_chunks_rag(chunks: List[str], db_name: str):
    """
    Index all schema chunks for a single database into one vector DB under ./storage/{db_name}
    """
    text_splitter = TokenTextSplitter(chunk_size=4096, chunk_overlap=0)
    documents = []
    


    for chunk in chunks:
        table_name = extract_table_name_from_chunk(chunk) or "unknown"
        nodes = text_splitter.split_text(chunk)
        documents.extend([
            Document(text=node, metadata={"table_name": table_name, "db_name": db_name})
            for node in nodes
        ])

    persist_path = os.path.join("./storage", db_name)
    os.makedirs(persist_path, exist_ok=True)
    


    try:
        storage_context = StorageContext.from_defaults(persist_dir=persist_path)
        index = load_index_from_storage(storage_context, embed_model=embed_model)
    except Exception:
        index = VectorStoreIndex.from_documents(documents, embed_model=embed_model)
        index.storage_context.persist(persist_dir=persist_path)
        return index

    for doc in documents:
        index.insert(doc)
    index.storage_context.persist(persist_dir=persist_path)
    return index

def extract_table_name_from_chunk(chunk: str) -> str:
    import re
    match = re.search(r"CREATE TABLE\s+(\w+)", chunk, re.IGNORECASE)
    if match:
        return match.group(1)
    return ""
