import { useState } from 'react';

export default function SQLBlock({ sql }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(sql).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <div className="rounded-lg overflow-hidden border border-gray-200 mt-1">
      <div className="flex items-center justify-between px-4 py-2 bg-gray-800 text-gray-300 text-xs">
        <span>SQL</span>
        <button
          onClick={handleCopy}
          className="hover:text-white transition-colors"
        >
          {copied ? 'Copied!' : 'Copy SQL'}
        </button>
      </div>
      <pre className="bg-gray-900 text-green-400 p-4 text-sm overflow-x-auto font-mono whitespace-pre-wrap">
        {sql}
      </pre>
    </div>
  );
}
