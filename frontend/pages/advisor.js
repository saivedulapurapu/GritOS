import React, { useState, useRef, useEffect } from 'react';
import Layout from '../components/Layout';
import { useBusiness } from '../context/BusinessContext';
import { Send, Bot, User, Sparkles, MessageSquare, Trash2, Zap, RefreshCcw } from 'lucide-react';
import { API_URL } from '../lib/api';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const FormattedMessage = ({ content, role }) => {
    return (
        <div className={`markdown-content ${role === 'user' ? 'user-content' : 'ai-content'}`}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
            </ReactMarkdown>
            <style jsx global>{`
                .markdown-content {
                    font-size: 1.1rem;
                    line-height: 1.7;
                    word-break: break-word;
                }
                .markdown-content p {
                    margin-bottom: 1.25rem;
                }
                .markdown-content p:last-child {
                    margin-bottom: 0;
                }
                .markdown-content strong {
                    color: inherit;
                    font-weight: 700;
                }
                .markdown-content ul, .markdown-content ol {
                    margin-bottom: 1.25rem;
                    padding-left: 1.5rem;
                }
                .markdown-content li {
                    margin-bottom: 0.5rem;
                }
                .ai-content ul {
                    list-style-type: none;
                }
                .ai-content ul li {
                    position: relative;
                }
                .ai-content ul li::before {
                    content: "•";
                    color: #a855f7;
                    font-weight: bold;
                    display: inline-block;
                    width: 1rem;
                    margin-left: -1rem;
                }

                /* Table Styling - Premium Dark Mode */
                .markdown-content table {
                    width: 100%;
                    border-collapse: separate;
                    border-spacing: 0;
                    margin-bottom: 1.5rem;
                    background: rgba(255, 255, 255, 0.03);
                    border: 1px solid rgba(255, 255, 255, 0.1);
                    border-radius: 1rem;
                    overflow: hidden;
                }
                .markdown-content th {
                    background: rgba(168, 85, 247, 0.15);
                    padding: 0.75rem 1rem;
                    text-align: left;
                    font-weight: 700;
                    color: #fff;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
                }
                .markdown-content td {
                    padding: 0.75rem 1rem;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.05);
                    color: rgba(255, 255, 255, 0.8);
                }
                .markdown-content tr:last-child td {
                    border-bottom: none;
                }
                .markdown-content tr:hover td {
                    background: rgba(255, 255, 255, 0.02);
                }

                /* Blockquotes */
                .markdown-content blockquote {
                    border-left: 4px solid #a855f7;
                    background: rgba(168, 85, 247, 0.05);
                    padding: 1rem 1.5rem;
                    border-radius: 0 1rem 1rem 0;
                    margin-bottom: 1.25rem;
                    font-style: italic;
                    color: rgba(255, 255, 255, 0.9);
                }

                /* Code blocks */
                .markdown-content code {
                    background: rgba(0, 0, 0, 0.3);
                    padding: 0.2rem 0.4rem;
                    border-radius: 0.4rem;
                    font-family: inherit;
                    color: #fca5a5;
                }
                .markdown-content pre code {
                    display: block;
                    padding: 1rem;
                    overflow-x: auto;
                    color: #fff;
                }
            `}</style>
        </div>
    );
};

export default function AIAdvisor() {
    const { business, shocks, chatMessages, setChatMessages } = useBusiness();
    const [input, setInput] = useState('');
    const [isTyping, setIsTyping] = useState(false);
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [chatMessages, isTyping]);

    const clearChat = () => {
        setChatMessages([{
            role: 'model',
            content: "Consultation reset. I'm ready for a fresh strategic analysis. What should we focus on?"
        }]);
    };

    const handleSend = async () => {
        if (!input.trim() || isTyping) return;

        const userMsg = { role: 'user', content: input };
        const updatedMessages = [...chatMessages, userMsg];
        setChatMessages(updatedMessages);
        setInput('');
        setIsTyping(true);

        // Placeholder for the streaming response
        const assistantMsg = { role: 'model', content: '' };
        setChatMessages(prev => [...prev, assistantMsg]);

        try {
            const response = await fetch(`${API_URL}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: updatedMessages,
                    state: { ...business, ...shocks }
                })
            });

            if (!response.ok) {
                const errorData = await response.text();
                throw new Error(`Engine error (${response.status}): ${errorData.substring(0, 50)}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let accumulatedContent = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                accumulatedContent += chunk;

                setChatMessages(prev => {
                    const last = prev[prev.length - 1];
                    const others = prev.slice(0, -1);
                    return [...others, { ...last, content: accumulatedContent }];
                });
            }
        } catch (err) {
            setChatMessages(prev => {
                const last = prev[prev.length - 1];
                const others = prev.slice(0, -1);
                return [...others, { ...last, content: `⚠️ Strategic Link Error: ${err.message}. Please ensure the GritOS engine is running.` }];
            });
        } finally {
            setIsTyping(false);
        }
    };

    return (
        <Layout>
            <div className="flex flex-col h-[calc(100vh-40px)] max-w-5xl mx-auto px-4 py-6">
                <div className="flex justify-between items-center mb-6">
                    <div>
                        <div className="flex items-center gap-3 mb-1">
                            <div className="p-2 bg-purple-600 rounded-lg">
                                <Zap size={18} className="text-white" />
                            </div>
                            <h1 className="text-3xl font-black tracking-tight bg-gradient-to-r from-white to-gray-500 bg-clip-text text-transparent">AI Strategy HQ</h1>
                        </div>
                        <p className="text-gray-400 text-sm font-medium">Real-time predictive intelligence for elite business resilience.</p>
                    </div>
                    <div className="flex items-center gap-4">
                        <button
                            onClick={clearChat}
                            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-gray-400 hover:text-white hover:bg-white/10 transition-all text-sm font-bold"
                        >
                            <Trash2 size={16} />
                            Clear Session
                        </button>
                        <div className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-purple-500/10 border border-purple-500/20 text-purple-400 text-sm font-bold shadow-[0_0_20px_rgba(168,85,247,0.1)]">
                            <Sparkles size={16} className="animate-pulse" />
                            Groq Llama 3 Engine
                        </div>
                    </div>
                </div>

                {/* Chat Container */}
                <div className="flex-grow bg-[#0d0f14] border border-white/5 rounded-[2rem] overflow-hidden flex flex-col relative shadow-2xl backdrop-blur-3xl">
                    <div className="absolute top-0 left-0 w-full h-[2px] bg-gradient-to-r from-transparent via-purple-600 to-transparent opacity-50"></div>

                    {/* Messages Area */}
                    <div ref={scrollRef} className="flex-grow overflow-y-auto p-6 space-y-6 scroll-smooth">
                        {chatMessages.map((msg, idx) => (
                            <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''} animate-in fade-in slide-in-from-bottom-4 duration-500`}>
                                <div className={`w-10 h-10 rounded-xl flex-shrink-0 flex items-center justify-center shadow-lg ${msg.role === 'model' ? 'bg-gradient-to-br from-purple-600 to-blue-600' : 'bg-[#1e293b] border border-white/10 ring-2 ring-white/5'}`}>
                                    {msg.role === 'model' ? <Bot size={20} className="text-white" /> : <User size={20} className="text-gray-300" />}
                                </div>
                                <div className={`max-w-[85%] md:max-w-[75%] p-5 rounded-2xl text-[1rem] leading-relaxed shadow-lg border ${msg.role === 'model'
                                    ? 'bg-white/5 border-white/5 text-gray-100 rounded-tl-sm'
                                    : 'bg-gradient-to-br from-purple-600 to-indigo-700 border-purple-500/30 text-white rounded-tr-sm'
                                    }`}>
                                    <FormattedMessage content={msg.content} role={msg.role} />
                                </div>
                            </div>
                        ))}
                        {isTyping && chatMessages[chatMessages.length - 1].content === '' && (
                            <div className="flex gap-4 animate-pulse">
                                <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-600 to-blue-600 flex items-center justify-center">
                                    <Bot size={20} className="text-white" />
                                </div>
                                <div className="p-4 rounded-2xl rounded-tl-sm bg-white/5 border border-white/5 flex gap-2 items-center">
                                    <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce"></div>
                                    <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce [animation-delay:0.2s]"></div>
                                    <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce [animation-delay:0.4s]"></div>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Input Area */}
                    <div className="p-4 md:p-6 border-t border-white/5 bg-[#0a0b10] z-10 shadow-[0_-10px_40px_rgba(0,0,0,0.5)]">
                        <div className="relative w-full max-w-4xl mx-auto flex gap-3">
                            <div className="relative flex-grow">
                                <input
                                    type="text"
                                    value={input}
                                    onChange={(e) => setInput(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && handleSend()}
                                    placeholder="Message AI Strategy HQ..."
                                    className="w-full bg-[#161a23] border border-white/10 rounded-xl px-5 py-4 text-[1rem] pr-20 focus:outline-none focus:border-purple-500/50 focus:ring-1 focus:ring-purple-500/30 transition-all text-white placeholder-gray-500"
                                />
                                <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center">
                                    <kbd className="hidden md:flex items-center justify-center w-6 h-6 bg-white/5 border border-white/10 text-[10px] font-semibold text-gray-500 rounded p-1">⏎</kbd>
                                </div>
                            </div>
                            <button
                                onClick={handleSend}
                                disabled={isTyping || !input.trim()}
                                className="px-6 bg-purple-600 hover:bg-purple-500 rounded-xl text-white font-medium hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50 disabled:grayscale transition-all shadow-lg flex items-center justify-center gap-2 min-w-[100px]"
                            >
                                <Send size={18} />
                                <span className="hidden sm:inline">Send</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </Layout>
    );
}
