#!/usr/bin/env python3
"""
Comprehensive debugging script to trace the entire indexing process 
to identify why only the first table is being saved.
"""

import os
import shutil
from db_utils import load_database_connections
from v2 import extract_create_table_list, generate_table_descriptions, split_described_chunks_per_table
from rag_systemv2 import index_schema_chunks_rag
from sqlalchemy import create_engine, text

def debug_step_by_step():
    print("=" * 60)
    print("🔍 DEBUGGING SCHEMA INDEXING PROCESS")
    print("=" * 60)
    
    # Load connection
    connections = load_database_connections()
    if "SchoolDB" not in connections:
        print("❌ SchoolDB not found in connections")
        return
    
    connection_uri = connections["SchoolDB"]
    print(f"✅ Connection URI: {connection_uri}")
    
    # Step 1: Check what tables exist in the database
    print("\n" + "=" * 50)
    print("📊 STEP 1: Checking database tables")
    print("=" * 50)
    
    engine = create_engine(connection_uri)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
        ))
        tables = [row[0] for row in result.fetchall()]
        print(f"📋 Tables in database: {tables}")
        print(f"📊 Total tables found: {len(tables)}")
    
    # Step 2: Extract CREATE TABLE statements
    print("\n" + "=" * 50)
    print("🔧 STEP 2: Extracting CREATE TABLE statements")
    print("=" * 50)
    
    schema_chunks = extract_create_table_list(connection_uri)
    print(f"📝 Total schema chunks extracted: {len(schema_chunks)}")
    
    for i, chunk in enumerate(schema_chunks):
        print(f"\n--- Schema Chunk {i+1} ---")
        print(f"Length: {len(chunk)} characters")
        print(f"First 100 chars: {chunk[:100]}...")
        
        # Extract table name
        table_name = chunk.split('(')[0].replace('CREATE TABLE', '').strip()
        print(f"Table name: {table_name}")
    
    # Step 3: Generate table descriptions
    print("\n" + "=" * 50)
    print("📝 STEP 3: Generating table descriptions")
    print("=" * 50)
    
    described_chunks = generate_table_descriptions(schema_chunks)
    print(f"📖 Total described chunks: {len(described_chunks)}")
    
    for i, chunk in enumerate(described_chunks):
        print(f"\n--- Described Chunk {i+1} ---")
        print(f"Length: {len(chunk)} characters")
        print(f"First 200 chars: {chunk[:200]}...")
    
    # Step 4: Split chunks per table
    print("\n" + "=" * 50)
    print("✂️ STEP 4: Splitting chunks per table")
    print("=" * 50)
    
    split_chunks = split_described_chunks_per_table(described_chunks)
    print(f"📑 Total split chunks: {len(split_chunks)}")
    
    for i, chunk in enumerate(split_chunks):
        print(f"\n--- Split Chunk {i+1} ---")
        print(f"Length: {len(chunk)} characters")
        print(f"First 200 chars: {chunk[:200]}...")
        
        # Try to extract table name from chunk
        if "**CREATE TABLE" in chunk:
            try:
                table_name = chunk.split('**CREATE TABLE')[1].split(';')[0].strip()
                print(f"Extracted table name: {table_name}")
            except:
                print("❌ Could not extract table name")
    
    # Step 5: Debug the indexing process
    print("\n" + "=" * 50)
    print("🔍 STEP 5: Debugging indexing process")
    print("=" * 50)
    
    # Remove old storage first
    storage_path = "./storage/SchoolDB"
    if os.path.exists(storage_path):
        print(f"🗑️ Removing old storage: {storage_path}")
        shutil.rmtree(storage_path)
    
    # Let's debug what happens in the indexing function
    print(f"📦 About to index {len(split_chunks)} chunks...")
    
    # Call the indexing function
    try:
        index_schema_chunks_rag(split_chunks, "SchoolDB")
        print("✅ Indexing completed successfully")
    except Exception as e:
        print(f"❌ Indexing failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 6: Verify what got indexed
    print("\n" + "=" * 50)
    print("🔍 STEP 6: Verifying indexed content")
    print("=" * 50)
    
    # Check the docstore
    docstore_path = os.path.join(storage_path, "docstore.json")
    if os.path.exists(docstore_path):
        import json
        with open(docstore_path, 'r') as f:
            docstore = json.load(f)
        
        print(f"📂 Docstore file exists: {docstore_path}")
        
        # Check ref_doc_info for table names
        ref_doc_info = docstore.get("docstore/ref_doc_info", {})
        print(f"📊 Total documents in docstore: {len(ref_doc_info)}")
        
        for doc_id, info in ref_doc_info.items():
            metadata = info.get("metadata", {})
            table_name = metadata.get("table_name", "unknown")
            db_name = metadata.get("db_name", "unknown")
            print(f"  - Doc ID: {doc_id[:8]}... | Table: {table_name} | DB: {db_name}")
    else:
        print("❌ Docstore file not found")
    
    # Step 7: Test retrieval
    print("\n" + "=" * 50)
    print("🔍 STEP 7: Testing retrieval")
    print("=" * 50)
    
    from llm_utilsv2 import retrieve_table_descriptions
    
    # Test retrieving each table
    for table in tables:
        print(f"\n--- Testing retrieval for: {table} ---")
        try:
            descriptions = retrieve_table_descriptions([table], "SchoolDB")
            print(f"✅ Retrieved {len(descriptions)} descriptions")
            for i, desc in enumerate(descriptions):
                print(f"  Description {i+1}: {desc[:100]}...")
        except Exception as e:
            print(f"❌ Retrieval failed for {table}: {e}")

if __name__ == "__main__":
    debug_step_by_step()
