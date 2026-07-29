import assert from "node:assert/strict";
import test from "node:test";

import {
  createAgentConfig,
  emitSdkEvent,
  emitSafeDebugDiagnostics,
  jsonlEmitter,
  normalizeAgentStatus,
  parseRunnerRequest,
  runAgentProof,
  RunnerProtocolError,
  sanitizeDiagnosticText,
} from "./runner-lib.mjs";

const BASE_REQUEST = {
  schemaVersion: 1,
  role: "implementation",
  instructions: "Implement the slice.",
  outcomeContract: "Return a terminal outcome.",
  timeoutSeconds: 5,
  workingDirectory: "/repo",
  requiredSkills: [],
  artifactContext: [],
  executionMode: "read_only",
  safeContext: ["slice=task-4a"],
};

test("parseRunnerRequest accepts the SDK runner protocol payload", () => {
  const request = parseRunnerRequest(JSON.stringify(BASE_REQUEST));

  assert.equal(request.instructions, "Implement the slice.");
  assert.equal(request.outcomeContract, "Return a terminal outcome.");
  assert.equal(request.timeoutSeconds, 5);
});

test("parseRunnerRequest rejects malformed protocol payloads", () => {
  assert.throws(() => parseRunnerRequest("not-json"), RunnerProtocolError);
  assert.throws(() => parseRunnerRequest(JSON.stringify({ ...BASE_REQUEST, timeoutSeconds: 0 })), /timeoutSeconds/);
});

test("emitSdkEvent normalizes assistant text deltas as assistant output evidence", () => {
  const records = [];

  emitSdkEvent({ type: "assistant-text-delta", text: "secret raw text is intentionally ignored" }, (record) => records.push(record));

  assert.deepEqual(records, [
    {
      type: "event",
      evidenceType: "assistant_output",
      summary: "Cline SDK Agent emitted assistant text output.",
      sdkEventType: "assistant-text-delta",
    },
  ]);
});

test("normalizeAgentStatus accepts only documented AgentRunResult statuses", () => {
  assert.equal(normalizeAgentStatus("completed"), "completed");
  assert.equal(normalizeAgentStatus("aborted"), "aborted");
  assert.equal(normalizeAgentStatus("failed"), "failed");
  assert.throws(() => normalizeAgentStatus("max_iterations"), /unsupported terminal status/);
});

test("createAgentConfig maps provider model and reasoning effort from environment", () => {
  const config = createAgentConfig(BASE_REQUEST, {
    CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
    CLINE_SDK_MODEL_ID: "gpt-5.5",
    CLINE_SDK_REASONING_EFFORT: "medium",
  });

  assert.equal(config.providerId, "openai-codex-cli");
  assert.equal(config.modelId, "gpt-5.5");
  assert.equal(config.reasoningEffort, "medium");
  assert.equal(config.systemPrompt, BASE_REQUEST.outcomeContract);
});

test("jsonlEmitter prevents duplicate terminal results", () => {
  const lines = [];
  const emit = jsonlEmitter((line) => lines.push(line));

  emit({ type: "terminal_result", status: "completed" });

  assert.throws(() => emit({ type: "terminal_result", status: "failed" }), /more than one terminal/);
  assert.equal(lines.length, 1);
});

test("runAgentProof uses Agent subscribe and run and emits one terminal result", async () => {
  const records = [];
  class FakeAgent {
    constructor(config) {
      this.config = config;
    }

    subscribe(listener) {
      listener({ type: "assistant-text-delta", text: "not emitted" });
      return () => undefined;
    }

    async run(prompt) {
      assert.match(prompt, /Implement the slice/);
      assert.equal(this.config.providerId, "openai-codex-cli");
      assert.equal(this.config.modelId, "gpt-5.5");
      assert.equal(this.config.reasoningEffort, "medium");
      return {
        status: "completed",
        agentId: "agent-1",
        runId: "run-1",
        iterations: 2,
        usage: { totalTokens: 10 },
      };
    }
  }

  await runAgentProof({
    AgentClass: FakeAgent,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
      CLINE_SDK_REASONING_EFFORT: "medium",
      CLINE_SDK_API_KEY: "secret",
    },
    emitRecord: (record) => records.push(record),
  });

  assert.equal(records.filter((record) => record.type === "terminal_result").length, 1);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "completed" });
  assert.equal(records.some((record) => JSON.stringify(record).includes("secret")), false);
  assert.equal(records.some((record) => record.kind === "run" && record.value === "run-1"), true);
});

test("runAgentProof omits SDK error details unless safe debug is enabled", async () => {
  const records = [];
  class FailingAgent {
    subscribe() {
      return () => undefined;
    }

    async run() {
      return {
        status: "failed",
        error: new Error("provider rejected secret sk-test-secret-token"),
      };
    }
  }

  await runAgentProof({
    AgentClass: FailingAgent,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
    },
    emitRecord: (record) => records.push(record),
  });

  assert.equal(records.some((record) => record.kind === "sdk_error_message"), false);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "failed" });
});

test("runAgentProof emits redacted SDK error details when safe debug is enabled", async () => {
  const records = [];
  class FailingAgent {
    subscribe() {
      return () => undefined;
    }

    async run() {
      return {
        status: "failed",
        error: new Error("provider rejected secret-token and sk-test-secret-token"),
      };
    }
  }

  await runAgentProof({
    AgentClass: FailingAgent,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
      CLINE_SDK_API_KEY: "secret-token",
      CLINE_SDK_DEBUG_SAFE: "1",
    },
    emitRecord: (record) => records.push(record),
  });

  const debugMessage = records.find((record) => record.kind === "sdk_error_message");

  assert.equal(records.some((record) => JSON.stringify(record).includes("secret-token")), false);
  assert.equal(records.some((record) => JSON.stringify(record).includes("sk-test-secret-token")), false);
  assert.match(debugMessage.value, /\[REDACTED\]/);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "failed" });
});

test("emitSafeDebugDiagnostics redacts thrown SDK errors", () => {
  const records = [];

  emitSafeDebugDiagnostics({
    error: new TypeError("Bearer abcdefghijklmnop failed with api_key=plain-secret"),
    env: { CLINE_SDK_DEBUG_SAFE: "1", CLINE_SDK_API_KEY: "plain-secret" },
    emitRecord: (record) => records.push(record),
  });

  assert.equal(records[0].kind, "sdk_error_type");
  assert.equal(records[0].value, "TypeError");
  assert.equal(records[1].kind, "sdk_error_message");
  assert.equal(records[1].value.includes("abcdefghijklmnop"), false);
  assert.equal(records[1].value.includes("plain-secret"), false);
});

test("sanitizeDiagnosticText redacts known secret patterns", () => {
  const sanitized = sanitizeDiagnosticText("sk-abcdefghijklmnop Bearer abcdefghijklmnop api key: abc secret-token", {
    CLINE_SDK_API_KEY: "secret-token",
  });

  assert.equal(sanitized.includes("sk-abcdefghijklmnop"), false);
  assert.equal(sanitized.includes("Bearer abcdefghijklmnop"), false);
  assert.equal(sanitized.includes("secret-token"), false);
});
