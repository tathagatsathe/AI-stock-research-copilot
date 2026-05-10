import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  TrendingUp, Activity, Newspaper, ShieldAlert, 
  DollarSign, BarChart2, Search, Target, Zap
} from 'lucide-react';

function App() {
  const [universe, setUniverse] = useState([]);
  const [selectedStock, setSelectedStock] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [loadingUniverse, setLoadingUniverse] = useState(false);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [error, setError] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

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

  const filteredUniverse = universe.filter(s => 
    s.ticker.toLowerCase().includes(searchQuery.toLowerCase()) || 
    s.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } }
  };

  const itemVariants = {
    hidden: { y: 20, opacity: 0 },
    visible: { y: 0, opacity: 1 }
  };

  return (
    <div className="min-h-screen p-4 md:p-8 flex flex-col items-center relative overflow-hidden">
      {/* Background Blobs for Animation */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-accent-purple/20 rounded-full mix-blend-screen filter blur-[100px] animate-blob"></div>
      <div className="absolute top-[20%] right-[-10%] w-[40%] h-[40%] bg-accent-cyan/20 rounded-full mix-blend-screen filter blur-[100px] animate-blob animation-delay-2000"></div>
      
      <div className="w-full max-w-[1400px] relative z-10 flex flex-col h-[calc(100vh-4rem)]">
        <header className="mb-8 text-center md:text-left flex items-center gap-3">
          <div className="p-3 bg-gradient-to-br from-accent-purple to-accent-cyan rounded-xl shadow-lg">
            <Zap className="text-white w-6 h-6" />
          </div>
          <div>
            <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
              Nexus<span className="text-accent-cyan">AI</span>
            </h1>
            <p className="text-sm text-slate-400 font-medium">Quantitative Stock Analysis</p>
          </div>
        </header>
        
        <div className="flex flex-col md:flex-row gap-6 flex-1 min-h-0">
          
          {/* Sidebar: Stock Universe */}
          <motion.div 
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="w-full md:w-80 glass-panel flex flex-col overflow-hidden shrink-0"
          >
            <div className="p-5 border-b border-glass-border">
              <h2 className="text-lg font-semibold flex items-center gap-2 mb-4 text-white">
                <Target className="w-5 h-5 text-accent-cyan" /> Market Universe
              </h2>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input 
                  type="text" 
                  placeholder="Search or enter custom ticker..." 
                  className="w-full bg-slate-800/50 border border-slate-700 rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan focus:border-transparent transition-all"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && searchQuery.trim() !== '') {
                      handleAnalyze(searchQuery.trim().toUpperCase());
                    }
                  }}
                />
              </div>
            </div>
            
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {loadingUniverse && (
                <div className="flex justify-center items-center h-20">
                  <div className="w-6 h-6 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin"></div>
                </div>
              )}
              {error && !loadingUniverse && <p className="text-red-400 text-sm p-2 text-center bg-red-400/10 rounded">{error}</p>}
              
              <AnimatePresence>
                {searchQuery.trim() !== '' && !universe.some(s => s.ticker.toLowerCase() === searchQuery.trim().toLowerCase()) && (
                  <motion.button
                    key="custom-ticker"
                    layout
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => handleAnalyze(searchQuery.trim().toUpperCase())}
                    className="w-full text-left p-3 rounded-xl transition-all border bg-slate-800/30 border-dashed border-slate-500 hover:bg-slate-800/50 hover:border-accent-cyan"
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-accent-cyan text-lg tracking-tight">Analyze "{searchQuery.trim().toUpperCase()}"</span>
                      <Search className="w-4 h-4 text-accent-cyan" />
                    </div>
                    <span className="text-xs text-slate-400 block mt-0.5">Custom Ticker Search (Press Enter)</span>
                  </motion.button>
                )}
                {filteredUniverse.map((stock) => (
                  <motion.button
                    key={stock.ticker}
                    layout
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    whileHover={{ scale: 1.02 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => handleAnalyze(stock.ticker)}
                    className={`w-full text-left p-3 rounded-xl transition-all border ${
                      selectedStock === stock.ticker 
                        ? 'bg-gradient-to-r from-accent-cyan/20 to-transparent border-accent-cyan/50 shadow-[inset_4px_0_0_0_#22d3ee]' 
                        : 'bg-slate-800/30 border-transparent hover:bg-slate-800/50 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-white text-lg tracking-tight">{stock.ticker}</span>
                      {selectedStock === stock.ticker && <Activity className="w-4 h-4 text-accent-cyan animate-pulse" />}
                    </div>
                    <span className="text-xs text-slate-400 truncate block mt-0.5">{stock.name}</span>
                  </motion.button>
                ))}
              </AnimatePresence>
            </div>
          </motion.div>
          
          {/* Main Content: Analysis */}
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex-1 glass-panel overflow-hidden flex flex-col"
          >
            {loadingAnalysis ? (
              <div className="flex-1 flex flex-col items-center justify-center">
                <div className="w-12 h-12 border-4 border-accent-purple border-t-transparent rounded-full animate-spin mb-4"></div>
                <p className="text-slate-400 font-medium animate-pulse">Running quantitative models...</p>
              </div>
            ) : error && !loadingAnalysis ? (
              <div className="flex-1 flex items-center justify-center p-8">
                <div className="glass-panel border-red-500/30 bg-red-500/10 p-6 text-center max-w-md">
                  <ShieldAlert className="w-12 h-12 text-red-400 mx-auto mb-4" />
                  <h3 className="text-lg font-bold text-white mb-2">Analysis Failed</h3>
                  <p className="text-red-200 text-sm">{error}</p>
                </div>
              </div>
            ) : !analysis ? (
              <div className="flex-1 flex flex-col items-center justify-center p-8 text-center opacity-60">
                <BarChart2 className="w-20 h-20 text-slate-600 mb-6" />
                <h3 className="text-2xl font-bold text-slate-300 mb-2">Awaiting Selection</h3>
                <p className="text-slate-400 max-w-sm">Select a ticker from the market universe to generate a comprehensive AI-driven analysis.</p>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-6 md:p-8">
                <motion.div 
                  variants={containerVariants} 
                  initial="hidden" 
                  animate="visible"
                  className="space-y-8"
                >
                  {/* Header Card */}
                  <motion.div variants={itemVariants} className="flex flex-col md:flex-row justify-between items-start md:items-end pb-6 border-b border-slate-700/50">
                    <div>
                      <h2 className="text-4xl font-black text-white tracking-tight mb-2 flex items-center gap-3">
                        {analysis.ticker}
                        <span className={`text-sm px-3 py-1 rounded-full font-bold uppercase tracking-wider ${
                          analysis.decision_brief.verdict === 'buy' || analysis.decision_brief.verdict === 'strong_buy' ? 'bg-green-500/20 text-green-400 border border-green-500/30' :
                          analysis.decision_brief.verdict === 'sell' || analysis.decision_brief.verdict === 'strong_sell' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                          'bg-yellow-500/20 text-yellow-400 border border-yellow-500/30'
                        }`}>
                          {analysis.decision_brief.verdict.replace('_', ' ')}
                        </span>
                      </h2>
                      <div className="flex items-center gap-6 text-sm">
                        <div className="flex items-center gap-2">
                          <DollarSign className="w-4 h-4 text-slate-400" />
                          <span className="text-2xl font-semibold text-white">{analysis.current_price.toFixed(2)}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <Activity className="w-4 h-4 text-slate-400" />
                          <span className="text-slate-300">RSI: {analysis.rsi.toFixed(2)}</span>
                        </div>
                      </div>
                    </div>
                  </motion.div>

                  {/* Summary Bullets */}
                  <motion.div variants={itemVariants} className="bg-slate-800/40 rounded-xl p-6 border border-slate-700/50">
                    <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                      <TrendingUp className="w-5 h-5 text-accent-cyan" /> Key Insights
                    </h3>
                    <ul className="space-y-3">
                      {analysis.decision_brief.summary_bullets.map((bullet, index) => (
                        <li key={index} className="flex items-start gap-3 text-slate-300">
                          <div className="mt-1.5 w-1.5 h-1.5 rounded-full bg-accent-cyan shrink-0"></div>
                          <span className="leading-relaxed">{bullet}</span>
                        </li>
                      ))}
                    </ul>
                  </motion.div>

                  {/* Strategy Ratings Grid */}
                  <motion.div variants={itemVariants}>
                    <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                      <BarChart2 className="w-5 h-5 text-accent-purple" /> Strategy Alpha
                    </h3>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                      {Object.entries(analysis.strategy_ratings).map(([strategy, rating]) => (
                        <div key={strategy} className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 flex flex-col items-center justify-center text-center group hover:bg-slate-800/60 transition-colors">
                          <p className="text-xs uppercase tracking-wider text-slate-400 mb-2 font-semibold">{strategy}</p>
                          <div className="relative mb-1">
                            <svg className="w-16 h-16 transform -rotate-90">
                              <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-slate-700" />
                              <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="4" fill="transparent" 
                                strokeDasharray={`${rating.score_1_10 * 17.6} 176`} 
                                className={`transition-all duration-1000 ${rating.score_1_10 > 7 ? 'text-green-400' : rating.score_1_10 > 4 ? 'text-yellow-400' : 'text-red-400'}`} 
                              />
                            </svg>
                            <span className="absolute inset-0 flex items-center justify-center text-xl font-bold text-white">{rating.score_1_10}</span>
                          </div>
                          <p className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full mt-2 ${
                            rating.confidence === 'high' ? 'bg-green-500/10 text-green-400' : 
                            rating.confidence === 'low' ? 'bg-red-500/10 text-red-400' : 
                            'bg-yellow-500/10 text-yellow-400'
                          }`}>
                            {rating.confidence} Conf
                          </p>
                        </div>
                      ))}
                    </div>
                  </motion.div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Macro Context */}
                    <motion.div variants={itemVariants} className="bg-slate-800/40 rounded-xl p-6 border border-slate-700/50">
                      <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                        <ShieldAlert className="w-5 h-5 text-accent-cyan" /> Macro Risk Profile
                      </h3>
                      <div className="space-y-4">
                        <div>
                          <p className="text-sm text-slate-400 mb-1">Volatility Regime</p>
                          <p className="text-lg font-semibold text-white capitalize">{analysis.macro.volatility_regime}</p>
                        </div>
                        <div>
                          <p className="text-sm text-slate-400 mb-1">Instability Score</p>
                          <div className="flex items-center gap-3">
                            <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
                              <div 
                                className={`h-full ${analysis.macro.instability_score_1_10 > 7 ? 'bg-red-500' : analysis.macro.instability_score_1_10 > 4 ? 'bg-yellow-500' : 'bg-green-500'}`} 
                                style={{ width: `${analysis.macro.instability_score_1_10 * 10}%` }}
                              ></div>
                            </div>
                            <span className="font-bold text-white">{analysis.macro.instability_score_1_10}/10</span>
                          </div>
                        </div>
                      </div>
                    </motion.div>

                    {/* News Feed */}
                    <motion.div variants={itemVariants} className="bg-slate-800/40 rounded-xl p-6 border border-slate-700/50 flex flex-col h-[300px]">
                      <h3 className="text-lg font-bold text-white mb-4 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Newspaper className="w-5 h-5 text-accent-purple" /> Market News
                        </div>
                        <span className={`text-xs px-2 py-1 rounded font-bold uppercase ${
                          analysis.news_analysis.overall_sentiment === 'bullish' ? 'text-green-400 bg-green-500/10' :
                          analysis.news_analysis.overall_sentiment === 'bearish' ? 'text-red-400 bg-red-500/10' :
                          'text-yellow-400 bg-yellow-500/10'
                        }`}>
                          {analysis.news_analysis.overall_sentiment}
                        </span>
                      </h3>
                      <div className="flex-1 overflow-y-auto pr-2 space-y-4">
                        {analysis.news_analysis.articles.map((article, index) => (
                          <div key={index} className="group cursor-pointer">
                            <p className="font-semibold text-sm text-slate-200 group-hover:text-accent-cyan transition-colors mb-1">{article.title}</p>
                            <p className="text-xs text-slate-400 line-clamp-2">{article.summary}</p>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  </div>
                </motion.div>
              </div>
            )}
          </motion.div>
          
        </div>
      </div>
    </div>
  );
}

export default App;