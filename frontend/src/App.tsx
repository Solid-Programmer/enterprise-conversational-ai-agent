import React, { useState } from 'react';
import { sendChatMessage } from './api/client';
import { ChatInput } from './components/ChatInput';
import { ChatResponse, type VisibleMessage } from './components/ChatResponse';

export const App: React.FC = () => {
  const [messages, setMessages] = useState<VisibleMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const send = async (message: string) => {
    setMessages((items) => [...items, { role: 'user', content: message }]);
    setLoading(true);
    setError(null);
    try {
      const response = await sendChatMessage(message);
      setMessages((items) => [...items, {
        role: 'assistant',
        content: response.message || (response.status === 'success' ? 'Query completed.' : 'No response was generated.'),
        response,
      }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : 'Unable to send the message.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ fontFamily: 'system-ui, sans-serif', padding: '2rem', maxWidth: 900, margin: '0 auto' }}>
      <h1>Enterprise Conversational AI Agent</h1>
      <ChatResponse messages={messages} />
      {error && <p style={{ color: '#b00020' }}>{error}</p>}
      <ChatInput onSend={send} disabled={loading} />
    </main>
  );
};

export default App;
