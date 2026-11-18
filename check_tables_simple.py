import json
from sqlalchemy import create_engine, text

# Load connection
with open("available_databases.json", "r") as f:
    data = json.load(f)

if "SchoolDB" in data.get("databases", {}):
    connection_uri = data["databases"]["SchoolDB"]
    print(f"Connection URI: {connection_uri}")
    
    # Check what tables exist
    engine = create_engine(connection_uri)
    with engine.connect() as conn:
        result = conn.execute(text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
        ))
        tables = [row[0] for row in result.fetchall()]
        print(f"Tables found: {tables}")
        print(f"Total tables: {len(tables)}")
        
        # Check if we have the expected tables
        expected_tables = ["Students", "Enrollments", "Courses"]
        for table in expected_tables:
            if table in tables:
                print(f"✅ {table} exists")
            else:
                print(f"❌ {table} does NOT exist")
else:
    print("SchoolDB not found in connections")
