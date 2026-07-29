#!/usr/bin/env node
import { Agent } from "@cline/sdk";

import { jsonlEmitter, parseRunnerRequest, readStdin, runAgentProof, RunnerProtocolError } from "./runner-lib.mjs";

const emitRecord = jsonlEmitter();

try {
  const request = parseRunnerRequest(await readStdin());
  await runAgentProof({ AgentClass: Agent, request, emitRecord });
} catch (error) {
  const isProtocolError = error instanceof RunnerProtocolError;
  emitRecord({
    type: "blocker",
    code: isProtocolError ? error.code : "sdk_runner_failed",
    summary: isProtocolError ? error.message : "Cline SDK runner failed before producing a valid Agent result.",
    evidence: error instanceof Error ? `error_type=${error.name}` : "error_type=unknown",
  });
  emitRecord({ type: "terminal_result", status: "failed" });
  process.exitCode = 1;
}
