import React from 'react';

export const LoadingIndicator: React.FC = () => (
  <div className="loading-indicator" aria-live="polite" aria-label="Thinking">
    <span className="loading-dot" />
    Thinking...
  </div>
);
