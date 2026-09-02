"""
Unit tests for the cloud-run-sandbox package.
"""

import json
import os
import sys
import importlib
import pytest

# Ensure workspace root is in sys.path
workspace_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if workspace_root not in sys.path:
    sys.path.insert(0, workspace_root)

# Import cloud-run-sandbox package dynamically
sandbox_pkg = importlib.import_module("cloud-run-sandbox")
is_sandbox_available = sandbox_pkg.is_sandbox_available
get_sandbox_binary = sandbox_pkg.get_sandbox_binary
execute_sandbox_command = sandbox_pkg.execute_sandbox_command
verify_sandbox_security_isolation = sandbox_pkg.verify_sandbox_security_isolation
strip_markdown_code = sandbox_pkg.strip_markdown_code
run_modernization_repair_loop = sandbox_pkg.run_modernization_repair_loop
CloudRunSandboxTelemetry = sandbox_pkg.CloudRunSandboxTelemetry


def test_sandbox_availability_check():
    """Verifies that sandbox binary detection functions without error."""
    avail = is_sandbox_available()
    assert isinstance(avail, bool)
    bin_path = get_sandbox_binary()
    if avail:
        assert bin_path is not None
    else:
        assert bin_path is None or not os.path.exists(bin_path)


def test_execute_sandbox_command_local_fallback(tmp_path):
    """Verifies execution of a standard command in the sandbox/fallback runner."""
    test_file = tmp_path / "hello.py"
    test_file.write_text("print('Sandbox test output')")

    code, output, duration_ms, sandbox_used = execute_sandbox_command(
        command=["python3", str(test_file)],
        mount_dir=str(tmp_path),
        timeout_seconds=5,
    )

    assert code == 0
    assert "Sandbox test output" in output
    assert duration_ms > 0
    assert isinstance(sandbox_used, bool)


def test_verify_sandbox_security_isolation():
    """Verifies security isolation reporting schema."""
    sec = verify_sandbox_security_isolation()
    assert "metadata_blocked" in sec
    assert "egress_denied" in sec
    assert "sandbox_active" in sec


def test_strip_markdown_code():
    """Verifies markdown stripping from LLM outputs."""
    raw_md = "```python\nprint('hello world')\n```"
    stripped = strip_markdown_code(raw_md)
    assert stripped == "print('hello world')"

    raw_plain = "print('plain code')"
    assert strip_markdown_code(raw_plain) == "print('plain code')"


def test_mock_repair_loop_execution():
    """Verifies full execution of the mock modernization repair loop."""
    tel = run_modernization_repair_loop(
        target_source_path="targets/legacy_analytics.py",
        test_harness_path="tests/test_harness.py",
        max_cycles=5,
        mock=True,
    )

    assert isinstance(tel, CloudRunSandboxTelemetry)
    assert tel.scenario_name == "Python_2_to_3_Semantic_Migration"
    assert tel.target_module == "legacy_analytics.py"
    assert tel.functional_test_passed is True
    assert tel.total_iterations == 4
    assert tel.wall_clock_latency_seconds > 0
    assert tel.total_input_tokens > 0
    assert tel.total_output_tokens > 0
    assert len(tel.iteration_traces) == 4
    assert tel.iteration_traces[0].exit_code != 0
    assert tel.iteration_traces[-1].exit_code == 0
    assert tel.final_repaired_code is not None


def test_server_endpoints():
    """Verifies that SandboxHTTPRequestHandler handles health checks and /run in mock mode."""
    import threading
    import urllib.request
    import json
    from http.server import HTTPServer

    server_mod = importlib.import_module("cloud-run-sandbox.server")
    SandboxHTTPRequestHandler = server_mod.SandboxHTTPRequestHandler

    # Start server on dynamic OS-assigned port
    httpd = HTTPServer(("127.0.0.1", 0), SandboxHTTPRequestHandler)
    port = httpd.server_address[1]
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        # Test GET /healthz
        req = opener.open(f"http://127.0.0.1:{port}/healthz", timeout=5)
        assert req.status == 200
        data = json.loads(req.read().decode("utf-8"))
        assert data["status"] == "ok"
        assert data["service"] == "adk-sandbox-service"

        # Test POST /run (mock mode)
        post_data = json.dumps({"mock": True}).encode("utf-8")
        post_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/run",
            data=post_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        post_resp = opener.open(post_req, timeout=10)
        assert post_resp.status == 200
        run_data = json.loads(post_resp.read().decode("utf-8"))
        assert run_data["functional_test_passed"] is True
        assert run_data["total_iterations"] == 4
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_requirements_file():
    """Verifies that cloud-run-sandbox contains standalone requirements.txt for Buildpack deploys."""
    req_path = os.path.join(workspace_root, "cloud-run-sandbox", "requirements.txt")
    assert os.path.exists(req_path), "cloud-run-sandbox/requirements.txt missing"
    with open(req_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "google-genai" in content
    assert "pydantic" in content
    assert "pytest" in content


def test_self_contained_repair_loop_with_default_paths():
    """Verifies that repair loop succeeds even when external file paths do not exist on disk."""
    tel = run_modernization_repair_loop(
        target_source_path="/nonexistent/legacy_analytics.py",
        test_harness_path="/nonexistent/test_harness.py",
        max_cycles=5,
        mock=True,
    )
    assert tel.functional_test_passed is True
    assert tel.total_iterations == 4
    assert tel.final_repaired_code is not None


def test_main_entrypoint_and_deploy_scripts():
    """Verifies main.py exists and deployment scripts use valid source deploy commands."""
    main_file = os.path.join(workspace_root, "cloud-run-sandbox", "main.py")
    assert os.path.exists(main_file), "cloud-run-sandbox/main.py missing"

    job_script = os.path.join(workspace_root, "cloud-run-sandbox", "deploy_sandbox_job.sh")
    service_script = os.path.join(workspace_root, "cloud-run-sandbox", "deploy_sandbox_service.sh")

    with open(job_script, "r", encoding="utf-8") as f:
        job_content = f.read()
    assert '--source="$SCRIPT_DIR"' in job_content
    assert "--set-build-env-vars" not in job_content

    with open(service_script, "r", encoding="utf-8") as f:
        service_content = f.read()
    assert '--source="$SCRIPT_DIR"' in service_content
    assert "--set-build-env-vars" not in service_content


def test_procfile_and_wsgi_app():
    """Verifies Procfile instructs Buildpacks to run python main.py and WSGI app callable exists."""
    procfile_path = os.path.join(workspace_root, "cloud-run-sandbox", "Procfile")
    assert os.path.exists(procfile_path), "cloud-run-sandbox/Procfile missing"
    with open(procfile_path, "r", encoding="utf-8") as f:
        proc_content = f.read().strip()
    assert "web: python main.py" in proc_content

    main_mod = importlib.import_module("cloud-run-sandbox.main")
    assert hasattr(main_mod, "app"), "main.py missing WSGI app callable"

    # Verify WSGI app response
    def dummy_start_response(status, headers):
        assert "200" in status

    resp = main_mod.app({}, dummy_start_response)
    assert len(resp) > 0
    data = json.loads(resp[0].decode("utf-8"))
    assert data["status"] == "ok"


def test_main_process_mode_routing(monkeypatch):
    """Verifies that main.py does not launch HTTP server when PORT is set in Job environment."""
    main_mod = importlib.import_module("cloud-run-sandbox.main")

    # Simulate Cloud Run Job environment (PORT is present, CLOUD_RUN_JOB is present, K_SERVICE is absent)
    monkeypatch.setenv("PORT", "8080")
    monkeypatch.setenv("CLOUD_RUN_JOB", "adk-sandbox-job")
    monkeypatch.delenv("K_SERVICE", raising=False)

    server_called = False
    experiments_called = False

    def mock_run_server(port):
        nonlocal server_called
        server_called = True

    def mock_run_experiments():
        nonlocal experiments_called
        experiments_called = True

    monkeypatch.setattr(main_mod, "run_server", mock_run_server)
    monkeypatch.setattr(main_mod, "run_experiments_main", mock_run_experiments)

    main_mod.main()
    assert experiments_called is True
    assert server_called is False

    # Simulate Cloud Run Service environment (K_SERVICE is present)
    monkeypatch.delenv("CLOUD_RUN_JOB", raising=False)
    monkeypatch.setenv("K_SERVICE", "adk-sandbox-service")
    server_called = False
    experiments_called = False

    main_mod.main()
    assert server_called is True
    assert experiments_called is False







