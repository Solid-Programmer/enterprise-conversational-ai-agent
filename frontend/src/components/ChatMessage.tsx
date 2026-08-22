import React from 'react';
import { CollapsibleSection } from './CollapsibleSection';
import { LoadingIndicator } from './LoadingIndicator';
import type { VisibleMessage } from './ChatResponse';

export const ChatMessage: React.FC<{ message: VisibleMessage }> = ({ message }) => {
  const response = message.response;
  const isSuccess = response?.status === 'success';

  return (
    <article className={`chat-message chat-message--${message.role}`}>
      <div className="message-label">{message.role === 'user' ? 'You' : 'Assistant'}</div>
      {message.pending ? <LoadingIndicator /> : <p className="message-content">{message.content}</p>}
      {!message.pending && isSuccess && response?.sql && (
        <CollapsibleSection title="SQL">
          <pre className="sql-block"><code>{response.sql}</code></pre>
        </CollapsibleSection>
      )}
      {!message.pending && isSuccess && response?.data != null && (
        <CollapsibleSection title="Structured data">
          <pre className="data-block">{JSON.stringify(response.data, null, 2)}</pre>
        </CollapsibleSection>
      )}
    </article>
  );
};
