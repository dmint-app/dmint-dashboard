# Dmint Dashboard V1

A simple local human approval dashboard for [Dmint](https://github.com/dmint-app/dmint) using Core's public APIs.

---

> [!WARNING]
> **NO AUTHENTICATION — LOCAL / DEMO USE ONLY**
>
> Dmint Dashboard V1 has **no authentication**, no session management, and no user roles. It binds by default to `127.0.0.1:8080`. Do **not** expose it directly to untrusted networks or bind to `0.0.0.0` without a reverse proxy providing authentication.

---

## 1. Architectural Invariant

**There is EXACTLY ONE database in Dmint:**

```
AI Agent
   │
   ▼
Dmint MCP Gateway
   │
   ▼
Dmint Core (Policy Engine & Authorization)
   │
   ▼
Core SQLite Database (approvals.sqlite3)
   ▲
   │ Core Public API
   │ (list_pending, list_records, get, approve_pending, reject_pending)
   │
Dmint Dashboard (FastAPI + Bootstrap 5)
   │
   ▼
Human Approver
```

### Critical Rules
- **The dashboard has NO database of its own.**
- The dashboard **never** creates `dashboard.db` or `dashboard.sqlite`.
- The dashboard **never** creates or modifies database tables.
- The dashboard **never** executes SQL queries directly.
- The dashboard **never** duplicates the approval state machine or makes policy decisions.
- Core remains the **sole owner** of SQLite persistence, schema, atomic compare-and-swap state transitions, request binding, and Ed25519 cryptographic signatures.

---

## 2. Frontend Technology

- **Bootstrap 5.3** loaded via CDN in `base.html`
- **Jinja2** server-side templates
- **Vanilla HTML/CSS/JavaScript** — no custom frontend framework
- **No Node.js, no npm, no frontend build steps**
- Responsive layout supporting desktop, tablet, and mobile browsers

---

## 3. Core Public APIs Used

The dashboard communicates with Core exclusively via public APIs:

| Core API Method | Dashboard Usage |
|---|---|
| `SQLiteApprovalStore.list_pending(*, limit=100)` | Queries unexpired `PENDING` records for `/` (Home) |
| `SQLiteApprovalStore.list_records(*, states=None, limit=200)` | Queries records with optional state filtering for `/audit` |
| `SQLiteApprovalStore.get(approval_id)` | Fetches single record details for `/approvals/{approval_id}` |
| `SQLiteApprovalStore.approve_pending(approval_id, authority=..., approved_by=...)` | Atomically transitions `PENDING → APPROVED` with signed assertion |
| `SQLiteApprovalStore.reject_pending(approval_id, authority=..., rejected_by=..., reason=...)` | Atomically transitions `PENDING → REJECTED` with reason |
| `LocalApprovalAuthority(issuer_id=..., audience=...)` | Signs human approval assertions using Core's Ed25519 signer |
| `ApprovalState` | Enum for filtering and badges (`PENDING`, `APPROVED`, `REJECTED`, `CONSUMED`, `EXPIRED`, `CANCELLED`, `POLICY_INVALIDATED`) |

---

## 4. Pages & Routes

| Route | Method | Description |
|---|---|---|
| `/` | `GET` | **Home**: Stat cards (Pending, Approved, Rejected) and responsive table of pending approvals |
| `/api/dashboard` | `GET` | **Dashboard JSON**: Polling endpoint returning live counts and pending approval records |
| `/approvals/{id}` | `GET` | **Details**: Full breakdown of the request (`WHO`, `WHAT`, `WHERE`, formatted arguments, policy provenance, timing) with Approve and Reject modals |
| `/approvals/{id}/approve` | `POST` | **Approve**: Calls Core `approve_pending()`, redirects to detail page with flash alert |
| `/approvals/{id}/reject` | `POST` | **Reject**: Accepts optional reason, calls Core `reject_pending()`, redirects with flash alert |
| `/audit` | `GET` | **Audit Log**: Chronological history of all approval records from Core with state filter dropdown |
| `/health` | `GET` | **Health Probe**: Returns `{"status": "ok", "core": "ok"}` JSON |

---

## 5. Installation

Requires Python &ge; 3.10.

```bash
# Clone repository
git clone https://github.com/dmint-app/dmint-dashboard.git
cd dmint-dashboard

# Create virtualenv and install
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## 6. Startup

The dashboard connects to an **existing** Core SQLite database:

```bash
# Run via CLI script
dmint-dashboard --db-path /path/to/existing/approvals.sqlite3 --deployment-epoch my-epoch

# Or run via Python module
python -m dmint_dashboard --db-path /path/to/existing/approvals.sqlite3 --deployment-epoch my-epoch
```

When `dmint-cli` is installed, the preferred launcher is:

```bash
dmint dashboard --db-path /path/to/existing/approvals.sqlite3
```

The dashboard is local-only by default, has no authentication in V1, and uses
the existing Core-owned SQLite database. It does not create a separate
dashboard database.

### Environment Variables

Configuration can also be passed via environment variables:

```bash
export DMINT_DB_PATH=/path/to/existing/approvals.sqlite3
export DMINT_DEPLOYMENT_EPOCH=my-epoch
export DMINT_DASHBOARD_HOST=127.0.0.1
export DMINT_DASHBOARD_PORT=8080
export DMINT_APPROVER_ID=security-operator

dmint-dashboard
```

---

## 7. Human Approve / Reject Workflow

### Approve Flow
1. Human reviews request on `/approvals/{approval_id}`:
   - **WHO**: Agent identity
   - **WHAT**: Tool name and action
   - **WHERE**: Resource identifier
   - **WITH WHAT**: Read-only, escaped JSON arguments
   - **UNDER WHICH**: Policy digest and version ID
   - **UNTIL WHEN**: Expiration timestamp
2. Human clicks **Approve** &rarr; confirmation modal opens.
3. Form submits `POST /approvals/{approval_id}/approve`.
4. Dashboard passes only `approval_id` and `approved_by` to Core's `approve_pending()`.
5. Core verifies pending status, non-expiration, integrity checksum, signs assertion, transitions state to `APPROVED`, and commits to SQLite.
6. Dashboard redirects with success flash message.

### Reject Flow
1. Human clicks **Reject** &rarr; modal opens with optional reason text area (max 500 chars).
2. Form submits `POST /approvals/{approval_id}/reject` with `reason`.
3. Dashboard passes only `approval_id`, `rejected_by`, and `reason` to Core's `reject_pending()`.
4. Core verifies pending status, updates state to `REJECTED`, stores the reason, and commits to SQLite.
5. Dashboard redirects with rejection confirmation flash message.

---

## 8. Client-Side Polling

Dashboard data refreshes automatically every 5 seconds using simple client-side short polling:

```
Browser (every 5000ms)
    │ fetch("/api/dashboard")
    ▼
FastAPI Route
    │ list_pending(), count_by_state()
    ▼
Core Public API
    │
    ▼
Core SQLite Database
    │
    ▼
JSON Response ──▶ Browser updates DOM cards & pending table
```

- **Polling Interval**: 5000 ms (`setInterval`).
- **Overlap Prevention**: In-flight requests lock out subsequent polls (`let polling = false; if (polling) return;`) until finished.
- **Visibility Aware**: Polling automatically pauses when the browser tab is hidden/backgrounded (`document.visibilityState`).
- **Resilience**: Network or server hiccups do not crash the page or disrupt the existing UI.
- **No WebSockets, No SSE, No background workers**: Intentionally avoided to keep V1 simple, stateless, and lightweight for demo and developer use.

---

## 9. Intentional V1 Limitations

- **No authentication / sessions**: Designed for local developer and operator use (`127.0.0.1`).
- **Local SQLite only**: Relies on the local filesystem path to the Core SQLite database.
- **Client-side polling**: Periodically polls `/api/dashboard` every 5 seconds (No WebSockets, No SSE, No background workers).
- **Single operator identity**: Defaults to `dashboard-human` (configurable via `DMINT_APPROVER_ID`).
