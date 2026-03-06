import { useState } from 'react';
import ChatWindow from './components/ChatWindow';
import ChatInput from './components/ChatInput';

const EXAMPLES = [
  'What are the top 3 products by total revenue?',
  'What is the average revenue per waiter?',
  'Which day of the week had the highest total revenue?',
];

export default function App() {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [prefill, setPrefill] = useState('');

  const handleSend = async (question) => {
    setPrefill('');
    const userMsg = { id: Date.now(), role: 'user', type: 'text', content: question };
    const loadingId = Date.now() + 1;
    const loadingMsg = { id: loadingId, role: 'assistant', type: 'loading' };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setLoading(true);

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      const { answer, sql, rows } = await res.json();

      const assistantMsg = {
        id: Date.now(),
        role: 'assistant',
        type: 'answer',
        content: answer,
        sql,
        rows,
      };

      setMessages((prev) =>
        prev.map((m) => (m.id === loadingId ? assistantMsg : m))
      );
    } catch (err) {
      const errorMsg = {
        id: Date.now(),
        role: 'assistant',
        type: 'error',
        content: err.message || 'Failed to connect to the model service.',
      };
      setMessages((prev) =>
        prev.map((m) => (m.id === loadingId ? errorMsg : m))
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-row h-screen">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 bg-gray-900 text-white flex flex-col px-5 py-6 gap-6">
        <div>
          <h1 className="text-lg font-semibold">SQL Query Assistant</h1>
          <p className="text-xs text-gray-400 mt-1">Ask in natural language, get results</p>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">Examples</p>
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              onClick={() => setPrefill(ex)}
              className="text-left text-sm text-gray-300 hover:text-white hover:bg-gray-800 rounded-md px-3 py-2 transition-colors"
            >
              {ex}
            </button>
          ))}
        </div>

        {messages.length > 0 && (
          <div className="mt-auto">
            <button
              onClick={() => setMessages([])}
              className="w-full flex items-center gap-2 text-sm text-gray-400 hover:text-white hover:bg-gray-800 rounded-md px-3 py-2 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
              </svg>
              New conversation
            </button>
          </div>
        )}
      </aside>

      {/* Chat column */}
      <div className="flex flex-col flex-1 min-w-0 bg-white">
        <ChatWindow messages={messages} />
        <ChatInput onSend={handleSend} disabled={loading} prefill={prefill} />
      </div>
    </div>
  );
}
