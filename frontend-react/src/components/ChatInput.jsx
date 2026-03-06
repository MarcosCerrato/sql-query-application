import { useState, useRef, useEffect } from 'react';

export default function ChatInput({ onSend, disabled, prefill }) {
  const [value, setValue] = useState('');
  const textareaRef = useRef(null);

  useEffect(() => {
    if (prefill) {
      setValue(prefill);
      textareaRef.current?.focus();
    }
  }, [prefill]);

  const handleResize = (el) => {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
    if (textareaRef.current) {
      textareaRef.current.style.height = '48px';
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="border-t border-gray-200 px-4 py-4">
      <div className="max-w-2xl mx-auto flex gap-2 items-end">
        <textarea
          ref={textareaRef}
          rows={1}
          value={value}
          onChange={(e) => { setValue(e.target.value); handleResize(e.target); }}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about your data..."
          disabled={disabled}
          className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50 overflow-hidden"
          style={{ minHeight: '48px', height: '48px' }}
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="bg-blue-500 hover:bg-blue-600 disabled:opacity-40 text-white rounded-xl px-4 py-3 text-sm font-medium transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
}
