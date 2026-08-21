import React, { useState } from 'react';

interface ChatInputProps {
  onSend: (message: string) => Promise<void>;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, disabled }) => {
  const [input, setInput] = useState('');

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    const message = input.trim();
    if (!message || disabled) return;
    setInput('');
    await onSend(message);
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', gap: '0.5rem', marginTop: '1rem' }}>
      <input type="text" value={input} disabled={disabled} onChange={(event) => setInput(event.target.value)}
        placeholder="Ask a question about sales data..." style={{ flex: 1, padding: '0.75rem', borderRadius: 4, border: '1px solid #ccc' }} />
      <button type="submit" disabled={disabled} style={{ padding: '0.75rem 1.25rem' }}>{disabled ? 'Thinking…' : 'Send'}</button>
    </form>
  );
};
