export default function ResultsTable({ rows }) {
  if (!rows || rows.length === 0) return null;

  const columns = Object.keys(rows[0]);

  return (
    <div className="mt-3">
      <p className="text-xs text-gray-500 mb-1">{rows.length} result{rows.length !== 1 ? 's' : ''} found</p>
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="text-sm min-w-full">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              {columns.map((col) => (
                <th key={col} className="px-3 py-2 text-left font-medium whitespace-nowrap border-b border-gray-200">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                {columns.map((col) => (
                  <td key={col} className="px-3 py-2 text-gray-700 whitespace-nowrap border-b border-gray-100">
                    {row[col] === null || row[col] === undefined ? <span className="text-gray-400 italic">null</span> : String(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
