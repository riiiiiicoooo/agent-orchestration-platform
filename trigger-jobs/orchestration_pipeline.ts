/**
 * Trigger.dev Job — Long-running agent orchestration pipeline.
 *
 * Handles complex multi-agent tasks that take 30s-5min to complete.
 * Provides checkpointing between stages for durability and resume.
 */

import { task, wait } from "@trigger.dev/sdk/v3";

export const orchestrationPipeline = task({
  id: "orchestration-pipeline",
  maxDuration: 300, // 5 minutes max

  run: async (payload: {
    taskId: string;
    sessionId: string;
    userId: string;
    input: string;
    agents: string[];
  }) => {
    const { taskId, sessionId, userId, input, agents } = payload;

    // Stage 1: Intent classification
    const intent = await classifyIntent(input);
    await wait.for({ seconds: 0.1 }); // Checkpoint

    // Stage 2: Context retrieval
    const context = await retrieveContext(sessionId, intent);
    await wait.for({ seconds: 0.1 }); // Checkpoint

    // Stage 3: Agent execution (may involve multiple agents)
    const agentResults: Record<string, any> = {};

    for (const agentId of agents) {
      try {
        const result = await executeAgent(agentId, input, context);
        agentResults[agentId] = result;
        await wait.for({ seconds: 0.1 }); // Checkpoint after each agent
      } catch (error) {
        agentResults[agentId] = { status: "failed", error: String(error) };
      }
    }

    // Stage 4: Guardrail check
    const guardrailResult = await checkGuardrails(agentResults);

    // Stage 5: Store results
    await storeResults(taskId, sessionId, agentResults, guardrailResult);

    return {
      taskId,
      success: guardrailResult.passed,
      agentResults,
      guardrailResult,
    };
  },
});

// Stub functions — connected to FastAPI backend in production
async function classifyIntent(input: string) {
  const response = await fetch("http://api:8000/internal/classify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input }),
  });
  return response.json();
}

async function retrieveContext(sessionId: string, intent: any) {
  const response = await fetch(`http://api:8000/internal/context/${sessionId}`);
  return response.json();
}

async function executeAgent(agentId: string, input: string, context: any) {
  const response = await fetch(`http://api:8000/internal/agents/${agentId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ input, context }),
  });
  return response.json();
}

async function checkGuardrails(agentResults: Record<string, any>) {
  const response = await fetch("http://api:8000/internal/guardrails/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ agentResults }),
  });
  return response.json();
}

async function storeResults(
  taskId: string,
  sessionId: string,
  agentResults: Record<string, any>,
  guardrailResult: any
) {
  await fetch("http://api:8000/internal/results", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ taskId, sessionId, agentResults, guardrailResult }),
  });
}
