import assert from "node:assert/strict";
import test from "node:test";

import {
  clineCoreModeForExecutionMode,
  createClineCoreOptions,
  createClineCoreStartInput,
  createFailClosedToolPolicies,
  createProbeCapabilities,
  createAgentConfig,
  emitClineCoreEvent,
  emitSdkEvent,
  emitSafeDebugDiagnostics,
  jsonlEmitter,
  normalizeAgentStatus,
  parseRunnerRequest,
  runClineCoreProbe,
  runClineCoreModeSwitchProbe,
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

test("createClineCoreStartInput supplies safe workspace and fail-closed tool policy configuration", () => {
  const startInput = createClineCoreStartInput(BASE_REQUEST, {
    CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
    CLINE_SDK_MODEL_ID: "gpt-5.5",
    CLINE_SDK_REASONING_EFFORT: "medium",
  });

  assert.equal(startInput.config.providerId, "openai-codex-cli");
  assert.equal(startInput.config.modelId, "gpt-5.5");
  assert.equal(startInput.config.cwd, "/repo");
  assert.equal(startInput.config.workspaceRoot, "/repo");
  assert.equal(startInput.config.mode, "plan");
  assert.equal(startInput.config.enableTools, false);
  assert.equal(startInput.config.enableSpawnAgent, false);
  assert.equal(startInput.config.enableAgentTeams, false);
  assert.equal(startInput.config.checkpoint.enabled, false);
  assert.equal(startInput.config.toolPolicies.bash.autoApprove, false);
  assert.equal(startInput.config.toolPolicies.editor.enabled, false);
  assert.equal(startInput.toolPolicies.applyPatch.autoApprove, false);
});

test("createClineCoreStartInput maps write-capable execution to explicit SDK act mode", () => {
  const startInput = createClineCoreStartInput(
    { ...BASE_REQUEST, executionMode: "write_capable" },
    {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
    },
  );

  assert.equal(startInput.config.mode, "act");
});

test("clineCoreModeForExecutionMode fails closed for unsupported execution modes", () => {
  assert.equal(clineCoreModeForExecutionMode("read_only"), "plan");
  assert.equal(clineCoreModeForExecutionMode("write_capable"), "act");
  assert.throws(() => clineCoreModeForExecutionMode("yolo"), /executionMode is unsupported/);
});

test("createClineCoreOptions installs local backend and dynamic approval capability", async () => {
  const records = [];
  const options = createClineCoreOptions((record) => records.push(record));

  const approval = await options.capabilities.requestToolApproval({ toolName: "bash" });

  assert.equal(options.clientName, "cline-sdlc-clinecore-probe");
  assert.equal(options.backendMode, "local");
  assert.equal(options.toolPolicies.bash.enabled, false);
  assert.deepEqual(approval, { approved: false, reason: "cline-sdlc ClineCore probe denies tool execution by default" });
  assert.equal(records.some((record) => record.evidenceType === "approval_request"), true);
  assert.equal(records.some((record) => record.kind === "tool" && record.value === "bash"), true);
});

test("createFailClosedToolPolicies returns independent policy objects", () => {
  const first = createFailClosedToolPolicies();
  const second = createFailClosedToolPolicies();

  first.bash.enabled = true;

  assert.equal(second.bash.enabled, false);
});

test("createProbeCapabilities records approval requests and denies by default", async () => {
  const records = [];
  const capabilities = createProbeCapabilities((record) => records.push(record));

  const decision = await capabilities.requestToolApproval({ toolName: "editor" });

  assert.equal(decision.approved, false);
  assert.equal(records[0].evidenceType, "approval_request");
  assert.equal(records[1].kind, "tool");
  assert.equal(records[1].value, "editor");
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

test("runClineCoreProbe uses ClineCore create subscribe and start and emits session diagnostics", async () => {
  const records = [];
  const calls = [];
  class FakeClineCore {
    static async create(options) {
      calls.push(["create", options]);
      return new FakeClineCore();
    }

    subscribe(listener) {
      calls.push(["subscribe"]);
      listener({ type: "status", payload: { sessionId: "session-1", status: "running" } });
      return () => calls.push(["unsubscribe"]);
    }

    async start(input) {
      calls.push(["start", input]);
      assert.equal(input.config.cwd, "/repo");
      assert.equal(input.config.workspaceRoot, "/repo");
      assert.equal(input.config.mode, "plan");
      assert.equal(input.config.enableTools, false);
      assert.equal(input.config.toolPolicies.bash.autoApprove, false);
      assert.equal(input.capabilities, calls[0][1].capabilities);
      return {
        sessionId: "session-1",
        manifestPath: ".cline/sessions/session-1/manifest.json",
        messagesPath: ".cline/sessions/session-1/messages.json",
        result: { status: "completed" },
      };
    }

    async dispose(reason) {
      calls.push(["dispose", reason]);
    }
  }

  await runClineCoreProbe({
    ClineCoreClass: FakeClineCore,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
    },
    emitRecord: (record) => records.push(record),
  });

  assert.equal(calls.map((call) => call[0]).includes("create"), true);
  assert.equal(calls.map((call) => call[0]).includes("subscribe"), true);
  assert.equal(calls.map((call) => call[0]).includes("start"), true);
  assert.equal(calls.map((call) => call[0]).includes("dispose"), true);
  assert.equal(records.some((record) => record.kind === "manifest"), true);
  assert.equal(records.some((record) => record.kind === "messages"), true);
  assert.equal(records.some((record) => record.kind === "plan_act_mode" && record.value === "plan"), true);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "completed" });
});

test("runClineCoreProbe reports missing ClineCore as blocked capability", async () => {
  const records = [];

  await runClineCoreProbe({
    ClineCoreClass: undefined,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
    },
    emitRecord: (record) => records.push(record),
  });

  assert.equal(records.some((record) => record.code === "clinecore_missing"), true);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "failed" });
});

test("runClineCoreModeSwitchProbe starts in plan mode then sends act mode to same session", async () => {
  const records = [];
  const calls = [];
  class FakeClineCore {
    static async create(options) {
      calls.push(["create", options]);
      return new FakeClineCore();
    }

    async start(input) {
      calls.push(["start", input]);
      assert.equal(input.config.mode, "plan");
      assert.equal(input.config.enableTools, false);
      assert.equal(input.config.toolPolicies.bash.autoApprove, false);
      return {
        sessionId: "session-1",
        manifestPath: ".cline/sessions/session-1/manifest.json",
        messagesPath: ".cline/sessions/session-1/messages.json",
      };
    }

    async send(input) {
      calls.push(["send", input]);
      assert.deepEqual(input, {
        sessionId: "session-1",
        prompt: "Continue this same bounded session in Act mode only if explicitly authorized by the caller.",
        mode: "act",
        delivery: "queue",
      });
    }

    async dispose(reason) {
      calls.push(["dispose", reason]);
    }
  }

  await runClineCoreModeSwitchProbe({
    ClineCoreClass: FakeClineCore,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
    },
    emitRecord: (record) => records.push(record),
  });

  assert.deepEqual(calls.map((call) => call[0]), ["create", "start", "send", "dispose"]);
  assert.equal(records.some((record) => record.kind === "plan_act_start_mode" && record.value === "plan"), true);
  assert.equal(records.some((record) => record.kind === "plan_act_send_mode" && record.value === "act"), true);
  assert.equal(records.some((record) => record.kind === "same_session_mode_switch" && record.value === "true"), true);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "completed" });
});

test("runClineCoreModeSwitchProbe blocks when send is unavailable", async () => {
  const records = [];
  class FakeClineCoreWithoutSend {
    static async create() {
      return new FakeClineCoreWithoutSend();
    }

    async start() {
      return { sessionId: "session-1" };
    }
  }

  await runClineCoreModeSwitchProbe({
    ClineCoreClass: FakeClineCoreWithoutSend,
    request: BASE_REQUEST,
    env: {
      CLINE_SDK_PROVIDER_ID: "openai-codex-cli",
      CLINE_SDK_MODEL_ID: "gpt-5.5",
    },
    emitRecord: (record) => records.push(record),
  });

  assert.equal(records.some((record) => record.code === "clinecore_send_missing"), true);
  assert.deepEqual(records.at(-1), { type: "terminal_result", status: "failed" });
});

test("emitClineCoreEvent maps session events to diagnostic lifecycle and tool evidence", () => {
  const records = [];

  emitClineCoreEvent({ type: "hook", payload: { sessionId: "session-1", hookEventName: "tool_call" } }, (record) => records.push(record));
  emitClineCoreEvent({ type: "hook", payload: { sessionId: "session-1", hookEventName: "tool_result" } }, (record) => records.push(record));
  emitClineCoreEvent({ type: "ended", payload: { sessionId: "session-1", reason: "completed" } }, (record) => records.push(record));
  emitClineCoreEvent({ type: "future-event", payload: { sessionId: "session-1" } }, (record) => records.push(record));

  assert.equal(records[0].evidenceType, "tool_request");
  assert.equal(records[2].evidenceType, "tool_result");
  assert.equal(records[4].evidenceType, "lifecycle");
  assert.equal(records[6].evidenceType, "diagnostic");
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
