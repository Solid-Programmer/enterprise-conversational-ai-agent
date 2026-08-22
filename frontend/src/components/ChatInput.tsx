import React, { useState } from 'react';

interface ChatInputProps {
  onSend: (message: string) => Promise<void>;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, disabled }) => {
  const [input, setInput] = useState('');

  const submit = async () => {
    const message = input.trim();
    if (!message || disabled) return;
    setInput('');
    await onSend(message);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    await submit();
  };

  const handleKeyDown = async (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      await submit();
    }
  };

  return (
    <form className="chat-composer" onSubmit={handleSubmit}>
      <textarea
        value={input}
        disabled={disabled}
        onChange={(event) => setInput(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Ask a question about sales data..."
        rows={1}
      />
      <button type="submit" disabled={disabled || !input.trim()}>{disabled ? 'Thinking...' : 'Send'}</button>
    </form>
  );
};
