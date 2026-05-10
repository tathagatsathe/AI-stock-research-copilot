import React, { useState, useEffect } from 'react';

function App() {
  const [universe, setUniverse] = useState([]);
  const [selectedStock, setSelectedStock] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [loadingUniverse, setLoadingUniverse] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const fetchUniverse = async () => {
      setLoadingUniverse(true);
      setError('');
      try {
        const response = await fetch('/api/stocks/universe');
        if (!response.ok) {
          throw new Error('Failed to fetch stock universe.');
        }
        const data = await response.json();
        setUniverse(data.stocks || []);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoadingUniverse(false);
      }
    };
    fetchUniverse();
  }, []);

  const handleAnalyze = async (ticker) => {
    setSelectedStock(ticker);
    setLoadingAnalysis(true);
    setAnalysis(null);
    setError('');
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
    } finally {
      setLoadingAnalysis(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white flex flex-col items-center p-4">
      <div className="w-full max-w-7xl">
        <h1 className="text-3xl font-bold mb-4 text-center">AI Stock Analysis</h1>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-1 bg-gray-800 rounded-lg p-4 overflow-y-auto h-[calc(100vh-120px)]">
            <h2 className="text-xl font-bold mb-4">Stock Universe</h2>
            {loadingUniverse && <p className="text-center">Loading stocks...</p>}
            {error && !loadingUniverse && <p className="text-red-500 text-center">{error}</p>}
            <ul className="space-y-2">
              {universe.map((stock) => (
                <li key={stock.ticker} className={`p-2 rounded-md cursor-pointer ${selectedStock === stock.ticker ? 'bg-blue-600' : 'bg-gray-700 hover:bg-gray-600'}`} onClick={() => handleAnalyze(stock.ticker)}>
                  <div className="flex justify-between items-center">
                    <span className="font-bold">{stock.ticker}</span>
                    <span className="text-sm">{stock.name}</span>
                  </div>
                </li>
              ))}
            </ul>
          </div>
          
          <div className="md:col-span-2 bg-gray-800 rounded-lg p-4 overflow-y-auto h-[calc(100vh-120px)]">
            <h2 className="text-xl font-bold mb-4">Analysis</h2>
            {loadingAnalysis && <p className="text-center">Loading analysis...</p>}
            {error && !loadingAnalysis && <p className="text-red-500 text-center">{error}</p>}
            {!analysis && !loadingAnalysis && <p className="text-center text-gray-400">Select a stock to analyze.</p>}

            {analysis && (
              <div className="space-y-6">
                <div className="p-4 bg-gray-700 rounded-lg">
                  <h3 className="text-lg font-bold">{analysis.ticker}</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-2">
                    <div><span className="font-semibold">Price:</span> ${analysis.current_price.toFixed(2)}</div>
                    <div><span className="font-semibold">50-Day SMA:</span> ${analysis.sma_50.toFixed(2)}</div>
                    <div><span className="font-semibold">RSI:</span> {analysis.rsi.toFixed(2)}</div>
                    <div><span className="font-semibold">20D Return:</span> {analysis.return_20d_pct?.toFixed(2) ?? 'N/A'}%</div>
                  </div>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <div className="p-4 bg-gray-700 rounded-lg">
                    <h3 className="text-lg font-bold mb-2">Decision Brief</h3>
                    <p className="font-bold text-xl mb-2 capitalize">{analysis.decision_brief.verdict.replace('_', ' ')}</p>
                    <ul className="list-disc list-inside space-y-1">
                      {analysis.decision_brief.summary_bullets.map((bullet, index) => (
                        <li key={index}>{bullet}</li>
                      ))}
                    </ul>
                  </div>

                  <div className="p-4 bg-gray-700 rounded-lg">
                    <h3 className="text-lg font-bold mb-2">Macro Context</h3>
                    <p><span className="font-semibold">Volatility:</span> {analysis.macro.volatility_regime}</p>
                    <p><span className="font-semibold">Instability Score:</span> {analysis.macro.instability_score_1_10}/10</p>
                  </div>
                </div>

                <div className="p-4 bg-gray-700 rounded-lg">
                  <h3 className="text-lg font-bold mb-2">News Analysis</h3>
                  <p className="mb-2"><span className="font-semibold">Overall Sentiment:</span> {analysis.news_analysis.overall_sentiment}</p>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {analysis.news_analysis.articles.map((article, index) => (
                      <div key={index} className="p-2 bg-gray-600 rounded">
                        <p className="font-semibold">{article.title}</p>
                        <p className="text-sm text-gray-300">{article.summary}</p>
                      </div>
                    ))}
                  </div>
                </div>
                
                <div className="p-4 bg-gray-700 rounded-lg">
                    <h3 className="text-lg font-bold mb-2">Strategy Ratings</h3>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-center">
                        {Object.entries(analysis.strategy_ratings).map(([strategy, rating]) => (
                            <div key={strategy} className="p-2 bg-gray-600 rounded">
                                <p className="capitalize font-semibold">{strategy}</p>
                                <p className="text-2xl font-bold">{rating.score_1_10}</p>
                                <p className="text-sm capitalize">{rating.confidence}</p>
                            </div>
                        ))}
                    </div>
                </div>

              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;