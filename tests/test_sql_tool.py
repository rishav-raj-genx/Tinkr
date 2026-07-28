"""Tests for the sql_tool module."""

import json
import sqlite3
import tempfile
import os

import pytest
from sql_tool import get_database_schema, execute_sql_query, DB_NAME


@pytest.fixture(autouse=True)
def temp_db():
    """Replace the real DB with a temporary in-memory one for tests."""
    # The module uses a file-level DB_NAME; we patch by creating a temp file
    old_db = DB_NAME
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    test_db = tmp.name

    # Override the module constant by patching
    import sql_tool
    sql_tool.DB_NAME = test_db

    # Create schema and seed data
    conn = sqlite3.connect(test_db)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY, name TEXT, region TEXT)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL)"
    )
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY, product_id INTEGER, customer_id INTEGER, quantity INTEGER, sale_date TEXT)"
    )
    cursor.execute("INSERT INTO customers (name, region) VALUES (?, ?)", ("Alice", "Europe"))
    cursor.execute("INSERT INTO customers (name, region) VALUES (?, ?)", ("Bob", "North America"))
    cursor.execute("INSERT INTO products (name, category, price) VALUES (?, ?, ?)", ("Widget", "Gadgets", 9.99))
    conn.commit()
    conn.close()

    yield

    # Cleanup
    sql_tool.DB_NAME = old_db
    os.unlink(test_db)


class TestGetDatabaseSchema:
    """Tests for get_database_schema."""

    def test_returns_valid_json(self):
        """Schema should be valid JSON."""
        result = get_database_schema()
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_includes_customers_table(self):
        """Schema should include the customers table."""
        result = json.loads(get_database_schema())
        assert "customers" in result

    def test_products_table_has_price_column(self):
        """Products table should have a price column."""
        result = json.loads(get_database_schema())
        products_cols = " ".join(result["products"])
        assert "price" in products_cols

    def test_includes_sales_table(self):
        """Schema should include the sales table."""
        result = json.loads(get_database_schema())
        assert "sales" in result


class TestExecuteSqlQuery:
    """Tests for execute_sql_query."""

    def test_select_all_customers(self):
        """SELECT should return all rows."""
        result = json.loads(execute_sql_query("SELECT * FROM customers"))
        assert len(result) == 2

    def test_select_with_where(self):
        """SELECT with WHERE should filter correctly."""
        result = json.loads(execute_sql_query("SELECT * FROM customers WHERE region = 'Europe'"))
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_rejects_non_select(self):
        """Non-SELECT queries should be rejected."""
        result = json.loads(execute_sql_query("DELETE FROM customers"))
        assert "error" in result

    def test_select_specific_columns(self):
        """SELECT with specific columns should work."""
        result = json.loads(execute_sql_query("SELECT name, region FROM customers"))
        assert len(result) == 2
        assert "name" in result[0]
        assert "id" not in result[0]

    @pytest.mark.network
    def test_invalid_sql(self):
        """Invalid SQL should return an error."""
        result = json.loads(execute_sql_query("SELECT * FROM nonexistent_table"))
        assert "error" in result

    def test_empty_result(self):
        """SELECT that returns nothing should return empty list."""
        result = json.loads(execute_sql_query("SELECT * FROM customers WHERE region = 'Mars'"))
        assert result == []

    def test_aggregate_query(self):
        """AGGREGATE queries should work."""
        result = json.loads(execute_sql_query("SELECT COUNT(*) as cnt FROM customers"))
        assert result[0]["cnt"] == 2
