from llama_index.core import StorageContext, load_index_from_storage
from rag_utils import embed_model

# Same embedding model you used for indexing
storage_context = StorageContext.from_defaults(persist_dir="./storage")
index = load_index_from_storage(storage_context, embed_model=embed_model)

# Access stored documents
docs = index.docstore.docs

print("\nStored documents:")
for doc_id, doc in docs.items():
    print(f"ID: {doc_id}")
    print(f"Text: {doc.text[:500]}")
    print("-" * 50)
