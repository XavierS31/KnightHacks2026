# Three developer coding agents

The repo ships these project-scoped Codex roles:

| Human | Role | Definition | Skill | Starter |
| --- | --- | --- | --- | --- |
| A | `developer_a_integration` | `.codex/agents/developer_a_integration.toml` | `$repofusion-integration` | [A tasks](tasks/developer-a.md) |
| B | `developer_b_personas` | `.codex/agents/developer_b_personas.toml` | `$repofusion-personas` | [B tasks](tasks/developer-b.md) |
| C | `developer_c_evolution` | `.codex/agents/developer_c_evolution.toml` | `$repofusion-evolution` | [C tasks](tasks/developer-c.md) |

These are development assistants. Application agents are defined separately in [runtime contracts](agent-contract.md) and use Hugging Face.

## Configuration and discovery

Current official Codex documentation supports standalone project agents in `.codex/agents/*.toml`, with `name`, `description` and `developer_instructions`. These files omit model, reasoning, provider, sandbox and approval overrides so parent settings are inherited. No Cursor agent format is assumed. [Official subagent documentation](https://learn.chatgpt.com/docs/agent-configuration/subagents)

Repo-local skills are in `.agents/skills`; they provide reusable project workflows and may be explicitly invoked by `$skill-name`. If newly added skills are not visible, restart/reopen the project session. Agent discovery can also require a new session on installations that read roles at startup. [Official skill documentation](https://learn.chatgpt.com/docs/build-skills)

The definitions are configuration, not running processes. A human can start each role from a chat opened against this repository (or its feature worktree). No project/user model settings or remote services are changed by these files.

## Copyable kickoff prompts

Developer A:

> Use the developer_a_integration agent and $repofusion-integration. Read AGENTS.md and docs/tasks/developer-a.md. Inspect the current skeleton and implement the first unfinished bounded milestone across the integration frontend and backend. Keep fixtures explicit, coordinate shared contracts, verify the change, and report evidence and the next gate.

Developer B:

> Use the developer_b_personas agent and $repofusion-personas. Read AGENTS.md and docs/tasks/developer-b.md. Inspect the current skeleton and implement the first unfinished bounded milestone across personas, the world and the Hugging Face adapter. Do not fabricate browser execution. Verify the change and report evidence and the next gate.

Developer C:

> Use the developer_c_evolution agent and $repofusion-evolution. Read AGENTS.md and docs/tasks/developer-c.md. Inspect the current skeleton and implement the first unfinished bounded milestone across feedback/evolution and database infrastructure. Keep fixtures explicit and require human review before v2 promotion. Verify the change and report evidence and the next gate.

If a particular client cannot discover custom roles, load the TOML's `developer_instructions` and matching skill explicitly in the task. Treat that as a manual scoped kickoff, not proof of installed role discovery. Each developer retains human responsibility for review and integration.

