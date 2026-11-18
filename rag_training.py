from llama_index.core import VectorStoreIndex, Document, StorageContext, load_index_from_storage
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.query_engine import RetrieverQueryEngine
from config import LLM_NAME, SQLQA_STORAGE_DIR

embed_model = HuggingFaceEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
llm = Ollama(model=LLM_NAME)

def create_sql_qa_document(question: str, sql_query: str) -> Document:
    """Wrap question + query as a single document."""
    text = f"Question: {question.strip()}\nSQL Query: {sql_query.strip()}"
    return Document(text=text, metadata={"type": "sql_qa"})

def index_sql_qa_pair(question: str, sql_query: str):
    """Index a question-query pair into vector DB."""
    doc = create_sql_qa_document(question, sql_query)
    index = VectorStoreIndex.from_documents([doc], embed_model=embed_model)
    index.storage_context.persist(persist_dir=SQLQA_STORAGE_DIR)
    return index

def add_sql_qa_batch(pairs: list) -> int:

    docs = []
    for item in pairs:
        q = item.get("question")
        sql = item.get("sql_query")
        if q and sql:
            text = f"Question: {q.strip()}\nSQL Query: {sql.strip()}"
            docs.append(Document(text=text, metadata={"type": "sql_qa"}))

    if not docs:
        raise ValueError("No valid question-query pairs found.")
    


    try:
        storage_context = StorageContext.from_defaults(persist_dir=SQLQA_STORAGE_DIR)
        index = load_index_from_storage(storage_context, embed_model=embed_model)
    except Exception:
        index = VectorStoreIndex.from_documents(docs, embed_model=embed_model)
        index.storage_context.persist(persist_dir=SQLQA_STORAGE_DIR)
        return len(docs)

    for doc in docs:
        index.insert(doc)
    index.storage_context.persist(persist_dir=SQLQA_STORAGE_DIR)
    return len(docs)


def query_sql_qa_rag(user_question: str) -> str:
    """Query saved SQL question-query vector DB for similar entries."""
    storage_context = StorageContext.from_defaults(persist_dir=SQLQA_STORAGE_DIR)
    index = load_index_from_storage(storage_context, embed_model=embed_model)
    query_engine = RetrieverQueryEngine.from_args(index.as_retriever(), llm=llm)

    response_obj = query_engine.query(user_question)
    chunks = [node.text for node in response_obj.source_nodes]
    if not chunks:
        return "❌ No examples could be retrieved from the SQL QA DB."
    return "\n\n---\n\n".join(chunks)
