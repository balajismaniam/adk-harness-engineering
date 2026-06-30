# Harness Engineering & Multi-Agent Topologies using Google ADK 2.0

This repository contains a structured implementation of multi-agent application architectures using the **Google Agent Development Kit (ADK) 2.0**.

Rather than focusing on raw prompt engineering, this project showcases **Harness Engineering**—the design of runtime state managers, isolated execution sandboxes, programmatic telemetry, and orchestration topologies required to build reliable multi-agent systems.

---

## Project Structure

```
├── targets/
│   ├── ACCTCALC.cbl             # Case Study 2 COBOL packed-decimal file with constraints
│   ├── legacy_analytics.py      # Case Study 1 legacy Python 2.7 file with iterator/division traps
│   ├── db_helper.py             # Case Study 4 legacy database connection module
│   ├── user_dao.py              # Case Study 4 legacy user database access operations
│   ├── admin_service.py         # Case Study 4 legacy database maintenance service
│   └── vulnerable_query.py      # Case Study 5 vulnerable SQL database execution module
├── tests/
│   ├── test_harness.py          # Pytest suite validating Case Study 1 migration
│   ├── test_db_migration.py     # Pytest suite validating Case Study 4 propagation
│   └── test_sqli_defense.py     # Pytest suite validating Case Study 5 SQLi defense
├── workflows/
│   ├── __init__.py              # Python package initializer
│   ├── workflows.py             # Unified workflow blueprint defining all 6 case studies
│   └── telemetry_models.py      # Pydantic schema for high-precision telemetry metrics
├── run_experiments.py           # Consolidated orchestration runner for all 6 case studies
├── .env.example                 # Environment configuration template file
├── Dockerfile                   # Deployment container blueprint
└── README.md                    # Project documentation (this file)
```

---

## 1. Foundations of Harness Engineering & Orchestration

In production multi-agent systems, language models serve as stateless intelligence layers. The reliability, security, and execution safety of the system depend entirely on the surrounding **Harness**.

The Harness layer is responsible for:
* **State & Namespace Management**: Maintaining session histories, step counters, and routing flags across execution graph nodes without context contamination.
* **Execution Isolation (Sandboxing)**: Protecting host system memory and environments by executing untrusted model-generated code in isolated forks.
* **Orchestrator Topologies**: Controlling execution workflows using deterministic graph pathways, dynamic branching, and collaborative agent debates.
* **Programmatic Telemetry**: Tracking raw resource consumption (absolute input/output token counts, execution latencies) at each graph tick.

---

## 2. Harness Architectures & Topologies (Case Studies)

The repository implements six case studies, each demonstrating a distinct harness orchestration pattern built using ADK 2.0's workflow engine:

### Case Study 1: Cyclic Verification Harness (Dynamic Loop)
* **Goal**: Python 2.7 to 3.x migration.
* **Topological Pattern**: Native cyclic routing back-edges.
* **Mechanism**: The harness routes legacy code to a `RefactorAgent`, captures compiler or pytest failures via subprocess errors, and loops back to the agent with console traceback logs until the test suite passes or a max-iteration guard (5) is triggered.

### Case Study 2: Parallel Parsing & Synthesis Harness (Fan-Out/Fan-In Graph)
* **Goal**: COBOL to Python modernization.
* **Topological Pattern**: Concurrently executing graph nodes.
* **Mechanism**: The harness isolates parsing concerns. A `StructureParser` node extracts storage division layouts while a `LogicExtractor` extracts procedure statements in parallel. A final `Synthesis` node joins the parallel paths to produce a unified, Pydantic-validated Python module.

### Case Study 3: Collaborative Debate Consensus Board (Multi-Agent Consensus)
* **Goal**: Enterprise migration routing and code review.
* **Topological Pattern**: Peer-to-peer shared session workspaces.
* **Mechanism**: The harness routes incoming payloads using a classification gateway, then feeds the modernized output into a flat-context collaborative debate between a `SecurityAuditor` and a `PerformanceEngineer`. The harness demands explicit sign-off from both peer roles before completion.

### Case Study 4: Multi-File Dependency Propagation Harness (Dependency Refactoring)
* **Goal**: Multi-file refactoring propagation.
* **Topological Pattern**: Dependency graph fan-out/fan-in.
* **Mechanism**: Once a base-class interface is refactored, the harness concurrently updates all downstream importing files in parallel to prevent import-signature drift, merging the execution back to a single verification node.

### Case Study 5: Adversarial Red/Blue Debate (Collaborative Adversarial Loop)
* **Goal**: SQL Injection defense and validation.
* **Topological Pattern**: Adversarial game-theoretic loop.
* **Mechanism**: A blue fixer agent secures a database query while a red exploiter agent dynamically generates bypass payloads. The harness executes the exploits inside a sandboxed database to check for vulnerabilities, exiting only when exploits fail and unit tests pass.

### Case Study 6: Dynamic Semantic Routing Gateway (Intent Classification)
* **Goal**: Dynamic topology routing.
* **Topological Pattern**: Dynamic routing.
* **Mechanism**: A central classification gateway inspects arbitrary input payloads at runtime using few-shot prompts to dynamically direct session state to the appropriate specialized sub-workflow.

---

## 3. Engineering Best Practices & Guardrails

### 3.1 Sandbox Execution Isolation
To prevent code execution vulnerabilities or orchestrator memory corruption:
* All test execution checking invokes pytest binaries inside clean shell forks using `subprocess.run`.
* Target execution outputs are isolated within the container environment and do not run inside the parent process memory.

### 3.2 State Namespacing & KeyError Prevention
In dynamic workflows fanning out session states to subgraphs, ADK 2.0 does not pre-populate all context schema fields with default values on session start. Accessing uninitialized properties can trigger Python `KeyError` exceptions. 
* **Rule**: Always initialize context counter variables safely:
  ```python
  ctx.state["iteration_count"] = ctx.state.get("iteration_count", 0) + 1
  ```

### 3.3 Concurrency & Session Sandboxing
Running parallel test runs or concurrent multi-agent executions modifying files in static project directories causes disk-write race conditions.
* **Rule**: The harness writes target code modifications dynamically into a session-isolated directory (e.g., `/tmp/adk_<session_id>`).
* Pytest suites dynamically insert this session folder at index 0 of `sys.path` to ensure import isolation:
  ```python
  targets_dir = os.environ.get("TARGETS_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), "../targets")))
  sys.path.insert(0, targets_dir)
  ```

---

## 4. Execution, Deployment & Generated Outputs

### 4.1 Configure Environment Variables
Copy `.env.example` to `.env` and fill in your GCP project and resource details:
```bash
cp .env.example .env
```
Ensure you configure:
* `GOOGLE_CLOUD_PROJECT`: Your Google Cloud Project ID.
* `CLOUD_RUN_REGION`: The region for your Cloud Run Jobs (e.g., `us-west1`).
* `SA_NAME`: The Service Account name (e.g., `adk-runner-sa`).
* `GCS_BUCKET_NAME`: The Google Cloud Storage bucket name to persist analysis outputs.

Load the environment variables into your current shell:
```bash
source .env
```

### 4.2 Production Deployment: Google Cloud Run (Jobs)
For production-grade batch runs, **Cloud Run Jobs** provide an isolated, stateless environment optimized for run-to-completion Jobs.

> [!NOTE]
> **Task Timeout**: The deployment script configures the job's task timeout to 30 minutes (`--task-timeout=30m`) to accommodate long-running workflows like Case Study 6 (Dynamic Semantic Routing Gateway).

#### A. Automated Build and Deploy
You can deploy the required service account, Artifact Registry, build the docker container, and register the Cloud Run Job using the helper script:
```bash
./deploy_job.sh
```

#### B. Execute the Job
The analysis runner maps individual Cloud Run tasks to specific case studies using modulo arithmetic (`task_index % 6 + 1`). 

* **Run all Case Studies in parallel (Recommended)**: Start a job execution specifying `--tasks 6` to run all 6 case studies concurrently as isolated parallel tasks:
  ```bash
  gcloud run jobs execute adk-analysis-job \
      --project=$GOOGLE_CLOUD_PROJECT \
      --region=$CLOUD_RUN_REGION \
      --tasks 6
  ```
* **Run a specific Case Study**: Pass the case study number as an argument using the `--args` flag:
  ```bash
  gcloud run jobs execute adk-analysis-job \
      --project=$GOOGLE_CLOUD_PROJECT \
      --region=$CLOUD_RUN_REGION \
      --args="--case-study=4"
  ```

#### C. Teardown & Cleanup
To avoid incurring Google Cloud costs, run the interactive cleanup helper script to safely remove deployed resources:
```bash
./cleanup_resources.sh
```

> [!IMPORTANT]
> **GEAP Location Routing**: Region endpoints for the Gemini Enterprise Agent Platform (GEAP) do not support `gemini-3.5-flash` calls. The docker image must be hosted locally (e.g., `us-west1`), but ensure `GOOGLE_CLOUD_LOCATION="global"` is configured for GEAP API calls.

### 4.3 Local Prototyping
For local debugging and rapid execution:
1. Create and activate a Python 3.11 virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
2. Configure your environment credentials by loading `.env`:
   ```bash
   source .env
   ```
3. Run the orchestration runner:
   ```bash
   # Run all case studies sequentially
   python run_experiments.py
   
   # Run a specific Case Study (e.g., Case Study 1)
   python run_experiments.py --case-study 1
   ```

### 4.4 Generated Analysis Outputs
Upon execution, the harness writes outputs containing:
* **`experiments_results_*.json`**: High-precision telemetry metrics tracking total execution time, total input tokens, total output tokens, and functional pass/fail status.
* **Transcripts**: Full programmatic execution logs including node transition history and agent prompt/response histories saved to `results/transcripts/`.
* **Output source files**: The finalized modernized code files saved to `output/` (locally) or persistent Google Cloud Storage buckets (when running on Cloud Run Jobs).

## License
This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file for the full license text.

## NOTE
This is not an officially supported Google product.