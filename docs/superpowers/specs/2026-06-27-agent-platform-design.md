# SyncBoard Agent Orchestrator Platform Design

## Goal

Build a platform-level AI Agent capability inside SyncBoard. The Agent should understand user requests, inspect project context, generate an editable plan, and safely perform approved edits across system modules through controlled tools.

The first implementation should not be a free-form autonomous bot. It should be an auditable Agent Orchestrator that follows this lifecycle:

1. User submits a natural-language request.
2. Backend creates an Agent run.
3. Agent reads authorized context.
4. Agent generates a plan.
5. User approves the plan or selected steps.
6. Edit tools run in dry-run mode and show diffs.
7. User confirms the diffs.
8. Tools execute changes.
9. Audit records and execution summaries are stored.

## Current State

SyncBoard currently has project, column, task, user, invitation, project chat, QA, bug tracking, and an existing AI chat feature. The existing `AIChat.vue`, `/api/ai/*` endpoints, `AIConversation`, `AIMessage`, and `room.ai_utils` provide multi-turn chat, RAG-style context building, analysis shortcuts, and direct tool-calling helpers.

The existing AI feature is not yet the target Agent Orchestrator:

- LLM calls and tool definitions are coupled inside `room.ai_utils` and `room.views.ai`.
- Some tools directly mutate database records without plan approval, dry-run, or diff confirmation.
- There are no Agent run, plan, step, tool call, or approval records.
- There is no separate tool registry with risk levels and authorization metadata.
- There is no plan/edit execution loop.
- There are no Agent-specific WebSocket updates.
- There is no auditable approval flow or rollback-ready diff record.

Before Agent editing is enabled, existing authorization boundaries must remain strict so tools cannot bypass project membership or user permissions.

## Recommended Architecture

### 1. Agent Conversation Layer

The frontend should expose an AI assistant panel where users can submit requests such as:

- Summarize overdue project tasks.
- Generate a QA remediation plan.
- Split a project into staged delivery tasks.
- Inspect system modules and propose improvements.

The panel should show:

- User messages.
- Assistant responses.
- Generated plans.
- Step status.
- Approval actions.
- Dry-run diffs.
- Execution summaries.

### 2. Agent Orchestrator Layer

The backend should coordinate every Agent run. It should be responsible for:

- Creating and tracking Agent runs.
- Collecting context through read-only tools.
- Generating plans.
- Creating executable steps.
- Requesting approval before edits.
- Running dry-run and execute phases.
- Emitting WebSocket status updates.
- Persisting audit records.

The Orchestrator should never allow the LLM to directly modify database records. All reads and edits must go through registered tools.

### 3. Module Tool Layer

Each system module should expose explicit tools. A tool definition should include:

- `name`: stable tool identifier, such as `task.create`.
- `description`: what the tool does.
- `input_schema`: accepted parameters.
- `permission`: required application permission.
- `risk_level`: `read`, `low`, `medium`, or `high`.
- `handler`: implementation entry point.
- `dry_run`: returns the expected diff without writing.
- `execute`: performs the approved change.

Initial tools:

#### Project tools

- `project.read`
- `project.update`

#### Column tools

- `column.list`
- `column.create`
- `column.update`
- `column.reorder`

#### Task tools

- `task.list`
- `task.create`
- `task.update`
- `task.move`
- `task.bulk_update`

#### Chat tools

- `chat.history.read`
- `chat.summarize`

#### System analysis tools

- `module.list`
- `module.capability_map`
- `module.plan_changes`

The first release should not expose tools for permission changes, destructive deletes, arbitrary code execution, shell commands, or source-code modification.

### 4. Approval and Permission Layer

Agent actions should be classified by risk:

- `read`: context gathering only.
- `low`: create drafts or plans.
- `medium`: create tasks, update task fields, move cards, update project text.
- `high`: deletion, bulk edits, permission changes, and other sensitive operations.

For the initial release:

- Read tools may run automatically after authorization checks.
- Edit tools require plan approval.
- Edit tools must run dry-run before execution.
- User confirmation is required after diff preview.
- High-risk tools should not be implemented in the first release.

Every tool call must verify the initiating user has access to the target project/module. Agent approval does not replace normal authorization.

### 5. Audit and Recovery Layer

Every Agent run and tool call should preserve enough information to answer:

- Who initiated the request?
- What was the original user request?
- What plan did the Agent generate?
- Which steps did the user approve?
- Which tools were called?
- What input was passed to each tool?
- What changed before and after execution?
- Which operations succeeded, failed, or were skipped?

Full rollback can be added later. The initial implementation must at least avoid silent failures and store before/after diffs for executed edits.

## Core Data Model

Create a new Django app named `agent` to keep orchestration separate from the existing `room` app.

### AgentSession

Represents a long-lived assistant conversation.

Key fields:

- user
- project, nullable if a session is system-wide
- title
- status
- created_at
- updated_at

### AgentMessage

Stores conversation history.

Key fields:

- session
- role: `user`, `assistant`, `system`, `tool`
- content
- metadata
- created_at

### AgentRun

Represents one execution attempt triggered by a user request.

Recommended statuses:

- `queued`
- `planning`
- `waiting_approval`
- `dry_running`
- `waiting_diff_confirmation`
- `running`
- `completed`
- `failed`
- `cancelled`

Key fields:

- session
- user
- project
- original_request
- status
- error_message
- started_at
- completed_at
- created_at
- updated_at

### AgentPlan

Stores the generated plan.

Key fields:

- run
- goal
- scope
- affected_modules
- risk_summary
- plan_json
- status
- created_at
- updated_at

### AgentStep

Represents one planned step.

Key fields:

- plan
- order
- title
- description
- status
- risk_level
- requires_approval
- created_at
- updated_at

### AgentToolCall

Stores each tool invocation.

Key fields:

- run
- step
- tool_name
- input_json
- output_json
- diff_json
- risk_level
- approval_status
- execution_status
- error_message
- created_at
- updated_at

### AgentApproval

Stores approval decisions.

Key fields:

- run
- step, nullable
- tool_call, nullable
- user
- decision: `approved` or `rejected`
- comment
- created_at

## API Design

Initial REST API:

- `POST /api/agent/sessions/`
  - Create or retrieve an assistant session.

- `GET /api/agent/sessions/:id/messages/`
  - Return session history.

- `POST /api/agent/runs/`
  - Start an Agent run from a user request.

- `GET /api/agent/runs/:id/`
  - Return run status, plan, steps, tool calls, and approvals.

- `POST /api/agent/runs/:id/approve/`
  - Approve the full plan or selected steps.

- `POST /api/agent/runs/:id/confirm-diff/`
  - Confirm dry-run diffs and allow execution.

- `POST /api/agent/runs/:id/cancel/`
  - Cancel a queued, planning, approval-waiting, or running Agent run.

- `GET /api/agent/tools/`
  - Return available tools and risk metadata for the current user/project.

Agent status updates should be pushed through Django Channels so the frontend can update run progress in real time.

## Plan/Edit Flow

1. User submits a request in the AI assistant panel.
2. Backend creates `AgentRun` with status `queued`.
3. Orchestrator transitions to `planning`.
4. Read-only tools collect authorized context.
5. Agent creates `AgentPlan` and `AgentStep` records.
6. Run transitions to `waiting_approval`.
7. User approves the whole plan or selected steps.
8. Orchestrator creates `AgentToolCall` records for approved edit steps.
9. Tools run in `dry_run` mode.
10. Run transitions to `waiting_diff_confirmation`.
11. User reviews diffs and confirms execution.
12. Tools execute approved changes.
13. Run transitions to `completed`, `failed`, or `cancelled`.
14. Assistant writes an execution summary message.

## Failure Handling

### Plan generation failure

- Mark `AgentRun` as `failed`.
- Store the error message.
- Show a retry option in the frontend.

### Context read failure

- Mark the affected step or tool call as failed.
- Continue only if the missing context is non-critical.
- Include a warning in the generated plan when context is incomplete.

### Dry-run failure

- Do not allow execution.
- Show the failed tool, input, and validation error.

### Execute failure

- Preserve audit records for successful tool calls.
- Mark remaining steps as skipped if execution cannot continue safely.
- Store the failing tool and error message.

## Development Roadmap

### P0: Security and permission foundation

Goal: make existing modules safe for Agent access.

Tasks:

- Add missing auth checks for task, column, and user APIs.
- Ensure users must be project members to read or edit project data.
- Reject anonymous users from project chat WebSocket connections.
- Add shared authorization helpers for project/module access.
- Add tests for unauthorized REST and WebSocket access.

Deliverable: existing project data can only be accessed through explicit permissions.

### P1: Agent platform skeleton

Goal: implement the Agent run lifecycle without depending on a real LLM.

Tasks:

- Create the `agent` Django app.
- Add Agent models and migrations.
- Add REST APIs for sessions, messages, runs, approval, cancellation, and tools.
- Add WebSocket updates for run status.
- Add a frontend AI assistant panel.
- Use a mock or rule-based planner to generate initial plans.

Deliverable: users can submit Agent requests, view generated plans, and approve or cancel runs.

### P2: Tool registry and first editable modules

Goal: allow approved Agent runs to safely read and edit system modules.

Tasks:

- Implement `ToolRegistry`.
- Add tool schema, permission, risk, dry-run, and execute interfaces.
- Implement initial read tools for project, columns, tasks, chat history, and module map.
- Implement initial edit tools for task creation, task update, task movement, column creation, and project update.
- Add dry-run diff generation.
- Add execution audit records.

Deliverable: approved Agent steps can create and update project planning data through controlled tools.

### P3: Real LLM, RAG, and multi-turn context

Goal: turn the rule-based platform into an intelligent assistant.

Tasks:

- Add an LLM provider abstraction.
- Add model configuration, timeout handling, retries, and error reporting.
- Store and summarize Agent conversation history.
- Add retrieval over project, task, chat, and document context.
- Support follow-up questions and plan refinement.

Deliverable: Agent can understand natural-language requests and generate useful plans from real project context.

### P4: Multi-Agent and long-running work

Goal: evolve the assistant into a full Agent platform.

Tasks:

- Add role-specific Agents such as project manager, QA, planning, and review Agents.
- Support background and long-running Agent runs.
- Add task recovery and better failure isolation.
- Add optional rollback for supported tools.
- Expand tool coverage to more SyncBoard modules.

Deliverable: SyncBoard supports specialized Agents that can plan, execute, review, and report across modules.

## Testing Requirements

### P0 tests

- Anonymous users cannot access protected APIs.
- Non-members cannot read or edit project data.
- Anonymous users cannot connect to protected WebSockets.

### P1 tests

- Sessions can be created and listed only by authorized users.
- Runs move through expected statuses.
- Plans can be generated by the mock planner.
- Approval and cancellation endpoints enforce ownership and project access.

### P2 tests

- Read tools return only authorized data.
- Edit tools cannot execute before approval.
- Dry-run does not write to the database.
- Execute writes expected changes and audit records.
- Failed tool calls preserve errors and do not silently continue.

### Frontend tests

- User can submit an Agent request.
- Generated plan is displayed.
- User can approve or cancel a run.
- Dry-run diffs are displayed before execution.
- Board data refreshes after successful execution.

## Non-Goals for the First Release

- Fully autonomous execution without user approval.
- Destructive delete tools.
- Permission or role modification tools.
- Arbitrary shell command execution.
- Source-code editing through the web Agent.
- Full rollback for every operation.
- Multi-Agent collaboration.

## Implementation Defaults

Use these defaults for the first implementation plan:

- Sessions may be project-scoped or global. A run that edits project data must be project-scoped and must verify project membership.
- Approval is supported at both plan and step level. P1 should implement plan-level approval first; P2 should add step-level approval for editable tool calls.
- Agent WebSocket updates should use a separate agent route namespace, while following the existing Django Channels conventions used by project chat.
- P3 should use a provider abstraction so the concrete LLM provider can be configured without changing the Orchestrator or tools.
