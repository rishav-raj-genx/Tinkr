import sqlite3
import json

DB_NAME = 'company_data.db'

def get_database_schema() -> str:
    """Returns the schema of the database to help formulate SQL queries."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        schema = {}
        for table in tables:
            table_name = table[0]
            if table_name != 'sqlite_sequence':
                cursor.execute(f"PRAGMA table_info({table_name});")
                columns = cursor.fetchall()
                schema[table_name] = [col[1] + f" ({col[2]})" for col in columns]
                
        conn.close()
        return json.dumps(schema, indent=2)
    except Exception as e:
        return f"Error fetching schema: {e}"

def execute_sql_query(query: str) -> str:
    """Executes a read-only SQL query and returns the results."""
    # Security: Ensure it's a read-only query
    query_upper = query.upper().strip()
    if not query_upper.startswith("SELECT"):
        return json.dumps({"error": "Only SELECT queries are allowed."})
        
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row  # To return dicts
        cursor = conn.cursor()
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        results = []
        for row in rows:
            results.append(dict(row))
            
        conn.close()
        
        # Return as JSON string so the frontend can parse it easily
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})
