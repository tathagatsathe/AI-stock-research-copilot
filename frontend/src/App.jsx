import React, { useState, useEffect } from 'react';

function App() {
  const [ticker, setTicker] = useState('');
  const [analysis, setAnalysis] = useState(null);
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await fetch('/api/health');
        const data = await response.json();
        setHealth(data);
      } catch (err) {
        console.error(err);
      }
    };
    fetchHealth();
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setAnalysis(null);

    if (!ticker) {
      setError('Please enter a stock ticker.');
      return;
    }

    try {
      const response = await fetch(`/api/stocks/analyze/${ticker}`);
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch analysis.');
      }
      const data = await response.json();
      setAnalysis(data);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 flex flex-col items-center justify-center">
      <div className="bg-white shadow-md rounded-lg p-8 max-w-2xl w-full">
        <h1 className="text-2xl font-bold mb-4 text-center">AI Stock Analysis</h1>
        {health && <p className="text-sm text-gray-500 text-center mb-4">Service: {health.service} - Status: {health.status}</p>}
        <form onSubmit={handleSubmit} className="mb-4">
          <div className="flex">
            <input
              type="text"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              placeholder="Enter stock ticker (e.g., AAPL)"
              className="flex-grow p-2 border border-gray-300 rounded-l-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              className="bg-blue-500 text-white p-2 rounded-r-md hover:bg-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              Analyze
            </button>
          </div>
        </form>
        {error && <p className="text-red-500 text-center">{error}</p>}
        {analysis && (
          <div className="mt-4">
            <h2 className="text-xl font-bold mb-2">{analysis.ticker} Analysis</h2>
            <div className="grid grid-cols-2 gap-4 mb-4">
                <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="font-bold">Current Price</h3>
                    <p>${analysis.current_price.toFixed(2)}</p>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="font-bold">50-Day SMA</h3>
                    <p>${analysis.sma_50.toFixed(2)}</p>
                </div>
                <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="font-bold">RSI</h3>
                    <p>{analysis.rsi.toFixed(2)}</p>
                </div>
            </div>
            <div>
              <h3 className="text-lg font-bold mb-2">News Analysis</h3>
              <p><span className="font-bold">Overall Sentiment:</span> {analysis.news_analysis.overall_sentiment}</p>
              <div className="mt-2">
                <h4 className="font-bold">Articles:</h4>
                <ul className="list-disc list-inside">
                  {analysis.news_analysis.articles.map((article, index) => (
                    <li key={index} className="mb-2">
                      <p className="font-semibold">{article.title}</p>
                      <p className="text-sm text-gray-600">{article.summary}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
