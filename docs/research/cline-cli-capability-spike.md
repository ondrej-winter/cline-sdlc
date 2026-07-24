# Cline CLI capability spike

## Status

- Date: 2026-07-23
- Related plan task: `0.3` in `docs/plans/cline-sdlc-orchestrator-plan.md`
- Cline executable observed: `/Users/owinter/.nvm/versions/node/v22.22.3/bin/cline`
- Cline version observed: `3.0.46`
- Decision: **Checkpoint A remains blocked** after supervised real-Cline proof.

## Purpose

Task 0.3 is a supervised proof for the CLI-wrapper architecture. It must determine
whether the installed Cline CLI can support the specification's non-negotiable
contracts before production lifecycle implementation proceeds.

The proof must not treat a version string or help text as sufficient evidence for
critical runtime behavior.

## Observed advertised capabilities

Running `cline --help` and `cline --version` locally showed that Cline `3.0.46`
advertises these supporting capabilities:

- `--json` for JSON message output;
- `--timeout <seconds>` for finite timeout configuration;
- `--cwd <path>` for explicit working directory selection;
- `--data-dir <path>` for isolated local state;
- `--hooks-dir <path>` for runtime hook injection;
- `skill` command support for skill management;
- `--version` reporting `3.0.46`.

These are useful prerequisites for the CLI-wrapper design, but they do not prove
the critical contracts by themselves.

## Critical contracts not proven by the supervised real-Cline proof

The supervised proof run on 2026-07-23 used Cline `3.0.46` in a disposable Git
repository with isolated Cline data and hook directories. The command exited `1`,
meaning one or more critical observations remained blocking. The typed report was
captured locally under the ignored `.cline-sdlc-proof/` proof directory and
contained no committed secrets.

The following Checkpoint A requirements remain unproven:

1. **Exactly one machine-detectable terminal outcome**
   - The supervised session emitted `0` parseable terminal outcomes where exactly
     one was required.
2. **Pre-execution permission mediation**
   - The supervised session outcome did not prove that a parent process can
     enforce argument-aware allow/deny decisions before a prohibited operation
     executes.
3. **Interruption recovery observability**
   - The supervised session outcome did not prove bounded child termination,
     sufficient event capture, or changed-path attribution after timeout or
     external interruption.
4. **Required skill availability without unintended network behavior**
   - Real `skill list` probing reported required skills as missing for
     `idea-refine`, `spec-driven-development`, `planning-and-task-breakdown`, and
     `code-review-and-quality`.

## Implemented local evidence model

This slice adds a minimal `cline_execution` vertical slice that records capability
evidence without starting lifecycle work:

- `CapabilityObservation` records a capability name, status, criticality, and
  safe evidence string.
- `ClineCapabilityReport` aggregates observations and exposes blocking critical
  observations.
- `ProveClineCliContracts` delegates probing through an application-owned port.
- `SubprocessClineCapabilityProbe` uses argument-array subprocess calls to inspect
  help/version output with a finite timeout.
- `SubprocessClineCapabilityProbe` now also exercises requested skill availability
  through deterministic `skill list` probing in automated tests, while treating
  failed skill probing as unproven rather than silently available.
- `CapabilityProbeRequest.supervised_session_probe` enables an explicit bounded
  session probe with caller-supplied repository, data, and hook directories.
- The fake-backed supervised probe validates exactly-one terminal outcome
  detection, permission-mediation evidence, interruption-recovery evidence,
  duplicate-outcome rejection, and bounded timeout reporting without real Cline,
  network access, or developer repository state.
- The supervised probe now extracts candidate terminal outcomes from top-level
  JSON lines and known Cline-style wrapped event fields (`message`, `content`,
  `text`, `data`, and `payload`). This narrows the earlier evidence gap where
  `cline --json` may emit event envelopes rather than the orchestrator's terminal
  outcome as the top-level JSON object.
- `tests/manual/cline_execution/prove_real_cline_capability.py` now provides a
  supervised proof command for explicitly selected real Cline executables. It
  requires caller-supplied disposable repository, isolated data, and hook
  directories, invokes the existing application use case and subprocess adapter,
  and emits one redacted JSON capability report with blocking observations.

The default automated tests use deterministic fake executables and do not require
real Cline credentials, network access, or global developer state.

## Supervised proof procedure

Run the proof only in a disposable repository and isolated Cline state directory.
Do not run it from the developer's working repository.

Example:

```shell
uv run python tests/manual/cline_execution/prove_real_cline_capability.py \
  --cline-command /Users/owinter/.nvm/versions/node/v22.22.3/bin/cline \
  --repository-root /tmp/cline-sdlc-proof-repo \
  --data-directory /tmp/cline-sdlc-proof-data \
  --hooks-directory /tmp/cline-sdlc-proof-hooks \
  --required-skill idea-refine \
  --required-skill spec-driven-development
```

Exit code `0` means every critical observation in the typed report is proven.
Exit code `1` means one or more critical observations remain blocking. The
command prints the complete redacted JSON report either way so the result can be
copied into this research note after human review.

## Supervised proof result and next action

Task 0.3 has established the first supervised capability evidence surface,
captured advertised Cline CLI support in a typed report, added deterministic
required-skill probing, added a fake-backed supervised session proof path, and
added a manual real-Cline proof command. The command was run against the installed
Cline `3.0.46` executable in a disposable repository with isolated data and hook
directories on 2026-07-23. The result **rejects Checkpoint A for the current
CLI-wrapper implementation evidence** because all critical runtime contracts
remained blocking in the typed report.

Tasks 1.1 and later remain unauthorized. A product decision is required before
continuing: either revise the CLI-wrapper proof mechanism and rerun the
supervised spike, install/configure required skills and prove the missing
contracts through supported Cline behavior, or review an SDK-based orchestration
direction. Any continuation must still prove or explicitly redesign:

- dedicated terminal outcome emission;
- pre-execution permission enforcement;
- timeout/interruption cleanup and write attribution;
- real Cline skill availability probing behavior without unintended network-backed
  side effects.

The next supervised proof run should specifically determine whether real
`cline --json` emits the orchestrator terminal outcome as a known wrapped event
field, a top-level object, another stable event shape, ordinary prose only, or no
recoverable outcome at all. Passing fake-backed wrapped-event tests is not itself
Checkpoint A evidence; it only makes the proof adapter capable of recognizing the
most likely structured event envelopes.

If any critical contract cannot be proven, implementation must stop for product
review and an SDK-direction decision rather than weakening the specification.
