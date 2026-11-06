import React from 'react';
import Layout from '../components/Layout';
import { useBusiness } from '../context/BusinessContext';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { TrendingUp, AlertCircle, CheckCircle2, Zap } from 'lucide-react';
import DataQualityCard from '../components/DataQualityCard';

export default function Overview() {
    const { data, loading, randomizeMockData } = useBusiness();

    // Only ever plot the backend's computed curve; nothing is drawn until it arrives.
    const chartData = data?.trajectory || [];

    const CustomTooltip = ({ active, payload }) => {
        if (active && payload && payload.length) {
            return (
                <div className="bg-[#1e293b] p-4 rounded-xl border border-white/10 shadow-2xl">
                    <p className="text-sm font-bold text-gray-400 mb-1">{payload[0].payload.name}</p>
                    <p className="text-xl font-black text-white">
                        {payload[0].value}% runway-decay estimate
                    </p>
                </div>
            );
        }
        return null;
    };

    const gritStatus = data?.grit_score > 70 ? 'Resilient' : data?.grit_score > 40 ? 'At Risk' : 'Critical';
    const gritColor = data?.grit_score > 70 ? 'text-green-400' : data?.grit_score > 40 ? 'text-yellow-400' : 'text-red-400';

    return (
        <Layout>
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-4xl font-black tracking-tight mb-2">Business Health Overview</h1>
                    <p className="text-gray-400">Real-time intelligence and runway projection.</p>
                </div>
                <button
                    onClick={randomizeMockData}
                    className="px-6 py-3 bg-gradient-to-r from-purple-600 to-blue-600 rounded-xl font-bold text-white hover:shadow-[0_0_20px_rgba(147,51,234,0.4)] transition-all flex items-center gap-2"
                >
                    <Zap size={18} />
                    Randomize Scenario
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
                {/* Main Grit Score Card */}
                <div className="lg:col-span-2 p-8 rounded-3xl bg-[#11131a] border border-white/5 relative overflow-hidden group">
                    <div className="absolute top-0 right-0 w-64 h-64 bg-purple-600/5 blur-[80px] group-hover:bg-purple-600/10 transition-colors"></div>
                    <div className="relative z-10 flex flex-col h-full justify-between">
                        <div>
                            <div className="flex items-center gap-2 text-gray-500 mb-6 uppercase tracking-widest text-xs font-bold font-mono">
                                <Activity size={14} className="text-purple-400" />
                                Current Grit Index
                            </div>
                            <div className="flex items-end gap-4 mb-4">
                                <h2 className={`text-8xl font-black ${gritColor}`}>{loading ? '---' : data?.grit_score || '0'}</h2>
                                <span className="text-xl text-gray-500 mb-4">/ 100</span>
                            </div>
                            <div className={`text-2xl font-bold flex items-center gap-2 mb-8 ${gritColor}`}>
                                {gritStatus}
                                {data?.grit_score > 70 ? <CheckCircle2 /> : <AlertCircle />}
                            </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="p-4 rounded-2xl bg-white/5 border border-white/5">
                                <div className="text-xs text-gray-500 uppercase mb-1">Runway-Decay Estimate (6 mo)</div>
                                <div className="text-2xl font-bold">{data?.runway_decay_estimate}%</div>
                            </div>
                            <div className="p-4 rounded-2xl bg-white/5 border border-white/5">
                                <div className="text-xs text-gray-500 uppercase mb-1">Fragility Tier</div>
                                <div className="text-lg font-bold">
                                    Baseline: {data?.fragility?.class || 'N/A'}
                                    <span className="text-gray-500"> → </span>
                                    Under stress: {data?.fragility?.stressed_class || 'N/A'}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Quick Stats Card */}
                <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
                    <h3 className="text-lg font-bold mb-6">Critical Benchmarks</h3>
                    <div className="space-y-6">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400"><TrendingUp size={18} /></div>
                                <span className="text-sm text-gray-400">Cash Runway</span>
                            </div>
                            <span className="font-bold">{data?.baseline?.runway_months === null ? '∞ Infinite' : `${data?.baseline?.runway_months ?? 0} Months`}</span>
                        </div>
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 rounded-lg bg-purple-500/10 text-purple-400"><TrendingUp size={18} /></div>
                                <span className="text-sm text-gray-400">Oper. Margin</span>
                            </div>
                            <span className="font-bold">{data?.baseline?.margin_percent || 0}%</span>
                        </div>
                        <div className="pt-4 border-t border-white/5">
                            <h4 className="text-sm font-bold text-gray-500 mb-4 uppercase tracking-tighter">Immediate Threat</h4>
                            <p className="text-sm leading-relaxed text-gray-400 italic">
                                "{data?.advice?.[0] || 'Analyzing business risks...'}"
                            </p>
                        </div>
                    </div>
                </div>
            </div>

            <div className="mb-8">
                <DataQualityCard report={data?.data_quality} />
            </div>

            {/* Runway-Decay Curve */}
            <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
                <div className="flex items-center justify-between mb-8">
                    <div>
                        <h3 className="text-xl font-bold">Runway-Decay Curve</h3>
                        <p className="text-sm text-gray-500">Heuristic estimate of staying solvent, months 1–6 (not a fitted survival model).</p>
                    </div>
                </div>
                <div className="h-[300px] w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <AreaChart data={chartData}>
                            <defs>
                                <linearGradient id="colorProb" x1="0" y1="0" x2="0" y2="1">
                                    <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.3} />
                                    <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0} />
                                </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff05" />
                            <XAxis dataKey="name" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} />
                            <YAxis stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} unit="%" />
                            <Tooltip content={<CustomTooltip />} />
                            <Area type="monotone" dataKey="prob" stroke="#8b5cf6" strokeWidth={3} fillOpacity={1} fill="url(#colorProb)" />
                        </AreaChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </Layout>
    );
}

const Activity = ({ size, className }) => <svg xmlns="http://www.w3.org/2000/svg" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg>;
