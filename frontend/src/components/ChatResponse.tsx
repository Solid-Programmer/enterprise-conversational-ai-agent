import React from 'react';
import type { ChatResponseData } from '../api/client';

export interface VisibleMessage {
  role: 'user' | 'assistant';
  content: string;
  response?: ChatResponseData;
}

export const ChatResponse: React.FC<{ messages: VisibleMessage[] }> = ({ messages }) => (
  <div style={{ display: 'grid', gap: '0.75rem', marginTop: '1.5rem' }}>
    {messages.map((message, index) => (
      <article key={message.role + '-' + index} style={{ padding: '0.9rem', borderRadius: 6, background: message.role === 'user' ? '#e9f2ff' : '#f5f5f5' }}>
        <strong>{message.role === 'user' ? 'You' : 'Assistant'}</strong>
        <p style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>{message.content}</p>
          {message.response?.data != null && (
          <details style={{ marginTop: '0.75rem' }}>
            <summary>Structured data</summary>
            <pre style={{ overflowX: 'auto', fontSize: '0.8rem' }}>{JSON.stringify(message.response.data, null, 2)}</pre>
          </details>
        )}
      </article>
    ))}
  </div>
);
