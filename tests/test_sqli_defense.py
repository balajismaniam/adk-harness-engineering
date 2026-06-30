"""
SQL Injection (SQLi) Defense Verification Test Harness.

Harness Pentesting Design:
This test harness acts as the execution validator for the Adversarial Red/Blue Debate.
It executes actual SQL injection attack strings (union queries, comment truncations, 
and command injections) against a temporary session SQLite database.
Defensive compliance is met only if:
1. Standard, non-malicious query flows return expected profiles.
2. Attack strings return empty results (parameterized successfully) or throw exceptions,
   proving they failed to compromise database logic.
"""

import sys
import os
import sqlite3
import pytest

# Prepend targets subdirectory to path at runtime to load session code copies
targets_dir = os.environ.get("TARGETS_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "../targets")))
sys.path.insert(0, targets_dir)

from vulnerable_query import search_user

DB_PATH = os.path.join(targets_dir, "test_users.db")

@pytest.fixture(autouse=True)
def setup_db():
    """
    Autouse fixture that runs before and after each test.
    
    Creates a temporary local SQLite database, inserts test records, 
    and removes the database file when teardown runs.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS users")
    cursor.execute("CREATE TABLE users (username TEXT, profile TEXT)")
    cursor.execute("INSERT INTO users VALUES ('alice', 'Alice profile data')")
    cursor.execute("INSERT INTO users VALUES ('bob', 'Bob profile data')")
    cursor.execute("INSERT INTO users VALUES ('charlie', 'Charlie admin data')")
    conn.commit()
    conn.close()
    yield
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

def test_normal_queries():
    """
    Verifies that the target code handles basic, non-malicious queries correctly.
    """
    # 1. Query default column (profile)
    res = search_user(DB_PATH, "alice")
    assert res == ["Alice profile data"]
    
    # 2. Query specific column (username)
    res_user = search_user(DB_PATH, "bob", column="username")
    assert res_user == ["bob"]

def test_username_sqli_prevention():
    """
    Validates SQL Injection (SQLi) defenses on the username parameter.
    """
    payloads = [
        "' OR '1'='1",
        "alice' OR '1'='1",
        "nonexistent' UNION SELECT profile FROM users --",
        "bob' --"
    ]
    for p in payloads:
        try:
            res = search_user(DB_PATH, p)
        except sqlite3.Error:
            # SQL compilation failures (e.g. unclosed quotes) are secure behaviors.
            continue
        
        # Safe parameterized queries return 0 rows for literal payloads containing logic keywords
        assert len(res) == 0, f"SQL Injection vulnerability verified for payload: {p}. Returned: {res}"

def test_column_sqli_prevention_and_validation():
    """
    Validates SQL Injection defenses and parameter validation on the column parameter.
    Any dynamic column inputs must be allowlisted to prevent column-based SQLi.
    """
    malicious_columns = [
        "profile; DROP TABLE users; --",
        "profile UNION SELECT username FROM users --",
        "invalid_column"
    ]
    for col in malicious_columns:
        with pytest.raises((ValueError, sqlite3.Error)):
            search_user(DB_PATH, "alice", column=col)
