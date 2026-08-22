import React, { useEffect, useRef, useState } from 'react';
import { useAuth0 } from '@auth0/auth0-react';
import { sendChatMessage } from './api/client';
import { ChatInput } from './components/ChatInput';
import { ChatResponse, type VisibleMessage } from './components/ChatResponse';

const messageId = () => crypto.randomUUID();

export const App: React.FC = () => {
  const [messages, setMessages] = useState<VisibleMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const historyRef = useRef<HTMLElement>(null);
  const { isLoading: isAuthLoading, isAuthenticated, error: authError, user, loginWithRedirect, logout, getAccessTokenSilently } = useAuth0();

  useEffect(() => {
    historyRef.current?.scrollTo({ top: historyRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const send = async (message: string) => {
    const pendingId = messageId();
    setMessages((items) => [
      ...items,
      { id: messageId(), role: 'user', content: message },
      { id: pendingId, role: 'assistant', content: '', pending: true },
    ]);
    setLoading(true);
    try {
      const accessToken = await getAccessTokenSilently();
      const response = await sendChatMessage(message, accessToken);
      const content = response.answer
        || response.message
        || (response.status === 'success' ? 'The query completed successfully.' : 'No response was generated.');
      setMessages((items) => items.map((item) => (
        item.id === pendingId ? { ...item, content, pending: false, response } : item
      )));
    } catch (requestError) {
      const detail = requestError instanceof Error ? requestError.message : 'Unable to send the message.';
      setMessages((items) => items.map((item) => (
        item.id === pendingId
          ? { ...item, content: `I couldn't complete that request. ${detail}`, pending: false }
          : item
      )));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="header-content">
          <h1>Enterprise Conversational AI Agent</h1>
          <div className="auth-actions">
            {isAuthLoading && <span className="auth-status">Checking access...</span>}
            {!isAuthLoading && authError && <span className="auth-error">Authentication unavailable</span>}
            {!isAuthLoading && !isAuthenticated && (
              <>
                <button className="secondary-button" onClick={() => loginWithRedirect({ authorizationParams: { screen_hint: 'signup' } })}>Sign up</button>
                <button className="primary-button" onClick={() => loginWithRedirect()}>Log in</button>
              </>
            )}
            {!isAuthLoading && isAuthenticated && (
              <>
                <span className="auth-status">{user?.name || user?.email || 'Authenticated user'}</span>
                <button className="secondary-button" onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}>Log out</button>
              </>
            )}
          </div>
        </div>
      </header>
      <main ref={historyRef} className="chat-history" aria-label="Conversation history">
        <div className="conversation-column"><ChatResponse messages={messages} /></div>
      </main>
      <footer className="composer-area"><div className="conversation-column"><ChatInput onSend={send} disabled={loading || !isAuthenticated} /></div></footer>
    </div>
  );
};

export default App;
