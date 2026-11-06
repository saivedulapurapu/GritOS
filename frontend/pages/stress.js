import React from 'react';
import Layout from '../components/Layout';
import { useBusiness } from '../context/BusinessContext';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, Legend, LabelList } from 'recharts';
import { ShieldAlert, Zap, TrendingDown, Info } from 'lucide-react';

export default function StressTest() {
    const { business, shocks, setShocks, data, loading } = useBusiness();

    const handleShockChange = (field, value) => {
        setShocks(prev => ({ ...prev, [field]: parseFloat(value) || 0 }));
    };

    // Bars use the same 12-month horizon as the backend's sensitivity / months-lost.
    // null runway = no cash burn -> full bar labelled ∞; runway over 12 -> full bar labelled 12+.
    const HORIZON = 12;
    const barValue = (val) => (val === null ? HORIZON : Math.min(HORIZON, parseFloat(val) || 0));
    const barLabel = (val) => {
        if (val === null) return '∞ no cash burn';
        if (val === undefined) return '';
        const months = parseFloat(val) || 0;
        return months > HORIZON ? `12+ (${months.toFixed(1)} mo)` : `${months.toFixed(1)} mo`;
    };

    const runwayData = [
        { name: 'Baseline', value: barValue(data?.baseline?.runway_months), label: barLabel(data?.baseline?.runway_months), color: '#3b82f6' },
        { name: 'Shock Impact', value: barValue(data?.simulation?.runway), label: barLabel(data?.simulation?.runway), color: '#ef4444' }
    ];

    const monthsLost = data?.simulation?.runway_lost_months ?? 0;

    const CustomTooltip = ({ active, payload }) => {
        if (active && payload && payload.length) {
            const { name, label } = payload[0].payload;
            return (
                <div className="bg-[#1e293b] p-4 rounded-xl border border-white/10 shadow-2xl">
                    <p className="text-sm font-bold text-gray-400 mb-1">{name}</p>
                    <p className="text-xl font-black text-white">
                        {label}
                    </p>
                </div>
            );
        }
        return null;
    };

    const shocksList = [
        { id: 'cac_shock', label: 'Ad Cost (CAC) Spike (%)', min: 0, max: 300, icon: <Zap size={16} /> },
        { id: 'rev_shock', label: 'Revenue Decline (%)', min: 0, max: 100, icon: <TrendingDown size={16} /> },
        { id: 'cogs_shock', label: 'Supply Cost Increase (%)', min: 0, max: 300, icon: <ShieldAlert size={16} /> }
    ];

    return (
        <Layout>
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-4xl font-black tracking-tight mb-2">Market Stress Simulator</h1>
                    <p className="text-gray-400">Project your business resilience against external shocks.</p>
                </div>
                <div className="px-4 py-2 rounded-full bg-red-500/10 border border-red-500/20 text-red-400 text-sm font-bold flex items-center gap-2">
                    <ShieldAlert size={16} />
                    Live Simulation Active
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                {/* Sliders Area */}
                <div className="space-y-8">
                    {shocksList.map((shock) => (
                        <div key={shock.id} className="p-8 rounded-3xl bg-[#11131a] border border-white/5 group hover:border-purple-500/30 transition-all">
                            <div className="flex justify-between items-center mb-6">
                                <div className="flex items-center gap-3">
                                    <div className="p-3 bg-white/5 rounded-2xl text-purple-400 group-hover:bg-purple-500/10 transition-colors">
                                        {shock.icon}
                                    </div>
                                    <span className="font-bold text-lg">{shock.label}</span>
                                </div>
                                <span className="text-2xl font-mono font-black text-white">+{shocks[shock.id]}%</span>
                            </div>
                            <input
                                type="range"
                                min={shock.min}
                                max={shock.max}
                                value={shocks[shock.id]}
                                onChange={(e) => handleShockChange(shock.id, e.target.value)}
                                className="w-full h-2 bg-[#0a0b10] rounded-lg appearance-none cursor-pointer accent-purple-500"
                            />
                            <div className="flex justify-between mt-4 text-xs text-gray-500 font-mono">
                                <span>MIN: {shock.min}%</span>
                                <span>MAX: {shock.max}%</span>
                            </div>
                        </div>
                    ))}

                    <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
                        <div className="font-bold text-lg mb-4">When revenue falls, ad spend…</div>
                        <div className="flex gap-3">
                            {[
                                { id: 'fixed', label: 'Stays fixed (default)' },
                                { id: 'scales', label: 'Scales with volume' },
                            ].map((opt) => (
                                <button
                                    key={opt.id}
                                    onClick={() => setShocks(prev => ({ ...prev, ad_spend_behaviour: opt.id }))}
                                    className={`px-4 py-2 rounded-xl text-sm font-bold border transition-all ${shocks.ad_spend_behaviour === opt.id ? 'bg-purple-600/30 border-purple-500/50 text-white' : 'bg-white/5 border-white/10 text-gray-400 hover:text-white'}`}
                                >
                                    {opt.label}
                                </button>
                            ))}
                        </div>
                        <p className="mt-3 text-xs text-gray-500">Fixed: committed campaigns keep spending, so effective CAC rises as demand falls. Scales: ad spend falls in line with orders.</p>
                    </div>

                    <div className="p-6 rounded-2xl bg-purple-600/5 border border-purple-500/10 flex items-start gap-4">
                        <Info className="text-purple-400 mt-1" size={20} />
                        <p className="text-sm text-gray-400 leading-relaxed">
                            Market shocks are simulated using a **Sensitivity Multiplier**. For example, a 20% CAC spike doesn't just increase costs; it measures how your overall **contribution margin** erodes and accelerates your **cash burn**.
                        </p>
                    </div>
                </div>

                {/* Impact Visualization */}
                <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5 flex flex-col">
                    <h3 className="text-xl font-bold mb-8">Runway Impact Analysis</h3>

                    <div className="flex-grow h-[400px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={runwayData} layout="vertical" margin={{ left: 40, right: 40 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff05" horizontal={false} />
                                <XAxis type="number" stroke="#64748b" fontSize={12} tickLine={false} axisLine={false} domain={[0, HORIZON]} ticks={[0, 3, 6, 9, 12]} tickFormatter={(t) => (t === HORIZON ? '12+' : t)} />
                                <YAxis dataKey="name" type="category" stroke="#fff" fontSize={14} fontWeight="bold" tickLine={false} axisLine={false} width={100} />
                                <Tooltip
                                    cursor={{ fill: '#ffffff05' }}
                                    content={<CustomTooltip />}
                                />
                                <Bar dataKey="value" radius={[0, 10, 10, 0]} barSize={60}>
                                    <LabelList dataKey="label" position="insideRight" fill="#fff" fontSize={12} />
                                    {runwayData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    <div className="mt-8 grid grid-cols-2 gap-4">
                        <div className="p-6 rounded-2xl bg-white/5 border border-white/5 text-center">
                            <div className="text-xs text-gray-500 uppercase mb-2">Months Lost (12-mo horizon)</div>
                            <div className="text-4xl font-black text-red-500">
                                {monthsLost.toFixed(1)}
                            </div>
                        </div>
                        <div className="p-6 rounded-2xl bg-white/5 border border-white/5 text-center">
                            <div className="text-xs text-gray-500 uppercase mb-2">Shock Sensitivity</div>
                            <div className="text-4xl font-black text-purple-400">
                                {(data?.fragility?.sensitivity ?? 0).toFixed(3)}
                            </div>
                        </div>
                    </div>

                    <div className="mt-4 p-6 rounded-2xl bg-white/5 border border-white/5">
                        <div className="text-xs text-gray-500 uppercase mb-2">Fragility Tier</div>
                        <div className="text-lg font-bold">
                            Baseline: {data?.fragility?.class || 'N/A'}
                            <span className="text-gray-500"> → </span>
                            <span className={data?.fragility?.stressed_class === 'Critical' ? 'text-red-400' : ''}>
                                Under stress: {data?.fragility?.stressed_class || 'N/A'}
                            </span>
                        </div>
                        {data?.fragility?.stressed_reasons?.length > 0 && (
                            <ul className="mt-2 text-xs text-gray-400 list-disc list-inside">
                                {data.fragility.stressed_reasons.map((reason) => <li key={reason}>{reason}</li>)}
                            </ul>
                        )}
                    </div>
                </div>
            </div>
        </Layout>
    );
}
