# Cline SDK capability matrix

## Status

- Source plan: `docs/plans/cline-sdk-first-sdlc-orchestrator-plan.md`
- Source spec: `docs/specs/cline-sdk-first-sdlc-orchestrator-spec.md`
- Related ADR: `docs/adr/0002-use-cline-sdk-contract-instead-of-cli-probing.md`
- Matrix date: 2026-07-30
- Decision state: SDK adapter foundation and same-session Plan-to-Act mode switch
  are proven for the reset MVP; SDK-native Plan/Act mediation remains out of MVP
  scope

This matrix maps the reset MVP SDK execution requirements to official Cline SDK
references, implemented adapter evidence, local smoke evidence, and blockers. It
is a delivery gate: `--plan-file` implementation must not use the SDK-first path
until every full-contract capability needed for repository-changing work is
proven by official SDK/API references plus local real-SDK smoke evidence or is
explicitly owned by the orchestrator.

## Classification labels

| Label | Meaning |
| --- | --- |
| `Agent`-proven | Proven through the documented `Agent`/`AgentRunResult` path and local real-SDK smoke evidence. |
| `ClineCore`-proven | Proven through the documented `ClineCore` session/probe path and local real-SDK smoke evidence. |
| Orchestrator-owned | Implemented and enforced by Python application/adapters outside the SDK primitive itself. |
| Out of MVP scope | Not required for the reset MVP because the orchestrator owns sequencing and reconciliation. |
| Unproven | Expected or desirable, but not proven by both official SDK references and local real-SDK smoke evidence. |
| Unsupported | No currently identified SDK primitive supports the requirement. |
| Blocked | Missing proof prevents repository-changing SDK-first lifecycle delivery. |

## Source references

Official references already inspected for the SDK-first plan:

- SDK overview: <https://docs.cline.bot/sdk/overview>
- SDK Agent reference: <https://docs.cline.bot/sdk/reference/agent.md>
- SDK Events reference: <https://docs.cline.bot/sdk/reference/events.md>
- SDK Permission Handling guide:
  <https://docs.cline.bot/sdk/guides/permission-handling.md>
- SDK ClineCore guide: <https://docs.cline.bot/sdk/clinecore.md>

Local evidence sources:

- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/runner.mjs`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/clinecore-probe.mjs`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/node_runner/clinecore-mode-switch-probe.mjs`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/adapter.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/protocol.py`
- `src/cline_sdlc/features/cline_execution/adapters/outbound/cline_sdk/runtime_probe.py`
- `src/cline_sdlc/features/cline_execution/application/use_cases/preflight_sdk_runtime.py`
- `scripts/run_cline_sdk_adapter_example.py`
- `scripts/diagnose_cline_sdk_events.py`

## Capability matrix

| Capability | Classification | Official SDK reference | Local evidence | Delivery decision |
| --- | --- | --- | --- | --- |
| `Agent.run` session execution | `Agent`-proven | Agent reference documents `new Agent(config)`, `agent.subscribe(listener)`, and `await agent.run(input)`. | Task 4a local smoke completed through `node_runner/runner.mjs` with terminal status `completed`; CI-safe fake Agent tests cover protocol behavior. | Usable for diagnostic SDK proof only; not sufficient for repository-changing lifecycle delivery. |
| Agent event subscription | `Agent`-proven | Agent and Events references document direct runtime event subscription. | Task 4a and Task 8 smoke observed `run-started`, `message-added`, `turn-started`, `assistant-text-delta`, `usage-updated`, `assistant-message`, `turn-finished`, and `run-finished`. | Diagnostic event stream is proven; event payloads are not authoritative lifecycle state. |
| `AgentRunResult` terminal status | `Agent`-proven | Agent reference documents `AgentRunResult.status` values `completed`, `aborted`, and `failed`. | Runner normalizes these statuses into the Python protocol and emits exactly one terminal result. | Proven as SDK-run terminal status, not as role-specific SDLC structured outcome. |
| `AgentRunResult.outputText` and messages | `Agent`-proven as diagnostic/model output | Agent reference documents `outputText`, `messages`, usage, and error fields. | Runner keeps assistant text and SDK messages as safe diagnostic/model-output evidence and avoids raw reasoning/secrets by default. | Must not be treated as authoritative lifecycle state or a substitute for role-specific structured outcomes. |
| Session identity | `ClineCore`-proven for ClineCore; `Agent`-proven for agent/run IDs | Agent reference documents `agentId` and `runId`; ClineCore guide documents `sessionId`, manifests, and session artifacts. | Task 4a recorded safe `agentId`/`runId`; Task 4b smoke recorded session, manifest, messages, and session-result diagnostics. | Diagnostic references are proven; they do not authorize lifecycle advancement. |
| Workspace root and working directory | `ClineCore`-proven | ClineCore guide documents `cwd` and `workspaceRoot` session configuration. | Task 4b probe used validated adapter-owned `cwd` and `workspaceRoot` from the runner request. | Proven as ClineCore configuration; still subject to Python path validation. |
| Plan/Act mode selection | ClineCore API-surface proven and adapter-proven | Adapter-local `@cline/shared` types expose `AgentMode = "act" | "plan" | "yolo" | "zen"`; `SessionPromptConfig.mode?: AgentMode`; `ClineCoreStartConfig` includes the prompt config fields; and `SendSessionInput.mode?: AgentMode` is accepted by `RuntimeHost.runTurn` / `ClineCore.send`. | `runner-lib.mjs` maps adapter execution mode `read_only` to SDK `plan` and `write_capable` to SDK `act`, emits a safe `plan_act_mode` diagnostic, and `node --test runner-lib.test.mjs` passed locally on 2026-07-30 with mode-selection coverage. | Proven only as explicit mode selection at session start; not proof of planning-result observation, user-input classification, or session-bound Act authorization. |
| Programmatic same-session Plan-to-Act mode switch API surface | `ClineCore`-proven | Adapter-local type references expose `ClineCore.send` as `RuntimeHost["runTurn"]`; `RuntimeHost.runTurn(input: SendSessionInput)` accepts `sessionId`, `prompt`, and optional `mode?: AgentMode`. | `runClineCoreModeSwitchProbe` starts a ClineCore session in `plan`, then sends a follow-up turn with the same `sessionId` and `mode: "act"`; CI-safe fake ClineCore tests prove the adapter call sequence and diagnostics. Real SDK smoke through `clinecore-mode-switch-probe.mjs` completed on 2026-07-30 after setting `interactive: true`, emitting `plan_act_start_mode=plan`, `plan_act_send_mode=act`, `same_session_mode_switch=true`, and terminal status `completed`. | Proven and accepted as the reset MVP Plan/Act primitive. The orchestrator authorizes the Act turn by deciding to send the same-session `mode: "act"` turn after the Plan turn completes. |
| Built-in tool policy coverage | `ClineCore`-proven | ClineCore and permission references document tools, tool policies, and default tool behavior. | Task 4b probe installs explicit fail-closed tool policies and reports tool-policy coverage diagnostics. | Proven enough to avoid SDK default auto-approval; not proof of repository-changing safety by itself. |
| Dynamic tool approval callback | Unproven SDK-native primitive / out of MVP scope | Permission Handling guide documents `ClineCore.create(...)` capability `requestToolApproval`. | CI-safe fake ClineCore tests exercise a callback; local real-SDK smoke installed the handler but did not observe a real approval request callback. | Does not block the reset MVP while repository-changing authority stays orchestrator-owned and post-Act Git/validation/commit gates remain authoritative. |
| Permission approval evidence | Unproven SDK-native primitive / out of MVP scope | Permission references establish approval concepts, but local evidence has not proven real dynamic approval behavior. | Runtime preflight reports `permission_approval` as unproven diagnostic capability evidence. | Does not block the reset MVP; SDK permission evidence must not be claimed until a real callback is observed. |
| Plan/Act observation | Unproven SDK-native primitive / out of MVP scope | Local package types prove session mode selection but do not prove a structured planning-result observation API. Inspected Agent, Events, Permission Handling, and ClineCore pages do not prove direct `needs_user_input` / `ready_to_act` semantics. | Same-session mode-switch smoke proves the orchestrator can run Plan then Act in one session, but not SDK-native planning-result classification. | Does not block the reset MVP because the orchestrator owns the sequencing decision; do not claim SDK-native `needs_user_input` / `ready_to_act` semantics. |
| Act authorization | Orchestrator-owned for MVP; SDK-native primitive unproven | Local package types and smoke prove `mode: "act"` can be supplied for a same-session turn. They do not prove a distinct SDK authorization API. | `clinecore-mode-switch-probe.mjs` proves the same-session Act turn can be sent programmatically. | Accepted for reset MVP as orchestrator-owned authorization to send the same-session Act turn after the Plan turn completes. |
| Structured role-specific outcomes | Blocked for SDK primitive; orchestrator-owned validation exists for normalized terminal outcomes | Agent result status and ClineCore session result are documented, but role-specific SDLC outcomes are not proven as SDK primitives. | Python DTOs/protocol validate normalized terminal results; existing lifecycle tests enforce role outcomes independently. | SDK output remains evidence only; missing role-specific structured outcomes block lifecycle advancement. |
| Event/evidence stream distinction | Orchestrator-owned with `Agent`/`ClineCore` inputs | Events reference documents SDK event streams. | Python protocol labels normalized events as diagnostic, assistant output, file change, validation, approval request, blocker, timeout, or interruption where supported. Unknown SDK events remain diagnostic. | Proven as adapter-owned normalization; only promoted evidence may be used for reconciliation. |
| Timeout handling | Orchestrator-owned | SDK docs expose `abort(reason?)`; Python adapter owns subprocess timeout. | `ClineSdkSessionRunner` terminates bounded child processes and returns structured timeout blockers such as `sdk_runner_timeout`. | Proven at adapter boundary; not proof of SDK-authored recovery metadata. |
| Interruption handling | Orchestrator-owned | SDK docs expose `abort(reason?)`; Python bootstrap/adapter own process signal handling. | Adapter and signal tests cover interruption pathways; protocol supports interruption terminal results. | Proven as adapter/orchestrator behavior; SDK-authored interruption recovery remains unproven. |
| Diagnostic references | `Agent`-proven, `ClineCore`-proven, and orchestrator-owned | Agent reference documents IDs and usage; ClineCore guide documents session artifacts. | Local smokes recorded safe agent/run/session/manifests/messages/usage diagnostics without printing secrets. | Proven for audit/troubleshooting only, not authoritative state. |
| File-change evidence | Unproven / blocked as SDK primitive; orchestrator-owned through Git reconciliation | ClineCore supports built-in tools, but inspected evidence has not proven normalized SDK file-change observations suitable for reconciliation. | Repository coordination slice independently reconciles changed paths through Git; SDK adapter currently does not prove authoritative file-change events. | SDK file-change evidence remains blocked; Git reconciliation remains authoritative. |
| Validation command evidence | Orchestrator-owned | SDK docs do not prove role-specific validation evidence suitable for lifecycle advancement. | Lifecycle orchestration and repository coordination own validation discovery/execution evidence. | SDK output cannot replace validation evidence. |
| CLI probe readiness | Blocked as SDK readiness source | ADR 0002 rejects terminal probing as the production execution boundary. | `PreflightSdkRuntime` rejects `CLI_PROBE` capability sources; CLI probe code remains compatibility/discovery surface until Task 10. | Must not be used as production-equivalent SDK readiness evidence. |

## Reset MVP requirement mapping

| Reset MVP requirement | Current mapping | Gate decision |
| --- | --- | --- |
| Fresh bounded session creation | `Agent.run` and ClineCore session start are proven; Python adapter owns finite timeout. | Partially satisfied for diagnostics. |
| Explicit session role selection | Python session DTOs model roles; SDK direct role semantics are limited to safe config/diagnostics. | Orchestrator-owned; not enough for lifecycle delivery alone. |
| Explicit instructions and repository context | Python protocol serializes instructions, safe context, working directory, and role. | Adapter-owned proof exists. |
| Configured skill availability requirements | Existing preflight/skill checks are orchestrator-owned and not SDK-proven. | Orchestrator-owned; SDK skill semantics remain outside this matrix. |
| Operation policy and permission constraints | Python operation policy is orchestrator-owned; ClineCore tool policy coverage is proven; real dynamic approval remains unproven. | Satisfied for reset MVP through orchestrator-owned operation policy, fail-closed tool policies, and independent Git/validation/commit gates. |
| Plan/Act mode selection | ClineCore type surface and adapter code can select `plan` or `act` explicitly from the adapter execution mode. | Proven as mode selection only. |
| Programmatic same-session Plan-to-Act mode switch | ClineCore type surface, fake adapter tests, and real ClineCore smoke show `ClineCore.send` can carry `mode: "act"` for an existing `sessionId` after a `plan` start when the session is kept interactive. | Satisfied as a mode-switch primitive; still not full Plan/Act mediation. |
| Plan/Act observation | No SDK-native planning-result observation is required for the reset MVP; same-session Plan-to-Act sequencing is orchestrator-owned. | Out of MVP scope as an SDK-native primitive. |
| Act authorization | Same-session `mode: "act"` send is proven; authorization to send that turn is owned by the orchestrator. | Satisfied for reset MVP as orchestrator-owned authorization. |
| Structured event or evidence streams | Agent/ClineCore events are proven as inputs; Python protocol distinguishes diagnostic observations from promoted evidence. | Partially satisfied; only normalized promoted evidence may be reconciled. |
| Structured role-specific terminal outcomes | Python validates normalized terminal results; SDK role-specific structured outcomes are not proven. | Blocked for lifecycle advancement. |
| Timeouts and interruptions | Python adapter/orchestrator own bounded timeout and interruption behavior. | Satisfied at adapter boundary. |
| Diagnostic references | Agent and ClineCore local smoke evidence proves safe diagnostic references. | Satisfied for audit/troubleshooting. |
| File-change reconciliation | Repository coordination owns Git reconciliation; SDK file-change evidence is unproven. | Orchestrator-owned Git evidence remains required. |
| Validation evidence | Lifecycle/repository slices own validation evidence. | Orchestrator-owned; SDK output cannot substitute. |
| Local atomic commit gate | Repository coordination owns explicit staging and commit gating. | Orchestrator-owned; not SDK capability. |

## Gate conclusion

The SDK adapter foundation is proven for controlled diagnostics, minimal Agent
execution, ClineCore session probing, same-session Plan-to-Act mode switching,
safe event normalization, timeout handling, and diagnostic references. For the
reset MVP, the orchestrator owns the sequencing decision: run a Plan turn, wait
for it to complete, then send an Act turn to the same SDK session when the
approved slice envelope still matches.

The following SDK-native capabilities remain unproven and must not be claimed,
but they no longer block the reset MVP:

- direct SDK `needs_user_input` / `ready_to_act` planning-result observation;
- a distinct SDK-native post-plan Act authorization primitive;
- real dynamic permission approval callback evidence;
- role-specific structured SDLC outcomes as SDK primitives;
- SDK file-change events as authoritative reconciliation input.

Lifecycle delivery must still fail closed when independent orchestrator-owned
Git reconciliation, focused validation, artifact/digest checks, or commit gating
do not agree. It must not promote assistant prose, terminal output, Cline
Checkpoints, `AgentRunResult.outputText`, or CLI probe observations into
authoritative lifecycle state.
