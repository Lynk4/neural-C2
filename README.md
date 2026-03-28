# neural-C2
---

**neural-C2** is a serverless Command & Control (C2) architecture that uses **GitHub Issues** as a dead-drop relay. It allows you to manage remote machines directly from the **ai Chat** interface using Natural Language (NLP).

---

## 🏗️ How it Works

The system uses a unique "dead-drop" mechanism where no direct socket connection exists between the controller and the agent.

```mermaid
graph LR
    User((User)) -- "NLP Command" --> Claude[Claude Desktop]
    AI-interface -- "MCP Server" --> MCP[ai-c2.py]
    MCP -- "Create Issue" --> GitHub{GitHub API}
    GitHub -- "Poll Issues" --> Agent[Remote Agent]
    Agent -- "Post Comment" --> GitHub
    GitHub -- "Read Comment" --> MCP
    MCP -- "Format Result" --> Claude
    Claude -- "Natural Language" --> User
```

---

1.  **Command**: You tell through ai chat : *"List files on agent-123"*
2.  **Relay**: MCP translates this into a GitHub Issue in your private repository.
3.  **Execution**: The remote agent polls GitHub, sees the task, runs the command, and posts the output as a comment.
4.  **Reporting**: ai reads the comment and explains the result to you.

---

## ✨ Features

-   **Zero Infrastructure**: No port forwarding, no VPS, no complex setup. Just a GitHub account.
-   **Natural Language Control**: Control your infrastructure by chatting. "Is the web server running?" or "Check free disk space."
-   **Multi-Agent Support**: Unique IDs for every machine, with broadcast capability.
-   **Stealthy Relay**: Traffic looks like standard HTTPS calls to `api.github.com`.
-   **Cross-Platform**: Agent runs on Windows (PowerShell) and Linux/macOS (PowerShell Core).

---

## 🛠️ Prerequisites

-   **GitHub Personal Access Token (PAT)**: Requires `repo` permissions.
-   **Python 3.10+** (For the Claude MCP side).
-   **PowerShell 5.1+** (Windows) or **PowerShell Core 7+** (Linux/macOS).
-   **Claude Desktop** installed.

---

## requirements.txt

```
mcp[fastmcp]>=0.4.1
requests>=2.31.0
```

---

## 🚀 Setup Guide

### 1. GitHub Configuration
1.  Create a **Private Repository** (e.g., `my-c2-relay`).
2.  Generate a GitHub PAT (Personal Access Token) with full `repo` scopes.
    -   *Settings > Developer Settings > Personal Access Tokens > Tokens (classic)*.

### 2. MCP Controller Setup 

Add the server:
```json
{
  "mcpServers": {
    "ai-c2": {
      "command": "env/bin/python3",
      "args": ["/absolute/path/to/ai-c2.py"],
      "env": {
        "GITHUB_TOKEN": "your_token_here",
        "GITHUB_REPO": "your_username/your_repo_name"
      }
    }
  }
}
```
---

### 3. Agent Deployment
1.  Copy `client.ps1` to the target machine.
2.  Configure your **Token** and **Repo** at the top of the file.
3.  Run the agent:

---

## 📡 NLP Commands

| Command | Description |
|---|---|
| *"Who is online?"* | Lists all active agents. |
| *"Check IP on agent-456"* | Runs a specific command on a target agent. |
| *"Run 'ls' on everyone"* | Broadcasts a command to all agents. |
| *"Remove dead agents"* | Cleans up agents that haven't checked in recently. |

---








