# vulnerable_query.py
import sqlite3

def search_user(db_path, username, column="profile"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = f"SELECT {column} FROM users WHERE username = '{username}'"
    cursor.execute(query)
    results = [row[0] for row in cursor.fetchall()]
    conn.close()
    return results
