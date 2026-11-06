import React from 'react';
import Layout from '../components/Layout';
import { useBusiness } from '../context/BusinessContext';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
import { ShieldAlert, Package, Globe, UserCheck, Info } from 'lucide-react';
import { currencySymbol } from '../lib/currency';

export default function RiskMatrix() {
    const { business, setBusiness, data, fetchAnalysis } = useBusiness();
    const sym = currencySymbol(business.currency);

    const handleInventoryChange = (field, value) => {
        const numValue = parseFloat(value) || 0;
        const newBusiness = { ...business, [field]: numValue };
        setBusiness(newBusiness);
    };

    const depData = [
        { name: 'Platform Dependency', score: data?.dependency?.platform_dependency || 0, color: '#f59e0b' },
        { name: 'Supplier Dependency', score: data?.dependency?.supplier_dependency || 0, color: '#ec4899' }
    ];

    const COLORS = ['#ef4444', '#22c55e'];
    const pieData = [
        { name: 'Locked Capital', value: data?.inventory?.locked_capital || 0 },
        { name: 'Available Cash', value: Math.max(0, business.cash_in_bank - (data?.inventory?.locked_capital || 0)) }
    ];

    const CustomPieTooltip = ({ active, payload }) => {
        if (active && payload && payload.length) {
            return (
                <div className="bg-[#1e293b] p-4 rounded-xl border border-white/10 shadow-2xl">
                    <p className="text-sm font-bold text-gray-400 mb-1">{payload[0].name}</p>
                    <p className="text-xl font-black text-white">
                        {sym}{payload[0].value.toLocaleString()}
                    </p>
                </div>
            );
        }
        return null;
    };

    const CustomBarTooltip = ({ active, payload }) => {
        if (active && payload && payload.length) {
            return (
                <div className="bg-[#1e293b] p-4 rounded-xl border border-white/10 shadow-2xl">
                    <p className="text-sm font-bold text-gray-400 mb-1">{payload[0].payload.name}</p>
                    <p className="text-xl font-black text-white">
                        {payload[0].value.toFixed(1)}%
                    </p>
                    <p className="text-xs text-gray-500 mt-1 uppercase font-bold tracking-widest">
                        Exposure Level
                    </p>
                </div>
            );
        }
        return null;
    };

    return (
        <Layout>
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-4xl font-black tracking-tight mb-2">Internal Risk Matrix</h1>
                    <p className="text-gray-400">Deep dive into operational and structural vulnerabilities.</p>
                </div>
                <button
                    onClick={() => fetchAnalysis()}
                    className="px-6 py-3 bg-white/5 border border-white/10 rounded-xl font-bold hover:bg-white/10 transition-all text-sm"
                >
                    Recalculate Risk
                </button>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                {/* Inventory Risk */}
                <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
                    <div className="flex items-center gap-3 mb-8">
                        <div className="p-3 bg-red-500/10 text-red-500 rounded-2xl">
                            <Package size={20} />
                        </div>
                        <h3 className="text-xl font-bold">Capital Lock Index</h3>
                    </div>

                    <div className="grid grid-cols-2 gap-8 mb-8">
                        <div className="space-y-4">
                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase tracking-tighter">Stock Units</label>
                                <input
                                    type="number"
                                    value={business.stock_units}
                                    onChange={(e) => handleInventoryChange('stock_units', e.target.value)}
                                    className="w-full bg-[#0a0b10] border border-white/5 rounded-xl px-4 py-3 text-lg font-mono mt-1 focus:border-red-500/50 outline-none"
                                />
                            </div>
                            <div>
                                <label className="text-xs font-bold text-gray-500 uppercase tracking-tighter">Cost Per Unit ({sym})</label>
                                <input
                                    type="number"
                                    value={business.cost_per_unit}
                                    onChange={(e) => handleInventoryChange('cost_per_unit', e.target.value)}
                                    className="w-full bg-[#0a0b10] border border-white/5 rounded-xl px-4 py-3 text-lg font-mono mt-1 focus:border-red-500/50 outline-none"
                                />
                            </div>
                        </div>
                        <div className="h-[200px]">
                            <ResponsiveContainer width="100%" height="100%">
                                <PieChart>
                                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={60} outerRadius={80} paddingAngle={2} dataKey="value">
                                        {pieData.map((entry, index) => (
                                            <Cell key={`cell-${index}`} fill={COLORS[index]} stroke="none" />
                                        ))}
                                    </Pie>
                                    <Tooltip content={<CustomPieTooltip />} />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </div>

                    <div className="p-6 rounded-2xl bg-white/5 border border-white/5">
                        <div className="flex justify-between items-center mb-2">
                            <span className="text-sm text-gray-400 font-bold uppercase">Locked Value</span>
                            <span className="text-2xl font-black text-red-500">{sym}{data?.inventory?.locked_capital?.toLocaleString() || '0'}</span>
                        </div>
                        <div className="text-xs text-red-400 font-bold animate-pulse mb-1">
                            {data?.inventory?.risk_level === 'RED' && "🚨 ACTION REQUIRED: Liquidity Trap Detected"}
                        </div>
                        <div className="text-xs text-gray-500 font-medium leading-relaxed">
                            {data?.inventory?.warning || `${data?.inventory?.days_to_liquidate?.toFixed(1) || '0'} days of inventory remaining.`}
                        </div>
                    </div>
                </div>

                {/* Dependency Risk */}
                <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5 relative overflow-hidden">
                    {data?.dependency?.platform_dependency > 50 && (
                        <div className="absolute top-0 right-0 px-4 py-1 bg-red-500 text-[10px] font-black uppercase tracking-tighter rounded-bl-xl z-10 animate-pulse">
                            High Exposure
                        </div>
                    )}
                    <div className="flex items-center gap-3 mb-8">
                        <div className="p-3 bg-amber-500/10 text-amber-500 rounded-2xl">
                            <Globe size={20} />
                        </div>
                        <h3 className="text-xl font-bold">Dependency Exposure</h3>
                    </div>

                    <div className="space-y-6 mb-8">
                        <div>
                            <div className="flex justify-between mb-2">
                                <label className="text-xs font-bold text-gray-500 uppercase tracking-tighter">Top Platform Dependency (%)</label>
                                <span className={`text-sm font-mono font-bold ${data?.dependency?.platform_dependency > 50 ? 'text-red-400' : 'text-gray-400'}`}>
                                    {data?.dependency?.platform_dependency?.toFixed(1)}%
                                </span>
                            </div>
                            <input
                                type="range"
                                min="0"
                                max={business.revenue}
                                value={business.top_platform_rev}
                                onChange={(e) => handleInventoryChange('top_platform_rev', e.target.value)}
                                className="w-full h-2 bg-[#0a0b10] rounded-lg appearance-none cursor-pointer accent-amber-500"
                            />
                        </div>
                        <div>
                            <div className="flex justify-between mb-2">
                                <label className="text-xs font-bold text-gray-500 uppercase tracking-tighter">Top Supplier Concentration (%)</label>
                                <span className={`text-sm font-mono font-bold ${data?.dependency?.supplier_dependency > 50 ? 'text-red-400' : 'text-gray-400'}`}>
                                    {data?.dependency?.supplier_dependency?.toFixed(1)}%
                                </span>
                            </div>
                            <input
                                type="range"
                                min="0"
                                max={business.total_purchases}
                                value={business.top_supplier_spend}
                                onChange={(e) => handleInventoryChange('top_supplier_spend', e.target.value)}
                                className="w-full h-2 bg-[#0a0b10] rounded-lg appearance-none cursor-pointer accent-pink-500"
                            />
                        </div>
                    </div>

                    <div className="h-[240px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={depData} margin={{ top: 10, right: 30, left: 0, bottom: 5 }}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff05" vertical={false} />
                                <XAxis dataKey="name" stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} />
                                <YAxis domain={[0, 100]} stroke="#64748b" fontSize={11} tickLine={false} axisLine={false} unit="%" />
                                <Tooltip cursor={{ fill: '#ffffff05' }} content={<CustomBarTooltip />} />
                                <Bar dataKey="score" radius={[8, 8, 0, 0]} barSize={50}>
                                    {depData.map((entry, index) => (
                                        <Cell key={`cell-${index}`} fill={entry.color} />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>

                    {data?.dependency?.platform_dependency > 50 && (
                        <div className="mt-6 p-4 rounded-xl bg-red-500/5 border border-red-500/10 flex gap-3 items-start">
                            <ShieldAlert size={16} className="text-red-400 shrink-0 mt-0.5" />
                            <p className="text-[11px] text-gray-400 leading-tight">
                                **Concentration Risk**: You have crossed the **50% platform threshold**. A single algorithm update or account suspension could permanently impair your enterprise value.
                            </p>
                        </div>
                    )}
                </div>
            </div>

            <div className="mt-10 p-8 rounded-3xl bg-amber-500/5 border border-amber-500/10">
                <div className="flex gap-6 items-start">
                    <div className="p-4 bg-amber-500/20 rounded-full">
                        <ShieldAlert className="text-amber-500" size={24} />
                    </div>
                    <div>
                        <h4 className="text-xl font-bold mb-2">Dependency Warning</h4>
                        <p className="text-gray-400 text-sm leading-relaxed max-w-3xl">
                            High platform dependency means your revenue is at risk if that platform changes its algorithm or policies.
                            Similarly, high supplier concentration makes you fragile to supply chain disruptions.
                            Aim for a dependency score below <span className="text-white font-bold">0.4</span> for optimal resilience.
                        </p>
                    </div>
                </div>
            </div>
        </Layout>
    );
}
