"""
Multi-File Dependency Refactoring Test Harness.

Harness Mocking Design:
When verifying signature changes propagating across importing modules (user_dao, admin_service),
actual network database connections are not required. This test harness:
1. Intercepts paths to load session-isolated modules.
2. Injects dummy mock modules for 'mysql' to prevent collection-time import crashes.
3. Uses unittest.mock.patch to inspect parameter propagation across file boundaries.
"""

import sys
import os

# Dynamically inject the target subdirectory at index 0 of sys.path.
# If TARGETS_DIR is set in the environment, it uses that path to support isolated test runs.
targets_dir = os.environ.get("TARGETS_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "../targets")))
sys.path.insert(0, targets_dir)


import pytest
import inspect
from unittest.mock import patch, MagicMock

# Define dummy mock modules for mysql to prevent import crashes during testing, 
# as actual mysql-connector-python libraries are not required for these mock signature tests.
sys.modules['mysql'] = MagicMock()
sys.modules['mysql.connector'] = MagicMock()

from db_helper import get_connection


def test_db_helper_signature():
    """
    Validates the signature of db_helper.get_connection.
    
    Uses python's native 'inspect' module to verify that the agent successfully 
    refactored the method signature to include host, port, user, and password parameters.
    """
    sig = inspect.signature(get_connection)
    assert "host" in sig.parameters, "host parameter missing in get_connection"
    assert "port" in sig.parameters, "port parameter missing in get_connection"
    assert "user" in sig.parameters, "user parameter missing in get_connection"
    assert "password" in sig.parameters, "password parameter missing in get_connection"


@patch("user_dao.get_connection", autospec=True)
def test_user_dao_usage(mock_get_conn):
    """
    Validates that user_dao has adopted the new parameterized signature of get_connection.
    
    Using unittest.mock.patch, we intercept calls to get_connection inside user_dao, 
    and inspect call arguments to confirm parameter propagation.
    """
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn
    
    from user_dao import get_user_profile
    get_user_profile("user123")
        
    assert mock_get_conn.called, "get_connection was not called by user_dao"
    _, kwargs = mock_get_conn.call_args
    assert "host" in kwargs, "host parameter not passed to get_connection"
    assert "port" in kwargs, "port parameter not passed to get_connection"
    assert "user" in kwargs, "user parameter not passed to get_connection"


@patch("admin_service.get_connection", autospec=True)
def test_admin_service_usage(mock_get_conn):
    """
    Validates that admin_service has adopted the new parameterized signature of get_connection.
    """
    mock_conn = MagicMock()
    mock_get_conn.return_value = mock_conn
    
    from admin_service import run_maintenance
    run_maintenance()
        
    assert mock_get_conn.called, "get_connection was not called by admin_service"
    _, kwargs = mock_get_conn.call_args
    assert "host" in kwargs, "host parameter not passed to get_connection"
    assert "port" in kwargs, "port parameter not passed to get_connection"
    assert "user" in kwargs, "user parameter not passed to get_connection"


