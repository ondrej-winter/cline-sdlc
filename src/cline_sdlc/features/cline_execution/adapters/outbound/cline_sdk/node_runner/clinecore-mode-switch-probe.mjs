#!/usr/bin/env node
import { ClineCore } from "@cline/sdk";

import {
  jsonlEmitter,
  parseRunnerRequest,
  readStdin,
  runClineCoreModeSwitchProbe,
  RunnerProtocolError,
} from "./runner-lib.mjs";

const emitRecord = jsonlEmitter();

try {
  const request = parseRunnerRequest(await readStdin());
  await runClineCoreModeSwitchProbe({ ClineCoreClass: ClineCore, request, emitRecord });
} catch (error) {
  const isProtocolError = error instanceof RunnerProtocolError;
  emitRecord({
    type: "blocker",
    code: isProtocolError ? error.code : "clinecore_mode_switch_probe_failed",
    summary: isProtocolError ? error.message : "ClineCore mode-switch probe failed before producing a valid result.",
    evidence: error instanceof Error ? `error_type=${error.name}` : "error_type=unknown",
  });
  emitRecord({ type: "terminal_result", status: "failed" });
  process.exitCode = 1;
}
