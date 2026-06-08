import React, { useState } from 'react';
import { MessageSquare, Send, Loader2 } from 'lucide-react';

export default function ChatPanel({ ticker }) {
  const [question, setQuestion] = useState('');
  const [trace, setTrace] = useState([]);
  const [answer, setAnswer] = useState('');
  const [citations, setCitations] = useState([]);
  const [confidence, setConfidence] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleAsk = async () => {
    if (!ticker || !question.trim()) return;
    setLoading(true);
    setError('');
    setTrace([]);
    setAnswer('');
    setCitations([]);
    setConfidence('');

    try {
      const params = new URLSearchParams({
        ticker,
        question: question.trim(),
      });
      const response = await fetch(`/api/stocks/chat/stream?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Chat stream failed.');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split('\n\n');
        buffer = parts.pop() || '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data:')) continue;
          const payload = JSON.parse(line.slice(5).trim());
          if (payload.type === 'trace') {
            setTrace((prev) => [...prev, payload.message]);
          } else if (payload.type === 'answer') {
            setAnswer(payload.answer || '');
            setCitations(payload.citations || []);
            setConfidence(payload.retrieval_confidence || '');
          }
        }
      }
    } catch (err) {
      setError(err.message || 'Unable to complete chat request.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-neutral-800/40 rounded-xl p-6 border border-neutral-700/50">
      <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
        <MessageSquare className="w-5 h-5 text-accent-purple" />
        Research Copilot
      </h3>

      {!ticker ? (
        <p className="text-sm text-neutral-400">Select a ticker to ask grounded research questions.</p>
      ) : (
        <>
          <div className="flex gap-2 mb-4">
            <input
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
              placeholder={`Ask about ${ticker} risks, catalysts, or fundamentals...`}
              className="flex-1 bg-neutral-800/50 border border-neutral-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent-cyan"
            />
            <button
              onClick={handleAsk}
              disabled={loading || !question.trim()}
              className="px-4 py-2 rounded-lg bg-accent-cyan/20 border border-accent-cyan/40 text-accent-cyan disabled:opacity-50 flex items-center gap-2"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Ask
            </button>
          </div>

          {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

          {trace.length > 0 && (
            <div className="mb-4 p-3 rounded-lg bg-neutral-900/60 border border-neutral-700/50">
              <p className="text-xs uppercase tracking-wider text-neutral-500 mb-2">Tool Trace</p>
              <ul className="space-y-1">
                {trace.map((line, idx) => (
                  <li key={idx} className="text-xs text-neutral-300">{line}</li>
                ))}
              </ul>
            </div>
          )}

          {answer && (
            <div className="space-y-3">
              <p className="text-sm text-neutral-200 leading-relaxed">{answer}</p>
              {confidence && (
                <p className="text-xs text-neutral-500">Retrieval confidence: {confidence}</p>
              )}
              {citations.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {citations.map((citation, idx) => (
                    citation.url ? (
                      <a
                        key={idx}
                        href={citation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs px-2 py-1 rounded-full bg-accent-purple/10 text-accent-purple border border-accent-purple/30 hover:bg-accent-purple/20"
                        title={citation.excerpt}
                      >
                        {citation.source}
                      </a>
                    ) : (
                      <span
                        key={idx}
                        className="text-xs px-2 py-1 rounded-full bg-neutral-700/50 text-neutral-300 border border-neutral-600"
                        title={citation.excerpt}
                      >
                        {citation.source}
                      </span>
                    )
                  ))}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
