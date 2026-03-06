import SQLBlock from './SQLBlock';
import ResultsTable from './ResultsTable';

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user';

  if (message.type === 'loading') {
    return (
      <div className="flex justify-start mb-4">
        <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
          <div className="flex gap-1 items-center h-5">
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]"></span>
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]"></span>
            <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]"></span>
          </div>
        </div>
      </div>
    );
  }

  if (message.type === 'error') {
    return (
      <div className="flex justify-start mb-4">
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="flex justify-end mb-4">
        <div className="bg-blue-500 text-white rounded-2xl rounded-tr-sm px-4 py-3 max-w-xl text-sm">
          {message.content}
        </div>
      </div>
    );
  }

  if (message.type === 'answer') {
    return (
      <div className="flex justify-start mb-4">
        <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl w-full text-sm">
          <p className="text-gray-800 whitespace-pre-wrap">{message.content}</p>
          {message.sql && (
            <div className="mt-3">
              <SQLBlock sql={message.sql} />
            </div>
          )}
          {message.rows && <ResultsTable rows={message.rows} />}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 max-w-xl w-full text-sm">
        {message.type === 'sql' ? (
          <SQLBlock sql={message.content} />
        ) : (
          <span>{message.content}</span>
        )}
      </div>
    </div>
  );
}
