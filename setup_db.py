import sqlite3
import random
from datetime import datetime, timedelta

def setup_database():
    print("📦 Creating company_data.db...")
    conn = sqlite3.connect('company_data.db')
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            region TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            price REAL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            customer_id INTEGER,
            quantity INTEGER,
            sale_date TEXT,
            FOREIGN KEY (product_id) REFERENCES products (id),
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        )
    ''')

    # ── Emotion Detection Tables ──
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emotional_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            predicted_state TEXT NOT NULL,
            user_confirmed BOOLEAN DEFAULT 0,
            mean_zcr REAL DEFAULT 0.0,
            rms_variance REAL DEFAULT 0.0,
            voice_energy_level TEXT DEFAULT 'medium',
            suggestions TEXT DEFAULT '[]',
            timestamp TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS emotional_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            emotional_state_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            FOREIGN KEY (emotional_state_id) REFERENCES emotional_states(id)
        )
    ''')

    # Clear existing data just in case
    cursor.execute('DELETE FROM sales')
    cursor.execute('DELETE FROM products')
    cursor.execute('DELETE FROM customers')

    # Insert Dummy Data
    regions = ['North America', 'Europe', 'Asia', 'South America']
    customers = [(f'Customer {i}', random.choice(regions)) for i in range(1, 21)]
    cursor.executemany('INSERT INTO customers (name, region) VALUES (?, ?)', customers)

    categories = {
        'Electronics': [('Laptop Pro', 1200.00), ('Smartphone X', 800.00), ('Wireless Earbuds', 150.00), ('4K Monitor', 400.00)],
        'Clothing': [('Cotton T-Shirt', 25.00), ('Denim Jeans', 60.00), ('Winter Jacket', 120.00), ('Sneakers', 90.00)],
        'Home Goods': [('Coffee Maker', 85.00), ('Blender', 45.00), ('Vacuum Cleaner', 200.00), ('Desk Lamp', 30.00)]
    }

    product_ids = []
    for cat, prods in categories.items():
        for name, price in prods:
            cursor.execute('INSERT INTO products (name, category, price) VALUES (?, ?, ?)', (name, cat, price))
            product_ids.append(cursor.lastrowid)

    customer_ids = [row[0] for row in cursor.execute('SELECT id FROM customers').fetchall()]
    
    # Generate random sales for the last 90 days
    sales = []
    for _ in range(200):
        prod_id = random.choice(product_ids)
        cust_id = random.choice(customer_ids)
        qty = random.randint(1, 5)
        
        # Random date in the last 90 days
        days_ago = random.randint(0, 90)
        sale_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        
        sales.append((prod_id, cust_id, qty, sale_date))

    cursor.executemany('INSERT INTO sales (product_id, customer_id, quantity, sale_date) VALUES (?, ?, ?, ?)', sales)

    conn.commit()
    conn.close()
    print("✅ Database successfully created and populated with dummy e-commerce data!")

if __name__ == '__main__':
    setup_database()
