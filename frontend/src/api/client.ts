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

export async function sendChatMessage(message: string, accessToken: string): Promise<ChatResponseData> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    throw new Error('API error: ' + response.statusText);
  }
  return response.json() as Promise<ChatResponseData>;
}
