# Text2DB

Text2DB is a local SQL question-answering assistant. It uses Ollama for language-model responses, LlamaIndex for schema retrieval, and SQL Server for query execution. The Streamlit app is the primary user interface; a FastAPI backend is also available.

> The React frontend is intentionally excluded from this repository because it is not currently working.

## Prerequisites

- Windows with Python 3.10 or later
- [Ollama](https://ollama.com/) and the `llama3:8b` model
- SQL Server with a database you can access
- Microsoft ODBC Driver 17 for SQL Server

The configured LLM is `llama3:8b` in `config.py`. Schema embeddings use `sentence-transformers/all-MiniLM-L6-v2`; the model may be downloaded the first time it is needed.

## Setup

Run these commands from the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install fastapi "uvicorn[standard]" pydantic pandas sqlalchemy pyodbc streamlit matplotlib seaborn json-repair llama-index-core llama-index-readers-database llama-index-llms-ollama llama-index-embeddings-huggingface
```

Dependencies are not currently pinned in a requirements file.

Start Ollama and download the configured model:

```powershell
ollama pull llama3:8b
```

Keep the Ollama service running while using the app.

## Run the Streamlit app

```powershell
streamlit run main_uiv2.py
```

Open the local URL printed by Streamlit (usually <http://localhost:8501>). Register a local account, then use **Connect to SQL Server** to connect to an existing database and index its schema.

## Run the API

In another terminal, with the virtual environment activated:

```powershell
python -m uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

The interactive API docs are at <http://127.0.0.1:8000/docs>. The React frontend is not included, so the API must be used directly or with a separate client.

## Local data and security

User accounts, conversation history, saved database connections, correction logs, and generated vector indexes are local runtime data and are excluded from Git. The app creates or updates these files as it runs.

This project is for local development and experimentation, not production deployment. The current authentication code stores passwords as plain text in the local `users.json` file. Use only disposable demo credentials; do not use real or reused passwords, and do not expose the app publicly.
