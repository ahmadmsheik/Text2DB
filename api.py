from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from auth_utils import register_user, login_user
from llm_utils import classify_input, generate_sql_query, generate_general_response, generate_correction_responsev2
from db_utils import (
    run_query, 
    get_all_databases, 
    create_db_reader,
    save_db_list_with_connection,
    try_connect_to_database,
    load_database_connections
)
from memory_utils import get_memory, update_memory, save_memory_to_disk
from v2 import extract_create_table_list, generate_table_descriptions, split_described_chunks_per_table, extract_join_graph_from_db, save_join_graph
from rag_systemv2 import index_schema_chunks_rag
from llm_utilsv2 import run_text_to_sql_pipeline
import pandas as pd
import json

app = FastAPI()

# CORS settings (allow React frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- HELPER FUNCTIONS --------------------
def ensure_database_initialized(db_name: str):
    """Ensure database reader is initialized for the given database."""
    try:
        connections = load_database_connections()
        if db_name not in connections:
            raise HTTPException(status_code=400, detail=f"Database '{db_name}' not found in saved connections")
        
        connection_uri = connections[db_name]
        db_reader = create_db_reader(connection_uri)
        if db_reader is None:
            raise HTTPException(status_code=500, detail=f"Failed to initialize database reader for '{db_name}'")
        
        return db_reader
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error initializing database: {str(e)}")

# -------------------- MODELS --------------------
class AuthInput(BaseModel):
    username: str
    password: str
    role: str | None = None

class QuestionInput(BaseModel):
    user_id: str
    question: str
    db_name: str | None = None

class QueryInput(BaseModel):
    sql_query: str
    db_name: str | None = None

class CorrectionInput(BaseModel):
    question: str
    bad_query: str
    error_message: str
    table_descriptions: list[str]
    joins: list[str]

class DatabaseConnection(BaseModel):
    server: str
    db_name: str
    driver: str = "ODBC Driver 17 for SQL Server"

class ChartInput(BaseModel):
    user_id: str
    question: str
    chart_type: str
    db_name: str



@app.post("/api/login")
def login(data: AuthInput):
    result = login_user(data.username, data.password)
    if result["success"]:
        return result
    raise HTTPException(status_code=401, detail=result["message"])


@app.post("/api/register")
def register(data: AuthInput):
    result = register_user(data.username, data.password, data.role)
    if result["success"]:
        return result
    raise HTTPException(status_code=400, detail=result["message"])


@app.post("/api/ask")
def ask(data: QuestionInput):
    try:
        update_memory(data.user_id, "user", data.question)
        route = classify_input(data.question)
        
        if route == "sql":
            if not data.db_name:
                raise HTTPException(status_code=400, detail="Database name required for SQL queries")
            
            # Initialize database reader for the specified database
            ensure_database_initialized(data.db_name)
            
            sql_query, table_descriptions, joins = run_text_to_sql_pipeline(data.question, data.db_name)
            
            success, result = run_query(sql_query)
            if success:
                if isinstance(result, list) and all(isinstance(row, dict) for row in result):
                    df = pd.DataFrame(result)
                    answer = df.to_dict('records')
                else:
                    answer = str(result)
                
                update_memory(data.user_id, "assistant", str(answer))
                return {
                    "type": "sql",
                    "query": sql_query,
                    "success": True,
                    "result": answer,
                    "table_descriptions": table_descriptions,
                    "joins": joins
                }
            else:
                # Auto-correction
                corrected_query = generate_correction_responsev2(
                    question=data.question,
                    bad_query=sql_query,
                    error_message=result,
                    table_descriptions=table_descriptions,
                    joins=joins
                )
                
                success, corrected_result = run_query(corrected_query)
                if success:
                    if isinstance(corrected_result, list) and all(isinstance(row, dict) for row in corrected_result):
                        df = pd.DataFrame(corrected_result)
                        answer = df.to_dict('records')
                    else:
                        answer = str(corrected_result)
                    
                    update_memory(data.user_id, "assistant", str(answer))
                    return {
                        "type": "sql",
                        "query": corrected_query,
                        "success": True,
                        "result": answer,
                        "corrected": True,
                        "original_query": sql_query,
                        "original_error": result
                    }
                else:
                    return {
                        "type": "sql",
                        "success": False,
                        "error": "Both original and corrected queries failed",
                        "original_query": sql_query,
                        "original_error": result,
                        "corrected_query": corrected_query,
                        "corrected_error": corrected_result
                    }
        else:
            response = generate_general_response(data.question, get_memory(data.user_id))
            update_memory(data.user_id, "assistant", str(response))
            return {"type": "general", "response": str(response)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/run_query")
def execute_query(data: QueryInput):
    # Initialize database reader if db_name is provided
    if data.db_name:
        ensure_database_initialized(data.db_name)
    
    success, result = run_query(data.sql_query)
    if success:
        if isinstance(result, list) and all(isinstance(row, dict) for row in result):
            df = pd.DataFrame(result)
            return {"success": True, "result": df.to_dict('records')}
        return {"success": True, "result": result}
    else:
        return {"success": False, "error": str(result)}


@app.post("/api/connect_database")
def connect_database(data: DatabaseConnection):
    try:
        print(f"🔍 API: Connecting to database {data.db_name}...")
        success, result = try_connect_to_database(data.server, data.db_name)
        if success:
            connection_uri = result
            print(f"✅ API: Connected to {data.db_name} at {result}")
            save_db_list_with_connection(data.db_name, connection_uri)
            print("💾 API: Saved DB connection")
            
            # Initialize database reader
            db_reader = create_db_reader(connection_uri)
            if db_reader is None:
                raise HTTPException(status_code=500, detail="Failed to initialize database reader")
            print("🔧 API: Database reader initialized")
            
            # Extract and index schema
            schema_chunks = extract_create_table_list(connection_uri)
            print(f"📝 API: Extracted {len(schema_chunks)} schema chunks")
            described_chunks = generate_table_descriptions(schema_chunks)
            print(f"📖 API: Generated descriptions for {len(described_chunks)} chunks")
            chunks = split_described_chunks_per_table(described_chunks)
            print(f"📑 API: Split into {len(chunks)} individual chunks")
            
            index_schema_chunks_rag(chunks, data.db_name)
            print("✅ API: Indexing completed")
            
            join_graph = extract_join_graph_from_db(connection_uri)
            save_join_graph(db_name=data.db_name, join_graph=join_graph)
            print(f"🔗 API: Join graph saved with {len(join_graph)} relationships")
            
            return {
                "success": True,
                "message": "Database connected and schema indexed successfully",
                "db_name": data.db_name,
                "connection_uri": connection_uri,
                "schema_extracted": schema_chunks,
                "saved_chunks": chunks,
                "total_tables": len(schema_chunks),
                "total_chunks": len(chunks)
            }
        else:
            raise HTTPException(status_code=400, detail=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/saved_databases")
def get_saved_databases():
    try:
        connections = load_database_connections()
        return {"databases": list(connections.keys())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chart")
def generate_chart(data: ChartInput):
    try:
        # Initialize database reader for the specified database
        ensure_database_initialized(data.db_name)
        
        # Use the new pipeline for chart generation
        sql_query, table_descriptions, joins = run_text_to_sql_pipeline(data.question, data.db_name)
        success, result = run_query(sql_query)
        
        if success and isinstance(result, list) and all(isinstance(row, dict) for row in result):
            df = pd.DataFrame(result)
            # Convert to numeric where possible
            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='ignore')
            
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            
            return {
                "success": True,
                "data": df.to_dict('records'),
                "columns": list(df.columns),
                "numeric_columns": numeric_cols,
                "query": sql_query
            }
        else:
            return {
                "success": False,
                "error": "Query didn't return valid data for charting"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/databases")
def list_databases():
    return get_all_databases()


@app.post("/api/logout")
def logout(user_id: str):
    try:
        save_memory_to_disk(user_id)
        return {"message": "Logged out successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
