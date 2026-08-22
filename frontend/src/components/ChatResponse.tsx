import React from 'react';
import type { ChatResponseData } from '../api/client';
import { ChatMessage } from './ChatMessage';

export interface VisibleMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  pending?: boolean;
  response?: ChatResponseData;
}

export const ChatResponse: React.FC<{ messages: VisibleMessage[] }> = ({ messages }) => (
  <div className="message-list">
    {messages.map((message) => <ChatMessage key={message.id} message={message} />)}
  </div>
);
