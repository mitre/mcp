# FastMCP "V1 to V3" upgrade: analysis and plan

Assembled 2026-08-30 against branch `fix/cti-pipeline`. Every load-bearing claim
here was verified empirically in this repo or in isolated venvs, not read off a
changelog. Claims that did not survive adversarial review were removed.

---

## 1. The premise needs correcting first

**We are not running the `fastmcp` package, and the CVEs do not reach us.**

### Package identity

`requirements.txt` declares `mcp>=1.9,<2`, the official
`modelcontextprotocol/python-sdk`. Both servers do
`from mcp.server.fastmcp import FastMCP`. That bundled class is what the vendor
retroactively named "FastMCP 1.0". The standalone `fastmcp` package (PrefectHQ,
formerly jlowin) is a **different distribution**.

So "upgrade V1 to V3" does not mean replacing anything. It means **adding a
second package on top of the one we already have**. Verified by installing it:

```
fastmcp 3.4.7  ->  fastmcp-slim[client,server] 3.4.7  ->  mcp>=1.24.0,<2.0
```

We keep 100% of the current `mcp` surface and bolt 27 more distributions on.

### The CVEs

Checked against OSV and the GitHub Advisory Database:

| | `mcp` (what we have) | `fastmcp` (what we would add) |
|---|---|---|
| Advisories, all time | 6 | 8 |
| Affecting the version actually installed (1.29.1 / 3.4.7) | **0** | **0** |
| Reachable on stdio-only, no-auth, no-HTTP | **0** | **0** |
| Highest severity in the set | 7.6 | **10.0** (OpenAPI provider SSRF) |

The live `.calderavenv` already runs **mcp 1.29.1**, released 2026-08-24, which
has zero advisories. Of the six `mcp` advisories, two say in their own text that
stdio servers are unaffected, three more are HTTP/SSE/WebSocket transports we
never instantiate, and the sixth is an opt-in experimental task handler.

On the other side, seven of `fastmcp`'s eight advisories live in the OAuth proxy,
the CLI installer, and the OpenAPI provider. None is in tool dispatch or stdio.
Migrating installs that code without using it.

**One real finding, and it is the floor rather than the ceiling.** `mcp==1.9.0`
satisfies our current constraint and is hit by five of the six. An install from a
stale wheelhouse lands there. Raising the floor is a one-line fix, and it is
independent of the migration.

**Honest summary: migrating takes the exploitable-CVE count from 0 to 0.** It
adds roughly 16 SCA-visible advisory rows in `authlib` and `joserfc`, packages
that `from fastmcp import FastMCP` never imports. Migrate for ergonomics if we
migrate. Do not sell it as security.

---

## 2. Complexity verdict

**The code change is two import lines. The migration is 8 to 13 engineer-days,
and it is gated on a change to CALDERA core that this plugin is not allowed to
make.**

| Bucket | Days | Driver |
|---|---|---|
| Mechanical edits | 0.25 | 2 imports, 2 `show_banner=False`, 2 requirements lines |
| **Core dependency PR (cross-repo)** | **2.0 to 4.0** | `fastmcp>=3` is unsatisfiable against core's pins. Calendar time is not ours to control. |
| Schema-drift remediation | 1.5 | Strict-args soak, 7 discarded `Returns:` blocks, 30 newly visible param descriptions |
| Sync-concurrency remediation | 0.75 | A deterministic `RuntimeError`, not just a perf change |
| Wire-level tests | 1.0 | There are currently **zero**. Nothing calls `list_tools`, `call_tool`, or `stdio_client` |
| GUI / discovery follow-through | 0.5 | Trajectory verification |
| Validation against live CALDERA | 1.0 | Real agents, before/after trajectory diff |
| **Total** | **7 to 9 plugin-side** | **8 to 13 all-in** |

The mechanical work is twenty minutes. Everything else is consequences.

---

## 3. Surface area

| Surface | Count | Notes |
|---|---|---|
| Server files | 2 | `mcp_server.py` (724 LOC, 5 async tools, all `-> dict`), `app/mcp_server.py` (556 LOC, 20 sync tools, **zero return annotations**) |
| Tools | **25** | All use exactly `@mcp.tool(name="...")`. No `description=`, no `annotations=`, no `structured_output=` anywhere |
| Client spawn sites | 2 | `app/workflows/plan_execute.py:248-256`, `app/workflows/author.py:242-250`, byte-identical |
| DSPy binding | 2 lines | `plan_execute.py:273`, `author.py:267` |
| Discovery | 1 | `app/discovery/servers.py`, AST-only, never imports. **Zero migration impact** |
| Tests touching MCP | 9 of 38 | |
| **Tests exercising the wire** | **0** | No schema assertion exists anywhere |
| requirements.txt files to edit | **2** | Ours, and **CALDERA core's** |

### Load-bearing hacks, corrected

- **`_stdout_safe` (`mcp_server.py:48-72`): keep it.** Verified by probe: FastMCP
  3 does *not* guard tool-body stdout either. A `print()` in an unguarded tool
  lands on stdout on both stacks.
- **`freeze_support()` (`mcp_server.py:713-723`): dead code, delete it.**
  `app/cti_pipeline_stage1.py:179` already aliases `ThreadPoolExecutor`. There is
  no `ProcessPoolExecutor` anywhere in the plugin.
- **`run_operation` and `wait_for_agents` are NOT wrapped** in `_stdout_safe`,
  unlike the other three CTI tools. That is a latent frame-corruption bug today,
  on the current version.

---

## 4. Breaking changes that actually apply

### 4.1 Dependency resolution (BLOCKER, cross-repo)

See section 5. This is a go/no-go, not a task.

### 4.2 Strict argument validation on all 25 tools (HIGH, agent-visible)

FastMCP 3 emits `"additionalProperties": false` on every input schema; mcp 1.29.1
omits it. Measured directly:

```
v1  call_tool("t", {"a":"hi","bogus":1})  ->  succeeds, "bogus" silently dropped
v3  call_tool("t", {"a":"hi","bogus":1})  ->  isError=True, unexpected_keyword_argument
```

DSPy forwards hallucinated extras rather than filtering them, so this changes the
failure profile of every tool. **There is no knob**: enforcement lives in the
pydantic call model, not the advertised schema.

This is arguably *better* for offensive tooling (the model gets corrected instead
of ignored), but it is a model-behaviour change and it must be soak-tested
against live ReAct runs, not desk-checked.

### 4.3 Sync tools move to a threadpool, and two of them break (HIGH)

FastMCP 3 defaults sync tools to `run_in_thread=True`. Good for 18 of the 20 core
tools. For `core_create_windows_ability` and `core_create_linux_ability` it is a
deterministic failure: both reach `ensure_lm_configured` (`app/dspy_env.py:117-154`),
an unlocked check-then-act ending in `dspy.configure(lm=...)`. Concurrent calls on
distinct worker threads hit:

```
RuntimeError: dspy.settings can only be changed by the thread that initially configured it.
```

Fix: a lock in `ensure_lm_configured`, or `run_in_thread=False` on those two.

### 4.4 Docstring parsing changes 7 tools, in both directions (MEDIUM)

FastMCP 3 parses Google-style docstrings; FastMCP 1.0 dumps `__doc__` verbatim.

- **Gain:** `Args:` entries become per-property descriptions. **30 parameter
  descriptions** become prompt text. All 30 need review for accuracy.
- **Loss:** the `Returns:` section is **stripped and discarded**. Seven sites:
  `mcp_server.py:179`, `:405`, `:573`, `:651`; `app/mcp_server.py:353`, `:436`, `:502`.

### 4.5 Per-property `title` removal (MEDIUM)

DSPy renders raw property dicts into the ReAct instruction block verbatim, so the
titles are currently prompt text. 20 of 25 tools lose them. Almost certainly an
improvement (less noise), but it is prompt text, which is the category that needs
soaking.

### 4.6 Text serialisation drift (MEDIUM)

Pretty-printed JSON becomes compact, and **list returns collapse from N content
blocks to 1**. `dspy/utils/mcp.py:22` returns a bare string for one block and a
Python list for many, so the observation the model reads **changes type** for the
8 core tools whose endpoint returns a JSON array.

### 4.7 Provably unchanged (do not re-litigate)

Decorators still return the plain function, so all 18 direct
`srv.build_adversary(...)` call sites in `tests/test_build_adversary.py` need
**zero** changes. AST discovery is untouched. `mcp.run()` still defaults to
stdio. Async tools were already concurrent on v1. 25/25 tool-name parity, zero
type drift, identical `required` sets.

### 4.8 What is NOT the problem

The six loose collection annotations (`platforms: Optional[list]`,
`agent_paws: list`, `atomic_ordering: list`, `payloads: Optional[list]`) emit
**identical degenerate schemas on both stacks**. They are worth fixing, but the
migration neither causes nor fixes them.

---

## 5. The dependency blocker

`fastmcp>=3` is **unsatisfiable** against CALDERA core's pins. Reproduced pairwise
with the real resolver:

| Core pin | fastmcp 3 requires | Result |
|---|---|---|
| `rich==13.7.0` | `rich>=13.9.4` | ResolutionImpossible |
| `packaging==23.2` | `packaging>=24.0` | ResolutionImpossible |
| `websockets==15.0` | `websockets>=15.0.1` | ResolutionImpossible |

No 3.x release escapes: all 20 stable releases carry the same floors.

### The dangerous part: it fails silently

CALDERA installs core and plugin requirements as **two sequential `pip install -r`
calls**, with no constraint file. So `ResolutionImpossible` never fires in
practice. Instead:

```
WOULD UPGRADE:
  packaging   23.2 -> 26.3    (core pins ==23.2)
  websockets  15.0 -> 17.1    (core pins ==15.0)
Exit code 0. pip check: "No broken requirements found."
```

That is two majors of `websockets` in a library core uses directly in its agent
transport, and three majors of `packaging`.

**This drift has already happened twice, undetected.** The live venv runs
`rich 15.0.0` against core's `==13.7.0`, and `cryptography 48.0.1` against core's
`==50.0.1`. Nothing in the build detects either.

Per our own `requirements.txt` header ("core-owned packages get a `>=` floor,
never a pin, so a plugin never contests a core-owned version"), adding
`fastmcp>=3` is exactly the violation that rule exists to prevent, laundered
through a transitive dependency.

**Python floor is not a blocker.** fastmcp 3.4.7 declares `requires-python >=3.10`,
inside CALDERA core's CI window (3.10.9 through 3.13).

---

## 6. Security: what is actually wrong right now

The migration is a distraction from these. All are framework-independent.

**F1, CRITICAL: path traversal to arbitrary file read, exfiltrated to the LLM
provider.** `_resolve_pipeline_file` (`mcp_server.py:75-99`) returns any absolute
path unchecked at `:78-79`, and resolves relatives with **no containment test**.
Reachable from three LLM-callable tools taking free-text paths:
`cti_pipeline_ingest_cti` (`:194`), `cti_pipeline_fuse` (`:275`),
`cti_pipeline_build_adversary` (`:415`). The file is then copied into
`data/raw/uploads/` (`:201-204`) and run through the full LLM pipeline. Plain
`plugins/mcp/.env` reaches the real secrets file with no `../` needed at all.

**This codebase already knows how to do this correctly.** `app/mcp_api.py:876-877`,
`:914-916`, `:966-967`, `:1175-1178` all do `root.resolve() in candidate.parents`,
and `tests/test_delete_containment.py:36-38` regression-tests it. The containment
discipline was applied at the browser boundary and not at the LLM boundary.

**F2, HIGH: untrusted CTI to LLM-authored shell command to execution, with no
human gate.** `app/dspy_env.py:177-181` produces a raw `command: str` with no
allowlist or length bound, POSTed as a stockpile ability. Full chain available to
one ReAct agent in one run: `core_create_windows_ability` ->
`core_create_adversary` -> `cti_pipeline_run_operation`, which posts
`"state": "running"` and `"autonomous": 1`. No `ToolAnnotations` anywhere, so the
5 mutating tools are indistinguishable from the 20 read tools in the schema the
model sees.

**F3, MEDIUM:** unencoded path-segment interpolation (`app/mcp_server.py:46`).
`core_get_ability_by_id(id="../../../plugin/mcp/gui")` reaches any path on the
CALDERA server with the red API key attached.

**F4, MEDIUM:** `os.environ.copy()` (`plan_execute.py:65`, `author.py:28`) hands
every spawned server the full parent environment including all secrets.

**F5, MEDIUM:** no timeouts anywhere. `requests.get/post` with no `timeout=`
(`app/mcp_server.py:49`, `:61`); `ClientSession(read, write)` positional, so
`read_timeout_seconds=None`. A hung CALDERA wedges the server indefinitely.

**F6, LOW/MEDIUM:** raw upstream error bodies returned to the model and browser;
the only scrubber (`app/mcp_svc.py:35`) matches OpenAI-shaped keys only.

**F7, correctness:** executor `name`/`platform` inverted at
`app/mcp_server.py:443-444` and `:510-511`. CALDERA's convention is the reverse.

**The April 2026 STDIO design RCE does not apply**, and no version change is what
makes that true. `command=sys.executable` is a literal and `args` is a key lookup
against a boot-time registry. It is protected by convention with **zero test
coverage**.

**Root cause behind F1, F2, and F4:** this codebase applies real security
discipline at the operator/HTTP boundary and none of it at the LLM/tool boundary.
For a plugin whose purpose is exposing adversary emulation to autonomous agents,
the LLM boundary is the one that matters, and it is the weaker of the two.

---

## 7. Options

Scoring 5 best, 1 worst. Agentic capability weighted 2x.

| Axis | A: stay on SDK 1.x, harden | B: SDK 2.x (`MCPServer`) | C: adopt `fastmcp` 3.x | D: build the seam |
|---|---|---|---|---|
| CVE exposure delta | **5** | 3 | 2 | 5 |
| Breaking-change cost | **5** | 1 | 2 | 4 |
| Dependency risk | **5** | 2 | **1** | 4 |
| Python-floor risk | **5** | 4 | 3 | 4 |
| Vendor risk | **4** | 3 | 2 | 4 |
| **Agentic gain (x2)** | **8** | 4 | **8** | **8** |
| Reversibility | **5** | 1 | 3 | **5** |
| Fit with stated design rules | **5** | 3 | **1** | **5** |
| **Total (/45)** | **42** | **20** | **22** | **39** |

### The reframe that decides this

**The binding constraint is the client binding, not the server framework.** Every
agentic capability we want terminates at two lines:

```python
session = await stack.enter_async_context(ClientSession(read, write))  # plan_execute.py:255
dspy_tools.append(dspy.Tool.from_mcp_tool(session, tool))              # plan_execute.py:273
```

`ClientSession(read, write)` advertises no elicitation capability, so
`ctx.elicit()` is rejected **regardless of server framework**. `convert_mcp_tool`
hardcodes `call_tool` with no `progress_callback`, so `ctx.report_progress()`
no-ops **regardless of server framework**. It reads only `name`, `description`,
`inputSchema`, so `ToolAnnotations` reach nothing **regardless of server
framework**.

A server-only migration to fastmcp 3 changes none of these.

And the capabilities are not gated on fastmcp anyway. On the **installed
mcp 1.29.1**: `Context` already has `elicit`, `report_progress`, `read_resource`,
`log`. `FastMCP.tool` already accepts `title`, `description`, `annotations`,
`structured_output`. `ClientSession` already accepts `elicitation_callback`,
`sampling_callback`, `read_timeout_seconds`. `call_tool` already accepts
`progress_callback`. **The gap is authorship, not framework.**

Two things are genuinely unique to fastmcp 3: middleware, and automatic sync-tool
threadpool offload. The first converts to nothing useful here (the gate must be
operator-facing, and the operator is in the parent process). The second is about
20 lines of `anyio.to_thread` work on Option A.

Also: **composition is a regression here.** `mount()` would collapse the two
servers into one process, so every run imports dspy and numpy, and we lose the
ability to run `caldera_core` alone.

### Recommendation

**Option A, executed properly, with Option D's seam folded in. Not "do nothing".**

Option C loses because the additions do not convert through the current client, it
costs 27 distributions, it requires a cross-repo bump of three `==` pins in
violation of our own stated convention, and **FastMCP 4.0.0b5 shipped 2026-08-28**
(verified on PyPI) with the docs site now serving v4 at the root. We would adopt a
line that is already superseded, and commit to a second migration to reach SDK v2.

Option B is the right destination at the wrong time: `mcp 2.0.0` is about five
weeks old.

### The one condition that flips this

**If these servers are ever exposed over HTTP to remote or third-party agents**
(streamable HTTP, authentication, per-operator token scoping, rate limiting,
multi-tenant sessions), **Option C wins immediately and decisively.** That is
where fastmcp has invested, it is the one thing bundled FastMCP 1.0 would make us
build ourselves, and the added authlib/joserfc stack stops being dead weight. It
also inverts every "not applicable" verdict in both CVE tables.

Nothing else flips it. Specifically **not** wanting progress, elicitation,
structured output, tool annotations, or better ReAct parsing: all reachable on A.

---

## 8. Execution plan

### Phase 0: ship this week, no migration, no cross-repo dependency

| Step | Change | Check |
|---|---|---|
| 0.1 | `requirements.txt`: `mcp>=1.9,<2` to `mcp>=1.28.1,<2` | Dry-run resolves; suite green |
| 0.2 | Containment in `_resolve_pipeline_file` (`mcp_server.py:75-99`) and `_resolve_rag_file` (`rag.py:202-215`); pin `fuse` output dir (`:292`) | New tests: `/etc/passwd`, `../../../../../../etc/passwd`, `plugins/mcp/.env` all rejected |
| 0.3 | Test asserting `command == sys.executable` and `args[0]` from the registry | Test fails if either literal is edited |
| 0.4 | Timeouts: `timeout=(5,30)` at `app/mcp_server.py:49`, `:61`; `read_timeout_seconds=` on both `ClientSession(...)` | A stalled CALDERA no longer wedges a run |
| 0.5 | `quote(segment, safe='')` on the 8 interpolation sites | `id="../../../x"` cannot escape `/api/v2/` |
| 0.6 | Wrap `run_operation` and `wait_for_agents` in `_stdout_safe`; delete dead `freeze_support()` (`:713-723`); broaden `_SECRET_RE` | Suite green |

Rollback: every item is an independent commit reverting cleanly.

### Phase 1: the client-binding seam (the actual unlock)

| Step | Change | Check |
|---|---|---|
| 1.1 | Replace `dspy.Tool.from_mcp_tool(...)` at `plan_execute.py:273` and `author.py:267` with a local converter (~12 lines) | Byte-identical trajectories on a baseline run, before adding anything |
| 1.2 | Through the seam: per-call `read_timeout_seconds`, `progress_callback`, per-operator tool-name filter, confirm-before-execute gate keyed on tool name | Gate fires on `cti_pipeline_run_operation` and both ability creators |
| 1.3 | Wire `on_progress` into `CTIIngestService()` (the callback already exists at `app/cti_ingest_svc.py:45-53` and is discarded) | Operator sees CTI stage progress in chat |

Rollback: revert two files. The seam is additive; servers are untouched.

### Phase 2: schema and error quality (framework-independent)

| Step | Change | Check |
|---|---|---|
| 2.1 | **Write the wire tests that do not exist.** Stdio round-trip fixture per server: assert 25 tool names, snapshot 25 input schemas, pin `isError` semantics | Prerequisite for everything after it, and for any future migration |
| 2.2 | Typed returns (`TypedDict`/Pydantic) on all 25 tools. Decide `{"error": ...}` vs `raise` here | Snapshot shows real output schemas with field names |
| 2.3 | Replace the 6 loose collection annotations | Snapshot diff reviewed |
| 2.4 | `ToolAnnotations(readOnlyHint=True)` on the 14 getters, `destructiveHint=True` on the 5 mutators | Feeds 1.2's gate |
| 2.5 | Convert the 20 sync REST tools to `async` with `aiohttp` (already a dependency), or `anyio.to_thread`. Lock `ensure_lm_configured` while there | Removes fastmcp 3's clearest remaining advantage |

### Phase 3: fastmcp 3, only if the flip condition is met

| Step | Change | Check |
|---|---|---|
| 3.1 | **Gate: PR against CALDERA core** bumping `rich>=13.9.4`, `packaging>=24.0`, `websockets>=15.0.1`. Full core CI | If core declines, Phase 3 stops. Do not proceed by floating the plugin file |
| 3.2 | Add `pip install -c requirements.txt -r plugins/mcp/requirements.txt` to CI | Catches the existing rich/cryptography drift as a side effect |
| 3.3 | Two import lines, two `show_banner=False`, requirements lines | Phase 2.1 snapshots regenerate; diff reviewed line by line |
| 3.4 | `run_in_thread=False` on both ability creators unless 2.5's lock landed | The dspy RuntimeError does not reproduce |
| 3.5 | Relocate the 7 discarded `Returns:` blocks; review the 30 newly visible param descriptions | Reviewed as prompt text |
| 3.6 | **Soak strict-args against live ReAct runs**; grep trajectories for `unexpected_keyword_argument` | Cannot be desk-checked |
| 3.7 | Forbid `fastmcp.Client(MCPConfig)` and `fastmcp discover` in contributing notes | Both widen the STDIO design RCE |

Rollback: revert 3.3 and 3.4 (four lines), drop `fastmcp`. **Only cheap if no
tool body was written against `ToolError` or the fastmcp `Context` API.**

---

## 9. Open questions needing a human decision

1. **Is HTTP or SSE exposure to remote or third-party agents on the roadmap?**
   The only question that changes the answer. If yes, Option C wins outright and
   Phases 0 through 2 become prep work rather than the destination.
2. **Will CALDERA core accept the three pin bumps?** Cross-repo, not ours, and the
   whole migration is gated on it. Related: core's pins are already not honored in
   the working venv for `rich` and `cryptography`. Fix that independently?
3. **`{"error": ...}` returns versus raising.** Roughly 25 sites currently return
   failures as successful results (`isError=False`), so the model reads them as
   ordinary data. Same decision on all four options; make it once.
4. **Where does the operator answer a confirm-before-execute prompt?** There is no
   channel today. `/execute` is fire-and-forget plus a `/status` poll. This needs
   a pending-approval queue, a POST endpoint, and a modal. **Largest unscoped item
   in the plan**, and it is CALDERA-side work.
5. **Does the LLM/tool boundary get the same containment discipline as the HTTP
   boundary?** A policy call about what an autonomous agent may name and author.

---

## 10. Key sources

- https://pypi.org/pypi/fastmcp/json (3.4.7 stable; 4.0.0b5 uploaded 2026-08-28)
- https://pypi.org/pypi/fastmcp-slim/json (`mcp>=1.24.0,<2.0`, `rich>=13.9.4`, `packaging>=24.0`, `websockets>=15.0.1`)
- https://pypi.org/pypi/mcp/json (latest 2.1.1; 1.x ends at 1.29.1, released 2026-08-24)
- https://gofastmcp.com/v3/getting-started/upgrading/from-mcp-sdk
- https://py.sdk.modelcontextprotocol.io/whats-new/ (1.x moves to maintenance with security patches, no deprecation date)
- https://github.com/advisories/GHSA-9h52-p55h-vw2f (CVE-2025-66416, fixed 1.23.0, states stdio unaffected)
- https://github.com/advisories/GHSA-jpw9-pfvf-9f58 (CVE-2026-52869, fixed 1.27.2, states stdio unaffected)
- https://github.com/advisories/GHSA-vj7q-gjh5-988w (CVE-2026-59950, fixed 1.28.1, WebSocket transport)
- https://github.com/advisories/GHSA-vv7q-7jx5-f767 (CVE-2026-32871, CVSS 10.0, fastmcp OpenAPI provider)
- https://github.com/advisories/GHSA-rww4-4w9c-7733 (CVE-2026-27124, fastmcp OAuth proxy)
- https://www.ox.security/blog/the-mother-of-all-ai-supply-chains-critical-systemic-vulnerability-at-the-core-of-the-mcp/

---

# Addendum: supply chain audit (2026-08-30)

Scanned all 227 installed distributions in `.calderavenv` against OSV, cross-checked
independently with `pip-audit`. Both tools agree.

## Result: 7 advisories across 4 packages, and **none of them are reachable**

| Package | Installed | Advisory | Fixed in | Reachable? |
|---|---|---|---|---|
| cryptography | 48.0.1 | CVE-2026-69247 PKCS#7 Bleichenbacher oracle | 50.0.0 | **No** |
| cryptography | 48.0.1 | CVE-2026-69249 exponential path building | 49.0.0 | **No** |
| cryptography | 48.0.1 | CVE-2026-69248 wildcard DNS permittedSubtrees escape | 49.0.0 | **No** |
| asyncssh | 2.20.0 | CVE-2026-54591 SCP path traversal to arbitrary write | 2.23.1 | **No** |
| asyncssh | 2.20.0 | CVE-2026-54590 AuthorizedKeysFile `%u` escape | 2.23.1 | **No** |
| diskcache | 5.6.3 | CVE-2025-69872 unsafe pickle deserialization | **none** | Local only |
| pip | 26.1.2 | CVE-2026-13346 | 26.2 | Build tooling |

### Why the cryptography ones are not reachable

All three live in code paths nothing calls. CVE-2026-69247 needs the PKCS#7
decryption API; `grep -rn "pkcs7\|PKCS7"` across core, all plugins, and all 227
venv packages returns zero call sites. The other two live in
`cryptography.x509.verification`, cryptography's own Rust path builder. CALDERA
terminates no TLS in Python, and every HTTP client in the tree (requests, httpx,
litellm, aiohttp, urllib3) verifies through stdlib `ssl` and OpenSSL, not through
cryptography's verifier.

Core's first-party cryptography use is symmetric only: Fernet, AES-CBC and
PBKDF2HMAC for payload encryption, in three files. The plugin does not import
cryptography at all.

### Why the asyncssh ones are not reachable

CALDERA does run an SSH tunnel server (`app/contacts/tunnels/tunnel_ssh.py:29`),
unconditionally, on `0.0.0.0:8022`. But `create_server` is passed only
`server_host_keys`, so `allow_scp=False`, `sftp_factory=None`,
`session_factory=None`. asyncssh refuses session channels outright when none of
those is set. Verified live against CALDERA's own `SSHServerTunnel`:

```
scp write   -> ChannelOpenError: Session refused
sftp        -> ChannelOpenError: Session refused
exec        -> ChannelOpenError: Session refused
direct-tcpip forwarding -> allowed (this is the tunnel feature)
```

There is no channel on which an SCP command can be delivered. For CVE-2026-54590,
CALDERA passes no `config=` to `create_server`, so `authorized_client_keys` is
`None` and there is nothing for `%u` to expand into. Public-key auth is not even
offered: `SSHServerTunnel` implements only password auth.

Both flip if someone adds `sftp_factory` / `allow_scp` to that file, or passes an
sshd-style config. Worth a comment on the line.

## What actually needs doing

### 1. The venv is nine days stale. This is the whole fix for 5 of 7.

Core commit `e0b5e1ce` (2026-08-26) already bumped `cryptography` to 50.0.1 and
`asyncssh` to 2.23.1 for exactly these advisories. The venv was built 2026-08-17
and faithfully matches core's pins *as of that date*. Nothing corrupted it.

```bash
pip install -r requirements.txt
```

That takes asyncssh to 2.23.1 with zero conflict (nothing in the tree constrains
it) and closes both SSH advisories.

### 2. mlflow blocks core's new cryptography pin, going forward

`mlflow` declares `cryptography<50,>=43.0.0` as a **base** dependency, and it is
the only active cap on cryptography in the tree. Core now pins
`cryptography==50.0.1`. Those are mutually exclusive. On the next clean install
pip backtracks to `mlflow 3.2.0`, which caps `pyarrow<22`, which has no cp314
wheels, so it will not even build.

No mlflow release in its history admits cryptography 50.x. **The reachable
ceiling is 49.0.0**, which closes two of the three cryptography advisories. The
one left open (PKCS#7) is the unreachable one, so this costs nothing in practice.

Either ask core to relax to `cryptography>=49.0.0,<51`, or make mlflow optional.
Worth checking whether mlflow is load-bearing: it is used for run tracking
(`app/mlflow_run.py`), not for the pipeline itself.

### 3. diskcache has no fix, but dspy ships a mitigation you are not using

dspy enables its disk cache by default at `~/.dspy_cache` (66 MB currently, actively
in use). The plugin never calls `dspy.configure_cache`, so it inherits
`restrict_pickle=False`. Directories are 0755 and files 0644, owner-writable only,
so on a single-operator host the local vector crosses no privilege boundary. In a
container or shared CI with a shared home it would.

One line at the existing `dspy.configure` site in `app/dspy_env.py`:

```python
dspy.configure_cache(restrict_pickle=True)
```

Available from dspy 3.2.0; needs the `dspy>=3.3.0` floor to avoid a litellm cap.

## The structural problems, which matter more than the CVE rows

**13 direct dependencies with no version constraint at all:** `aiofiles`,
`beautifulsoup4`, `dspy`, `litellm`, `mlflow`, `numpy`, `psutil`, `pydantic`,
`python-dotenv`, `rapidfuzz`, `requests`, `spacy`, `trafilatura`. No lockfile
anywhere, zero `--hash` pins. A compromised upload of any in-range version is
installed silently.

**The `mcp>=1.9,<2` floor is itself exploitable by backtracking.** Demonstrated
with the real resolver:

```
pip install "mcp>=1.9,<2" "pydantic<2.9"   ->  mcp 1.12.4
```

`mcp 1.12.4` carries three advisories. A mild cap on an unrelated package is
enough to walk `mcp` backwards into vulnerable territory. Raise the floor to
`mcp>=1.28.1,<2`.

**Two packages are invisible to every scanner.** `en_core_web_lg` (425 MB) and
`en_core_web_sm` are installed from GitHub release URLs, not PyPI, so OSV has no
data and `pip-audit` skips them by name. spaCy records a sha256 after download,
but that is trust-on-first-use, not a pre-declared expected hash. The trust anchor
is Explosion's GitHub releases plus TLS. Loading a spaCy model is code execution.

**The two-pass install has no constraint file.** `pip check` does not catch this:
it returns "No broken requirements found" on a drifted venv, because a downgraded
core package still satisfies every declared range. It is below core's pin, not
broken. Only a resolve against core's pin file detects it:

```bash
pip install --dry-run -c ../../requirements.txt -r plugins/mcp/requirements.txt
```

Adding that to CI is the single highest-value change here, and the plugin CI
currently runs only flake8.

## Priority

1. `pip install -r requirements.txt` to un-stale the venv. Free, closes both SSH advisories.
2. Add the constraint-resolve check to CI. Catches this whole class permanently.
3. Raise `mcp>=1.28.1,<2` and add floors to the 13 unpinned deps.
4. `dspy.configure_cache(restrict_pickle=True)`.
5. Resolve the mlflow / cryptography ceiling with core, or make mlflow optional.

None of this involves FastMCP. The supply-chain risk in this plugin is the
unpinned scientific-Python stack and the absent CI gate, not the MCP layer.

## Is there a lighter-weight `mcp`? No, and it does not matter

`mcp` 1.29.1 declares **17 required** dependencies and only 3 extras (`cli`,
`rich`, `ws`). `starlette`, `uvicorn`, `sse-starlette`, `python-multipart`,
`httpx` and `pyjwt[crypto]` are all **required**, not optional, even for a
stdio-only server. The plugin already installs with no extras, so there is
nothing to turn off.

But the weight question is moot, because almost all of it is already in the tree
for other reasons. Measured as a true removal diff against every other declared
dependency of core and the plugin:

```
tree without mcp : 168 packages
tree with mcp    : 173 packages
marginal cost    :   5 packages  (mcp, httpx-sse, pyjwt, python-multipart, sse-starlette)
                     2.8 MB total
```

`starlette` and `uvicorn` are already required by `mlflow-skinny` and `fastapi`.
`httpx`, `pydantic`, `jsonschema` and `anyio` come in via litellm, dspy and mlflow.
`cryptography` is pinned by core directly.

For scale, in the same tree: `en_core_web_lg` is 425 MB, `litellm` 113 MB,
`mlflow` 61 MB. The entire MCP SDK is 0.66% of the spaCy model.

Hand-rolling a stdio JSON-RPC server would recover those 2.8 MB and cost protocol
conformance ownership. It is also not actually possible without more work than it
sounds: `mcp` is used on **both** sides here, `ClientSession` and `stdio_client`
in `plan_execute.py` and `author.py`, and `dspy.Tool.from_mcp_tool` requires a
real `mcp.ClientSession`. Dropping the SDK means reimplementing the client, the
server, and the DSPy bridge.

**The backtracking exposure is a floor problem, not a weight problem.** The fix is
one character range, and it costs nothing:

```diff
-mcp>=1.9,<2
+mcp>=1.28.1,<2
```

If reducing supply-chain surface is the actual goal, the targets are `litellm`,
`mlflow` and the spaCy model, not the MCP SDK.
