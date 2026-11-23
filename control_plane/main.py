"""
Platform Control Plane (The Air Traffic Control Tower)
======================================================
This Python service is the heart of your Internal Developer Platform (IDP).
It does three main jobs:
1. Reads Golden Path blueprints (templates/*/template.yaml) so the portal knows
   what questions to ask developers.
2. Validates the developer's answers and sends a "Go" signal to the GitHub
   Actions conveyor belt via GitHub's REST API.
3. Checks the status of running pipelines and hands back the live website link.
"""

from pathlib import Path
import os
import re
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
import httpx
from pydantic import BaseModel, Field, field_validator
import yaml

# Load environment settings from .env (checks both control_plane/.env and root .env)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

TEMPLATES_DIR = BASE_DIR / "templates"
WORKFLOW_FILENAME = "deploy-s3-golden-path.yml"

app = FastAPI(
    title="TX Platform Control Plane",
    description="Minimal Internal Developer Platform MVP for S3 Golden Path deployments",
    version="0.1.0",
)


# ------------------------------------------------------------------------------
# Data Shape for Incoming Deployment Requests (What Goes In)
# ------------------------------------------------------------------------------
class DeployRequest(BaseModel):
    template_id: str = Field(default="s3-website", description="Golden Path template ID")
    repo_url: str = Field(..., description="GitHub repository URL holding the website code")
    app_name: str = Field(..., description="Unique lowercase name for the S3 bucket")
    aws_region: str = Field(default="us-east-1", description="AWS region for hosting")
    build_output_dir: str = Field(default=".", description="Folder containing index.html")

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not (cleaned.startswith("https://") or cleaned.startswith("http://")):
            raise ValueError("repo_url must start with https:// or http://")
        return cleaned

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", cleaned):
            raise ValueError(
                "app_name must be 3-63 characters using only lowercase letters, numbers, and hyphens"
            )
        return cleaned


# ------------------------------------------------------------------------------
# Helper Functions: Reading Templates & Checking GitHub Credentials
# ------------------------------------------------------------------------------
def load_templates() -> dict[str, dict[str, Any]]:
    """Scan templates/*/template.yaml and load each Golden Path blueprint."""
    catalog: dict[str, dict[str, Any]] = {}
    if not TEMPLATES_DIR.exists():
        return catalog

    for template_file in sorted(TEMPLATES_DIR.glob("*/template.yaml")):
        with template_file.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        metadata = data.get("metadata", {})
        template_id = metadata.get("id") or template_file.parent.name
        catalog[template_id] = {
            "id": template_id,
            "metadata": metadata,
            "parameters": data.get("parameters", []),
            "steps": data.get("steps", []),
            "outputs": data.get("outputs", {}),
        }
    return catalog


def normalize_github_repo(raw_repo: str) -> str:
    """Accept 'owner/repo' or a full GitHub repo URL and return 'owner/repo'."""
    cleaned = raw_repo.strip()
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
            break
    cleaned = cleaned.rstrip("/")
    if cleaned.endswith(".git"):
        cleaned = cleaned[:-4]
    return cleaned.strip("/")


def get_github_config() -> tuple[str | None, str | None, str]:
    """Read GitHub API settings from .env / environment variables on each request."""
    load_dotenv(BASE_DIR / ".env", override=True)
    load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    repo_raw = (os.getenv("GITHUB_REPO") or "").strip()
    repo = normalize_github_repo(repo_raw) if repo_raw else ""
    branch = (os.getenv("GITHUB_BRANCH") or "main").strip() or "main"

    if not token or token == "ghp_your_token_here":
        token = None
    if not repo or repo in ("your-username/tx-platform", "devzeuz/your-repo-name"):
        repo = None
    return token, repo, branch


# ------------------------------------------------------------------------------
# Station 1: Template Discovery Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/templates")
def list_templates() -> dict[str, Any]:
    """Return every Golden Path template available on the platform."""
    templates = load_templates()
    return {"templates": list(templates.values())}


@app.get("/api/templates/{template_id}")
def get_template(template_id: str) -> dict[str, Any]:
    """Return one specific Golden Path template (including form questions & steps)."""
    templates = load_templates()
    if template_id not in templates:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return templates[template_id]


# ------------------------------------------------------------------------------
# Station 2: Validation & Deployment Trigger (Pressing "Go" on the Conveyor Belt)
# ------------------------------------------------------------------------------
@app.post("/api/deploy")
async def trigger_deploy(request: DeployRequest) -> dict[str, Any]:
    """Validate inputs and dispatch the GitHub Actions workflow (or dry-run locally)."""
    templates = load_templates()
    if request.template_id not in templates:
        raise HTTPException(status_code=404, detail=f"Template '{request.template_id}' not found")

    template = templates[request.template_id]
    expected_live_url = f"http://{request.app_name}.s3-website-{request.aws_region}.amazonaws.com"

    dispatch_inputs = {
        "repo_url": request.repo_url,
        "app_name": request.app_name,
        "aws_region": request.aws_region,
        "build_output_dir": request.build_output_dir,
    }

    token, repo, branch = get_github_config()

    # Local Dry-Run Mode: lets you test the entire platform flow before adding GitHub secrets
    if not token or not repo:
        return {
            "mode": "dry_run",
            "message": (
                "GITHUB_TOKEN or GITHUB_REPO is not configured yet. "
                "Showing the exact payload and execution plan that would be sent to GitHub."
            ),
            "template_id": request.template_id,
            "live_url": expected_live_url,
            "github_dispatch_preview": {
                "endpoint": f"https://api.github.com/repos/<owner>/<repo>/actions/workflows/{WORKFLOW_FILENAME}/dispatches",
                "payload": {"ref": branch, "inputs": dispatch_inputs},
            },
            "execution_plan": template.get("steps", []),
        }

    # Live Mode: call GitHub's REST API to start deploy-s3-golden-path.yml
    dispatch_url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILENAME}/dispatches"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    payload = {"ref": branch, "inputs": dispatch_inputs}

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(dispatch_url, headers=headers, json=payload)

    if response.status_code not in (200, 201, 204):
        raise HTTPException(
            status_code=502,
            detail=f"GitHub API rejected dispatch ({response.status_code}): {response.text}",
        )

    return {
        "mode": "live",
        "message": "Golden Path pipeline triggered on GitHub Actions!",
        "dispatch_status": response.status_code,
        "workflow_runs_url": f"https://github.com/{repo}/actions/workflows/{WORKFLOW_FILENAME}",
        "live_url": expected_live_url,
        "inputs": dispatch_inputs,
    }


# ------------------------------------------------------------------------------
# Station 3: Deployment Status Tracker
# ------------------------------------------------------------------------------
@app.get("/api/status")
async def get_deployment_status() -> dict[str, Any]:
    """Check the latest runs of the S3 Golden Path workflow on GitHub."""
    token, repo, _ = get_github_config()

    if not token or not repo:
        return {
            "mode": "dry_run",
            "message": "Set GITHUB_TOKEN and GITHUB_REPO in .env to track live GitHub Actions runs.",
            "runs": [],
        }

    runs_url = (
        f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILENAME}/runs?per_page=5"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(runs_url, headers=headers)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch workflow runs ({response.status_code}): {response.text}",
        )

    data = response.json()
    runs = [
        {
            "id": run.get("id"),
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "html_url": run.get("html_url"),
            "created_at": run.get("created_at"),
        }
        for run in data.get("workflow_runs", [])
    ]
    return {"mode": "live", "runs": runs}


# ------------------------------------------------------------------------------
# Station 4: Built-In Developer Portal UI (What the Developer Sees)
# ------------------------------------------------------------------------------
PORTAL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>TX Platform — Developer Portal</title>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --success: #22c55e;
      --warn: #f59e0b;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 2rem 1rem;
    }
    .container { max-width: 720px; margin: 0 auto; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 1.25rem;
    }
    h1 { margin: 0 0 0.25rem; font-size: 1.5rem; }
    h2 { margin: 0 0 0.75rem; font-size: 1.15rem; }
    .subtitle { color: var(--muted); margin: 0 0 1.25rem; font-size: 0.95rem; }
    .field { margin-bottom: 1rem; }
    label { display: block; font-weight: 600; margin-bottom: 0.25rem; font-size: 0.9rem; }
    .hint { color: var(--muted); font-size: 0.8rem; margin-bottom: 0.35rem; }
    input {
      width: 100%;
      padding: 0.6rem 0.75rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: #0f172a;
      color: var(--text);
      font-size: 0.95rem;
    }
    input:focus { outline: 2px solid var(--accent); border-color: transparent; }
    button {
      background: var(--accent);
      color: #0f172a;
      border: none;
      border-radius: 8px;
      padding: 0.7rem 1.25rem;
      font-weight: 700;
      font-size: 0.95rem;
      cursor: pointer;
    }
    button:hover { background: var(--accent-hover); }
    button:disabled { opacity: 0.6; cursor: not-allowed; }
    .badge {
      display: inline-block;
      padding: 0.2rem 0.6rem;
      border-radius: 999px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      margin-bottom: 0.75rem;
    }
    .badge-dry { background: rgba(245, 158, 11, 0.2); color: var(--warn); }
    .badge-live { background: rgba(34, 197, 94, 0.2); color: var(--success); }
    .steps { list-style: none; padding: 0; margin: 0.75rem 0 0; }
    .steps li {
      padding: 0.5rem 0.75rem;
      border-left: 3px solid var(--accent);
      background: rgba(15, 23, 42, 0.5);
      margin-bottom: 0.5rem;
      border-radius: 0 6px 6px 0;
      font-size: 0.9rem;
    }
    pre {
      background: #0b1120;
      padding: 0.85rem;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 0.82rem;
      border: 1px solid var(--border);
    }
    a { color: var(--accent); }
    .hidden { display: none; }
    .error { color: #f87171; font-size: 0.9rem; margin-top: 0.75rem; }
  </style>
</head>
<body>
  <div class="container">
    <div class="card">
      <h1 id="template-title">Loading Golden Path...</h1>
      <p class="subtitle" id="template-desc"></p>
      <form id="deploy-form">
        <div id="form-fields"></div>
        <button type="submit" id="submit-btn">Deploy via Golden Path</button>
        <div id="form-error" class="error hidden"></div>
      </form>
    </div>

    <div id="result-card" class="card hidden">
      <span id="mode-badge" class="badge"></span>
      <h2>Deployment Response</h2>
      <p id="result-message"></p>
      <p><strong>Live Website Link:</strong> <a id="live-url" href="#" target="_blank" rel="noopener noreferrer"></a></p>
      <p id="workflow-link-row" class="hidden">
        <strong>GitHub Actions Run:</strong> <a id="workflow-url" href="#" target="_blank" rel="noopener noreferrer">Open Pipeline Runs</a>
      </p>
      <h3>Conveyor Belt Steps (from template.yaml)</h3>
      <ul id="steps-list" class="steps"></ul>
      <details>
        <summary style="cursor:pointer; color: var(--muted); margin-top: 0.75rem;">Raw Control Plane Response</summary>
        <pre id="raw-json"></pre>
      </details>
    </div>
  </div>

  <script>
    const formFields = document.getElementById("form-fields");
    const deployForm = document.getElementById("deploy-form");
    const submitBtn = document.getElementById("submit-btn");
    const formError = document.getElementById("form-error");
    const resultCard = document.getElementById("result-card");
    let loadedTemplate = null;

    async function loadTemplate() {
      const res = await fetch("/api/templates/s3-website");
      const tpl = await res.json();
      loadedTemplate = tpl;

      document.getElementById("template-title").textContent = tpl.metadata.name || "S3 Golden Path";
      document.getElementById("template-desc").textContent = tpl.metadata.description || "";

      formFields.textContent = "";
      for (const param of tpl.parameters || []) {
        const wrapper = document.createElement("div");
        wrapper.className = "field";

        const label = document.createElement("label");
        label.setAttribute("for", param.id);
        label.textContent = param.title + (param.required ? " *" : "");

        const hint = document.createElement("div");
        hint.className = "hint";
        hint.textContent = param.description || "";

        const input = document.createElement("input");
        input.id = param.id;
        input.name = param.id;
        input.type = "text";
        input.required = Boolean(param.required);
        if (param.default !== undefined) input.value = param.default;

        wrapper.appendChild(label);
        wrapper.appendChild(hint);
        wrapper.appendChild(input);
        formFields.appendChild(wrapper);
      }
    }

    deployForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      formError.classList.add("hidden");
      submitBtn.disabled = true;
      submitBtn.textContent = "Dispatching...";

      const payload = { template_id: "s3-website" };
      for (const param of (loadedTemplate && loadedTemplate.parameters) || []) {
        payload[param.id] = document.getElementById(param.id).value;
      }

      try {
        const res = await fetch("/api/deploy", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
        }

        const badge = document.getElementById("mode-badge");
        badge.textContent = data.mode === "live" ? "Live Dispatch" : "Dry-Run Preview";
        badge.className = "badge " + (data.mode === "live" ? "badge-live" : "badge-dry");

        document.getElementById("result-message").textContent = data.message;

        const liveLink = document.getElementById("live-url");
        liveLink.textContent = data.live_url;
        liveLink.href = data.live_url;

        const wfRow = document.getElementById("workflow-link-row");
        if (data.workflow_runs_url) {
          document.getElementById("workflow-url").href = data.workflow_runs_url;
          wfRow.classList.remove("hidden");
        } else {
          wfRow.classList.add("hidden");
        }

        const stepsList = document.getElementById("steps-list");
        stepsList.textContent = "";
        for (const step of (loadedTemplate && loadedTemplate.steps) || []) {
          const li = document.createElement("li");
          li.textContent = `${step.name} (${step.action}): ${step.description}`;
          stepsList.appendChild(li);
        }

        document.getElementById("raw-json").textContent = JSON.stringify(data, null, 2);
        resultCard.classList.remove("hidden");
      } catch (err) {
        formError.textContent = "Error: " + err.message;
        formError.classList.remove("hidden");
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Deploy via Golden Path";
      }
    });

    loadTemplate();
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def developer_portal() -> HTMLResponse:
    """Serve the built-in Developer Portal UI."""
    return HTMLResponse(content=PORTAL_HTML)

