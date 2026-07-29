#!/usr/bin/env node
import { ClineCore } from "@cline/sdk";

import { jsonlEmitter, parseRunnerRequest, readStdin, runClineCoreProbe, RunnerProtocolError } from "./runner-lib.mjs";

const emitRecord = jsonlEmitter();

try {
  const request = parseRunnerRequest(await readStdin());
  await runClineCoreProbe({ ClineCoreClass: ClineCore, request, emitRecord });
} catch (error) {
  const isProtocolError = error instanceof RunnerProtocolError;
  emitRecord({
    type: "blocker",
    code: isProtocolError ? error.code : "clinecore_probe_failed",
    summary: isProtocolError ? error.message : "ClineCore probe failed before producing a valid result.",
    evidence: error instanceof Error ? `error_type=${error.name}` : "error_type=unknown",
  });
  emitRecord({ type: "terminal_result", status: "failed" });
  process.exitCode = 1;
}
