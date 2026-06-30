# user_dao.py
from db_helper import get_connection
def get_user_profile(user_id):
    conn = get_connection("prod_db")
    return f"User profile for {user_id} using [{conn}]"
