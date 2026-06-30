# admin_service.py
from db_helper import get_connection
def run_maintenance():
    conn = get_connection("prod_db")
    return f"Maintenance run complete using [{conn}]"
