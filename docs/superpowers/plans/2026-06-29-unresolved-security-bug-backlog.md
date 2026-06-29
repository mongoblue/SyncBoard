# Unresolved Security and Bug Backlog

> Created: 2026-06-29
>
> Purpose: Track remaining issues from the latest security/bug audit and guide small, verified repair batches. Each implementation batch should use TDD where applicable, stage only explicit files, and commit separately.

## P0: Security / Permission Issues

### P0-A: Add global DRF default authentication requirement

- **Status:** Unfixed
- **Main files:**
  - `backend/backend/settings.py`
  - auth/public API views that must remain `AllowAny`
  - likely tests in `backend/tests/test_auth.py`, `backend/tests/test_permissions.py`, `backend/tests/test_project_isolation_regressions.py`
- **Risk:** DRF views without explicit `permission_classes` remain public by default.
- **Recommended batch:** Medium. Add global `DEFAULT_PERMISSION_CLASSES = ['rest_framework.permissions.IsAuthenticated']`, then explicitly mark login/register/public endpoints as `AllowAny`.
- **Verification:** Run auth, permissions, and project-isolation tests. Local pytest may be blocked by MySQL availability.

### P0-B: Validate Bug assignment target project access

- **Status:** Unfixed
- **Main files:**
  - `backend/bug_tracker/views.py`
  - `backend/tests/test_bug_tracker.py`
- **Risk:** `BugViewSet.assign` can assign a bug to any existing user, including users outside the bug project.
- **Recommended batch:** Smallest P0; fix first.
- **Expected rule:** Assignee must be able to access the bug project, meaning project owner or project member.
- **Verification:** `python -m pytest tests/test_bug_tracker.py::TestBugAssign -q`.

### P0-C: Project-scope QA WebSocket dashboard and recorder

- **Status:** Partially fixed
- **Main files:**
  - `backend/qa_center/consumers.py`
  - `backend/qa_center/routing.py`
  - `backend/tests/test_qa_websocket_security.py`
  - `frontend/src/composables/useRecorderSocket.ts`
  - `frontend/src/views/qa/components/RecorderPanel.vue`
  - `frontend/src/views/qa/UiCaseDetail.vue`
- **Risk:** Logged-in users can still join global QA dashboard groups; recorder socket can start browser recording without project-level authorization.
- **Recommended batch:** Larger backend + frontend compatibility change. Require project-scoped routes or project ID handshake before side effects.
- **Verification:** WebSocket security tests plus frontend typecheck/tests.

## P1: Functional Bugs / Integration Risks

### P1-A: ChatConsumer blocks the async event loop with sync Redis calls

- **Status:** Unfixed
- **Main files:**
  - `backend/room/consumers_chat.py`
- **Risk:** `xrange`, `xadd`, and related synchronous Redis calls run inside `AsyncWebsocketConsumer` methods and can block all WebSocket work under load.
- **Recommended batch:** Move Redis operations to async Redis client or isolate sync calls in thread executor.

### P1-B: Global notification consumer can duplicate DB writes

- **Status:** Unfixed
- **Main files:**
  - `backend/room/consumers_global.py`
  - `backend/qa_center/views_devops.py`
  - `backend/qa_center/bug_utils.py`
- **Risk:** Notification rows can be created both by business code and by each connected global consumer, causing duplicates.
- **Recommended batch:** Make business entry points create notification rows once; consumers should only push events, or add idempotency keys.

### P1-C: Frontend WebSocket singleton does not support multiple URLs/channels

- **Status:** Partially fixed / still risky
- **Main files:**
  - `frontend/src/stores/composables/useWebSocket.ts`
- **Risk:** One module-level socket and listener set can mix unrelated business channels, reuse an old URL, and leak listeners/reconnects.
- **Recommended batch:** Manage sockets by URL or channel key and return unsubscribe/close semantics per channel.

### P1-D: Chat.vue hardcodes WebSocket host and port

- **Status:** Unfixed
- **Main files:**
  - `frontend/src/views/Chat.vue`
  - `frontend/src/composables/wsHost.ts`
- **Risk:** Breaks reverse proxy, HTTPS, and non-`:8000` deployments.
- **Recommended batch:** Replace manual host construction with `buildWsUrl()`.

### P1-E: Test run detail lacks a clear `run_finished` event

- **Status:** Partially fixed
- **Main files:**
  - `backend/qa_center/views_api_test.py`
  - `backend/qa_center/consumers.py`
  - `frontend/src/views/qa/TestRunDetail.vue`
- **Risk:** Frontend can miss final run state and keep showing running until refresh.
- **Recommended batch:** Emit a final `run_finished` event with run ID, status, totals, and duration.

## P2: Deployment / Stability / Maintainability Risks

### P2-A: Unsafe `SECRET_KEY` fallback

- **Status:** Unfixed
- **Main files:**
  - `backend/backend/settings.py`
- **Risk:** Production can boot with a fixed weak key if `DJANGO_SECRET_KEY` is missing.
- **Recommended batch:** Fail closed in production; allow explicit dev-only fallback.

### P2-B: DRF BasicAuthentication remains enabled

- **Status:** Unfixed
- **Main files:**
  - `backend/backend/settings.py`
- **Risk:** Basic auth may be undesirable in production and broadens credential exposure risk.
- **Recommended batch:** Keep only session/token authentication in production, or gate BasicAuthentication by environment.

### P2-C: Django serves media unconditionally

- **Status:** Unfixed
- **Main files:**
  - `backend/backend/urls.py`
- **Risk:** Production may serve uploaded media through Django without intended web-server/storage controls.
- **Recommended batch:** Only add `static(..., document_root=settings.MEDIA_ROOT)` or `serve` route when `settings.DEBUG` is true.

### P2-D: Production deploy checks still warn

- **Status:** Unfixed
- **Main files:**
  - `backend/backend/settings.py`
- **Risk:** Missing HSTS, secure cookies, SSL redirect, strong secret enforcement, and strict production settings.
- **Recommended batch:** Split or gate dev/prod settings and run `manage.py check --deploy`.

### P2-E: Legacy `room/views.py` remains alongside modular views

- **Status:** Partially resolved / cleanup pending
- **Main files:**
  - `backend/room/urls.py`
  - `backend/room/views.py`
  - `backend/room/views/`
- **Risk:** Maintenance confusion and future fixes may target an unused legacy file.
- **Recommended batch:** Confirm imports, then delete, rename, or mark legacy code clearly if safe.

### P2-F: TestRun cancellation does not stop already submitted work

- **Status:** Unfixed
- **Main files:**
  - `backend/qa_center/views_test_run.py`
  - `backend/qa_center/views_api_test.py`
- **Risk:** UI shows cancelled while background work continues and consumes resources.
- **Recommended batch:** Add cooperative cancellation checks before scheduling each case and inside long-running execution paths.

### P2-G: Run plan parallel execution can share one `requests.Session`

- **Status:** Unfixed
- **Main files:**
  - `backend/qa_center/run_plan_executor.py`
- **Risk:** Cookie/header state can leak across parallel cases; `requests.Session` is not safe for shared concurrent mutation.
- **Recommended batch:** Use per-worker/per-case sessions in parallel mode.

### P2-H: Locust runner process and report risks

- **Status:** Partially fixed / still risky
- **Main files:**
  - `backend/qa_center/locust_runner.py`
  - `backend/qa_center/tasks.py`
- **Risk:** Undrained subprocess pipes can block, percentile calculation is custom, and temp files may not be cleaned on normal completion.
- **Recommended batch:** Drain or redirect output, use standard percentile logic, and cleanup temp files on all terminal paths.

## Suggested Repair Order

1. P0-B: Bug assign project-member validation.
2. P0-A: Global DRF default permission with explicit public endpoint exceptions.
3. P0-C: QA WebSocket dashboard/recorder project scoping.
4. P1-D: Chat.vue WebSocket host cleanup.
5. P1-B: Global notification duplicate write prevention.
6. P1-E: Emit `run_finished` event.
7. P1-A/P1-C: WebSocket internals hardening.
8. P2 production/stability items in separate deployment-oriented batches.
