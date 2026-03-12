// extensions/mirofish/src/backend-client.ts
/**
 * Lightweight HTTP client for MiroFish Flask backend.
 * Uses Node.js native fetch (available in Node 22+).
 */

const DEFAULT_BACKEND_URL = "http://localhost:5001";

function getBaseUrl(): string {
  return process.env.MIROFISH_URL || DEFAULT_BACKEND_URL;
}

interface ChatResponse {
  success: boolean;
  data?: {
    response: string;
    tool_calls?: unknown[];
    sources?: unknown[];
  };
  error?: string;
}

interface InterviewResponse {
  success: boolean;
  data?: {
    response: string;
    agent_id: number;
    [key: string]: unknown;
  };
  error?: string;
}

interface ReportResponse {
  success: boolean;
  data?: {
    report_id: string;
    simulation_id: string;
    status: string;
    markdown_content: string;
    outline?: unknown;
    created_at?: string;
    completed_at?: string;
  };
  error?: string;
  has_report?: boolean;
}

/**
 * Chat with the Report Agent about a completed simulation.
 */
export async function chatWithAgent(
  simId: string,
  message: string,
  chatHistory: { role: string; content: string }[] = [],
): Promise<ChatResponse> {
  const url = `${getBaseUrl()}/api/report/chat`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      simulation_id: simId,
      message,
      chat_history: chatHistory,
    }),
  });
  if (!res.ok) {
    return { success: false, error: `Backend HTTP ${res.status}` };
  }
  return (await res.json()) as ChatResponse;
}

/**
 * Interview a specific simulation agent.
 */
export async function interviewAgent(
  simId: string,
  agentId: number,
  question: string,
): Promise<InterviewResponse> {
  const url = `${getBaseUrl()}/api/simulation/interview`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      simulation_id: simId,
      agent_id: agentId,
      prompt: question,
    }),
  });
  if (!res.ok) {
    return { success: false, error: `Backend HTTP ${res.status}` };
  }
  return (await res.json()) as InterviewResponse;
}

/**
 * Get report by simulation ID.
 */
export async function getReport(simId: string): Promise<ReportResponse> {
  const url = `${getBaseUrl()}/api/report/by-simulation/${encodeURIComponent(simId)}`;
  const res = await fetch(url);
  if (!res.ok) {
    return { success: false, error: `Backend HTTP ${res.status}` };
  }
  return (await res.json()) as ReportResponse;
}

/**
 * Get report summary (truncated markdown for chat-friendly display).
 */
export async function getReportSummary(
  simId: string,
  maxChars: number = 2000,
): Promise<{ summary: string; reportId: string } | null> {
  const report = await getReport(simId);
  if (!report.success || !report.data) return null;

  const md = report.data.markdown_content || "";
  const summary = md.length > maxChars
    ? md.slice(0, maxChars) + "\n\n...(報告已截斷，完整內容請使用 Canvas Dashboard)"
    : md;

  return { summary, reportId: report.data.report_id };
}
