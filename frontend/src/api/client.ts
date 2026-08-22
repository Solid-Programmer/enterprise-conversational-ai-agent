export interface ChatResponseData {
  status: 'success' | 'clarification_required' | 'requires_human_review' | 'error';
  route?: 'tool' | 'text_to_sql' | null;
  tool_name?: string | null;
  sql?: string | null;
  answer?: string | null;
  data: unknown;
  message?: string | null;
  metadata: Record<string, unknown>;
}

const CHAT_REQUEST_TIMEOUT_MS = 130_000;

export async function sendChatMessage(message: string, accessToken: string): Promise<ChatResponseData> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), CHAT_REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ message }),
      signal: controller.signal,
    });
    const payload = await response.json() as ChatResponseData;
    if (!response.ok) {
      throw new Error(payload.answer || payload.message || `API error: ${response.status}`);
    }
    return payload;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new Error('The request timed out. Please try again.');
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}
