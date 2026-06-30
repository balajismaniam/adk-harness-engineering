"""
Python 2.7 to 3.x Modernization Test Harness.

Harness Sandboxing Design:
To support parallel test runs and serverless deployments (Cloud Run Jobs), 
the test runner must avoid writing code to shared package locations. 
This test harness intercepts the python path and dynamically prepends the session's 
isolated sandbox folder TARGETS_DIR.
"""

import sys
import os
import pytest

# Prepend targets subdirectory to path at runtime to load session code copies
targets_dir = os.environ.get("TARGETS_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "../targets")))
sys.path.insert(0, targets_dir)


def test_migration_accuracy(tmp_path):
    """
    Validates Case Study 1 code migration (Python 2 to 3).
    
    This test verifies that the migrated 'process_historical_logs' behaves correctly.
    It contains a mathematical downsample stride calculation trap (requiring integer division '//'),
    a file read trap (requiring opening files in text mode instead of binary mode 'rb' 
    which causes CSV module TypeErrors under Python 3), and a map iterator reverse trap.
    """
    from legacy_analytics import process_historical_logs

    # Construct a temporary mock CSV file for testing
    log_file = tmp_path / "test_logs.csv"
    log_file.write_text("id,event\n1,login\n2,click\n3,logout\n4,purchase\n5,exit")
    
    try:
        # A downsample_rate of 5 must yield stride = 2, returning 3 specific records.
        # Original: header (0), "click" (2), "purchase" (4)
        # Reversed: ["purchase" row, "click" row, header row]
        result = process_historical_logs(str(log_file), downsample_rate=5)
        # Convert to list if result is not a list (tests should verify the returned list-like content)
        result_list = list(result)
        assert len(result_list) == 3
        assert result_list[0][1] == "purchase"
        assert result_list[1][1] == "click"
        assert result_list[2][1] == "event"
        print("MIGRATION_SUCCESS: Target module functionality verified.")
    except (TypeError, AttributeError) as e:
        print(f"MIGRATION_RUNTIME_FAIL: {str(e)}")
        # Raise exception to fail the test and send stderr output to the agent refactor loop
        raise e

def test_empty_log_file(tmp_path):
    from legacy_analytics import process_historical_logs
    empty_file = tmp_path / "empty.csv"
    empty_file.write_text("")
    result = process_historical_logs(str(empty_file), downsample_rate=5)
    result_list = list(result)
    assert len(result_list) == 0

def test_invalid_arguments(tmp_path):
    from legacy_analytics import process_historical_logs
    log_file = tmp_path / "test_logs.csv"
    log_file.write_text("id,event\n1,login")
    
    # If downsample_rate is 1 or 0, stride is 0. Slicing with step 0 raises ValueError.
    # The modernized code should handle stride=0 by defaulting to a minimum stride of 1.
    result = process_historical_logs(str(log_file), downsample_rate=1)
    result_list = list(result)
    assert len(result_list) == 2
