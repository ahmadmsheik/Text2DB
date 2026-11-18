from llama_index.core import VectorStoreIndex, Document, StorageContext, load_index_from_storage
from llama_index.llms.ollama import Ollama
from llama_index.core.query_engine import RetrieverQueryEngine
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from config import LLM_NAME
from llama_index.core.text_splitter import TokenTextSplitter


embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
llm = Ollama(model=LLM_NAME)


def create_schema_document(schema_text: str, schema_id: str = "default") -> Document:
    return Document(text=schema_text, metadata={"type": "schema", "schema_id": schema_id})

def index_schema_with_embeddings(schema_text: str):
    text_splitter = TokenTextSplitter(chunk_size=4096, chunk_overlap=0)
    nodes = text_splitter.split_text(schema_text)
    documents = [Document(text=node) for node in nodes]
    


    try:
        storage_context = StorageContext.from_defaults(persist_dir="./storage")
        index = load_index_from_storage(storage_context, embed_model=embed_model)
    except Exception as e:
        index = VectorStoreIndex.from_documents(documents, embed_model=embed_model)
        index.storage_context.persist(persist_dir="./storage") 
        return index
        
    for doc in documents:
        index.insert(doc)
    index.storage_context.persist(persist_dir="./storage")
    return index



def query_schema_rag(question: str):
    storage_context = StorageContext.from_defaults(persist_dir="./storage")
    index = load_index_from_storage(storage_context, embed_model=embed_model)
    query_engine = RetrieverQueryEngine.from_args(index.as_retriever(), llm=llm)
    response_obj = query_engine.query(question)
    chunk_texts = [node.text for node in response_obj.source_nodes]
    if not chunk_texts:
        return "❌ No examples could be retrieved."
    return "\n\n---\n\n".join(chunk_texts)
