# Cline CLI capability spike

## Status

- Date: 2026-07-23
- Related plan task: `0.3` in `docs/plans/cline-sdlc-orchestrator-plan.md`
- Cline executable observed: `/Users/owinter/.nvm/versions/node/v22.22.3/bin/cline`
- Cline version observed: `3.0.46`
- Decision: **Checkpoint A remains blocked** pending deeper supervised proof.

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

## Critical contracts not yet proven

The following Checkpoint A requirements remain unproven by this slice:

1. **Exactly one machine-detectable terminal outcome**
   - Help and version output do not prove that an arbitrary Cline session can emit
     exactly one dedicated terminal outcome channel or file that is separate from
     ordinary assistant prose.
2. **Pre-execution permission mediation**
   - Help output advertises hook injection, but this slice does not prove that a
     parent process can enforce argument-aware allow/deny decisions before a
     prohibited operation executes.
3. **Interruption recovery observability**
   - Help output advertises timeouts, but this slice does not prove bounded child
     termination, sufficient event capture, or changed-path attribution after
     timeout or external interruption.
4. **Required skill availability without unintended network behavior**
   - Help output advertises a `skill` command backed by the open skills CLI, but
     this slice does not prove that required skills can be checked without
     network-backed `npx` behavior.

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

The default automated tests use deterministic fake executables and do not require
real Cline credentials, network access, or global developer state.

## Decision and next action

Task 0.3 has established the first supervised capability evidence surface and
captured advertised Cline CLI support in a typed report. It has **not** proven the
critical runtime behavior needed to pass Checkpoint A.

Before Tasks 1.1 and later can be authorized, a follow-up supervised spike must
exercise real Cline sessions in a disposable repository with isolated data and
hook directories to prove or reject:

- dedicated terminal outcome emission;
- pre-execution permission enforcement;
- timeout/interruption cleanup and write attribution;
- skill availability probing behavior.

If any critical contract cannot be proven, implementation must stop for product
review and an SDK-direction decision rather than weakening the specification.
