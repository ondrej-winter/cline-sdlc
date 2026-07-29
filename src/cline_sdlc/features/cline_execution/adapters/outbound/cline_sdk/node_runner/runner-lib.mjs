/** Minimal JSONL runner library for the adapter-owned Cline SDK Agent proof.
 *
 * Official SDK references used by this proof:
 * - SDK overview: https://docs.cline.bot/sdk/overview
 * - Agent reference: https://docs.cline.bot/sdk/reference/agent.md
 * - Events reference: https://docs.cline.bot/sdk/reference/events.md
 *
 * The documented shape is `new Agent(...)`, `agent.subscribe(...)`, and
 * `await agent.run(...)`. This runner intentionally proves only the bare Agent
 * path. ClineCore sessions, repository tools, Plan/Act mediation, and dynamic
 * approvals remain unproven here.
 */

const SCHEMA_VERSION = 1;
const SAFE_STATUS_MAP = new Map([
  ["completed", "completed"],
  ["aborted", "aborted"],
  ["failed", "failed"],
]);
const REDACTED_VALUE = "[REDACTED]";

export class RunnerProtocolError extends Error {
  constructor(message, code = "invalid_runner_request") {
    super(message);
    this.name = "RunnerProtocolError";
    this.code = code;
  }
}

export function parseRunnerRequest(rawInput) {
  let payload;
  try {
    payload = JSON.parse(rawInput);
  } catch {
    throw new RunnerProtocolError("Runner request was not valid JSON.");
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new RunnerProtocolError("Runner request must be a JSON object.");
  }
  if (payload.schemaVersion !== SCHEMA_VERSION) {
    throw new RunnerProtocolError("Runner request schema version is unsupported.");
  }
  const instructions = requiredString(payload, "instructions");
  const outcomeContract = requiredString(payload, "outcomeContract");
  const workingDirectory = requiredString(payload, "workingDirectory");
  const timeoutSeconds = payload.timeoutSeconds;
  if (!Number.isFinite(timeoutSeconds) || timeoutSeconds <= 0) {
    throw new RunnerProtocolError("Runner request timeoutSeconds must be a finite positive number.");
  }
  return {
    ...payload,
    instructions,
    outcomeContract,
    workingDirectory,
    timeoutSeconds,
  };
}

export function createAgentConfig(request, env = process.env) {
  const providerId = requiredEnv(env, "CLINE_SDK_PROVIDER_ID");
  const modelId = requiredEnv(env, "CLINE_SDK_MODEL_ID");
  const reasoningEffort = optionalEnv(env, "CLINE_SDK_REASONING_EFFORT");
  const apiKey = optionalEnv(env, "CLINE_SDK_API_KEY");
  const baseUrl = optionalEnv(env, "CLINE_SDK_BASE_URL");
  return removeUndefinedValues({
    providerId,
    modelId,
    reasoningEffort,
    apiKey,
    baseUrl,
    systemPrompt: request.outcomeContract,
  });
}

export function buildPrompt(request) {
  const context = Array.isArray(request.safeContext) ? request.safeContext : [];
  const artifacts = Array.isArray(request.artifactContext) ? request.artifactContext : [];
  return [
    request.instructions,
    "",
    "Outcome contract:",
    request.outcomeContract,
    "",
    `Working directory: ${request.workingDirectory}`,
    `Execution mode: ${request.executionMode ?? "read_only"}`,
    `Safe context: ${context.join("; ")}`,
    `Artifacts: ${artifacts.map((artifact) => `${artifact.path} (${artifact.digest})`).join("; ")}`,
  ].join("\n");
}

export async function runAgentProof({ AgentClass, request, env = process.env, emitRecord }) {
  const agent = new AgentClass(createAgentConfig(request, env));
  const unsubscribe = typeof agent.subscribe === "function" ? agent.subscribe((event) => emitSdkEvent(event, emitRecord)) : undefined;
  const abortController = new AbortController();
  const timeout = setTimeout(() => abortController.abort(), request.timeoutSeconds * 1000);
  try {
    const result = await agent.run(buildPrompt(request), { signal: abortController.signal });
    emitAgentDiagnostics(result, emitRecord);
    emitSafeDebugDiagnostics({ error: result?.error, env, emitRecord });
    emitRecord({ type: "terminal_result", status: normalizeAgentStatus(result?.status) });
  } catch (error) {
    const timedOut = abortController.signal.aborted;
    emitSafeDebugDiagnostics({ error, env, emitRecord });
    emitRecord({
      type: "blocker",
      code: timedOut ? "sdk_agent_timeout" : "sdk_agent_run_failed",
      summary: timedOut ? "Cline SDK Agent run exceeded the configured timeout." : "Cline SDK Agent run failed.",
      evidence: safeErrorEvidence(error),
    });
    emitRecord({ type: "terminal_result", status: timedOut ? "timed_out" : "failed" });
  } finally {
    clearTimeout(timeout);
    if (typeof unsubscribe === "function") {
      unsubscribe();
    }
  }
}

export function emitSdkEvent(event, emitRecord) {
  const eventType = typeof event?.type === "string" ? event.type : "unknown";
  if (eventType === "assistant-text-delta") {
    emitRecord({
      type: "event",
      evidenceType: "assistant_output",
      summary: "Cline SDK Agent emitted assistant text output.",
      sdkEventType: eventType,
    });
    return;
  }
  emitRecord({
    type: "event",
    evidenceType: "diagnostic",
    summary: "Cline SDK Agent emitted a diagnostic event.",
    sdkEventType: eventType,
  });
}

export function normalizeAgentStatus(status) {
  const normalized = SAFE_STATUS_MAP.get(status);
  if (!normalized) {
    throw new RunnerProtocolError("Cline SDK Agent returned an unsupported terminal status.", "unsupported_agent_status");
  }
  return normalized;
}

export function emitAgentDiagnostics(result, emitRecord) {
  emitDiagnosticIfPresent(emitRecord, "agent", result?.agentId, "Cline SDK Agent identifier");
  emitDiagnosticIfPresent(emitRecord, "run", result?.runId, "Cline SDK Agent run identifier");
  if (Number.isInteger(result?.iterations)) {
    emitRecord({ type: "diagnostic", kind: "iterations", value: String(result.iterations), summary: "Cline SDK Agent iteration count" });
  }
  if (result?.usage && typeof result.usage === "object") {
    emitRecord({ type: "diagnostic", kind: "usage", value: "present", summary: "Cline SDK Agent returned usage metadata" });
  }
}

export function emitSafeDebugDiagnostics({ error, env = process.env, emitRecord }) {
  if (env.CLINE_SDK_DEBUG_SAFE !== "1" || error === undefined || error === null) {
    return;
  }
  const errorName = typeof error?.name === "string" && error.name.trim() ? error.name : typeof error;
  emitRecord({
    type: "diagnostic",
    kind: "sdk_error_type",
    value: sanitizeDiagnosticText(errorName, env),
    summary: "Cline SDK Agent returned safe debug error type",
  });
  const message = error instanceof Error ? error.message : typeof error?.message === "string" ? error.message : String(error);
  if (message.trim()) {
    emitRecord({
      type: "diagnostic",
      kind: "sdk_error_message",
      value: sanitizeDiagnosticText(message, env),
      summary: "Cline SDK Agent returned safe debug error message",
    });
  }
}

export function sanitizeDiagnosticText(value, env = process.env) {
  let sanitized = String(value);
  for (const secretValue of knownSecretValues(env)) {
    sanitized = sanitized.split(secretValue).join(REDACTED_VALUE);
  }
  return sanitized
    .replace(/sk-[A-Za-z0-9_-]{8,}/g, REDACTED_VALUE)
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]{8,}/gi, `Bearer ${REDACTED_VALUE}`)
    .replace(/api[-_ ]?key\s*[:=]\s*[^\s,;]+/gi, `api_key=${REDACTED_VALUE}`);
}

export function jsonlEmitter(write = process.stdout.write.bind(process.stdout)) {
  let emittedTerminal = false;
  return (record) => {
    if (record.type === "terminal_result") {
      if (emittedTerminal) {
        throw new RunnerProtocolError("Runner attempted to emit more than one terminal result.", "duplicate_terminal_result");
      }
      emittedTerminal = true;
    }
    write(`${JSON.stringify(record)}\n`);
  };
}

export async function readStdin(stream = process.stdin) {
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf8");
}

function requiredString(payload, fieldName) {
  const value = payload[fieldName];
  if (typeof value !== "string" || !value.trim()) {
    throw new RunnerProtocolError(`Runner request field ${fieldName} must be a non-empty string.`);
  }
  return value;
}

function requiredEnv(env, fieldName) {
  const value = optionalEnv(env, fieldName);
  if (!value) {
    throw new RunnerProtocolError(`Missing required Cline SDK runner environment variable ${fieldName}.`, "missing_sdk_configuration");
  }
  return value;
}

function optionalEnv(env, fieldName) {
  const value = env[fieldName];
  return typeof value === "string" && value.trim() ? value : undefined;
}

function removeUndefinedValues(payload) {
  return Object.fromEntries(Object.entries(payload).filter(([, value]) => value !== undefined));
}

function knownSecretValues(env) {
  return [env.CLINE_SDK_API_KEY]
    .filter((value) => typeof value === "string" && value.length >= 4)
    .sort((left, right) => right.length - left.length);
}

function emitDiagnosticIfPresent(emitRecord, kind, value, summary) {
  if (typeof value === "string" && value.trim()) {
    emitRecord({ type: "diagnostic", kind, value, summary });
  }
}

function safeErrorEvidence(error) {
  if (error instanceof Error && error.name) {
    return `error_type=${error.name}`;
  }
  return "error_type=unknown";
}
