import sqlite3
 
def get_connection():
    conn = sqlite3.connect("work_orders.db", check_same_thread=False)
    return conn
 
 
def create_table():
    conn = get_connection()
    cursor = conn.cursor()
 
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS work_orders (
        work_order_no TEXT PRIMARY KEY,
        work_center TEXT,
        mat_no TEXT,
        mat_desc TEXT,
        total_qty INTEGER,
        completed_qty INTEGER,
        status TEXT,
        start_date TEXT,
        end_date TEXT
    )
    """)
 
    conn.commit()
    conn.close()