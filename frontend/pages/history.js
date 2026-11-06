import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const API = 'http://localhost:8000';

const fmtRunway = (v) => (v === null || v === undefined ? '∞' : `${Number(v).toFixed(1)} mo`);

export default function History() {
    const [rows, setRows] = useState([]);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetch(`${API}/api/history?limit=100`)
            .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
            .then(setRows)
            .catch((e) => setError(e.message));
    }, []);

    // oldest -> newest for the trend line
    const chartData = [...rows].reverse().map((r) => ({
        name: new Date(r.created_at).toLocaleTimeString(),
        grit: r.grit_score,
        estimate: r.runway_decay_estimate,
        quality: r.quality_score,
    }));

    return (
        <Layout>
            <div className="mb-10">
                <h1 className="text-4xl font-black tracking-tight mb-2">Analysis History</h1>
                <p className="text-gray-400">Every analysis is saved with its inputs, results and data-quality issues.</p>
            </div>

            {error && <div className="mb-6 text-red-400 text-sm">Could not load history: {error}</div>}

            <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5 mb-8">
                <h3 className="text-xl font-bold mb-6">Trend</h3>
                <div className="h-[280px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                            <XAxis dataKey="name" stroke="#64748b" fontSize={11} />
                            <YAxis domain={[0, 100]} stroke="#64748b" fontSize={11} />
                            <Tooltip contentStyle={{ background: '#1e293b', border: 'none' }} />
                            <Legend />
                            <Line type="monotone" dataKey="grit" name="Grit Score" stroke="#8b5cf6" dot={false} strokeWidth={2} />
                            <Line type="monotone" dataKey="estimate" name="Runway-decay estimate %" stroke="#3b82f6" dot={false} strokeWidth={2} />
                            <Line type="monotone" dataKey="quality" name="Data quality" stroke="#22c55e" dot={false} strokeWidth={2} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>

            <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5 overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="text-xs text-gray-500 uppercase">
                        <tr className="text-left">
                            <th className="py-2 pr-4">When</th>
                            <th className="pr-4">Business</th>
                            <th className="pr-4">Period</th>
                            <th className="pr-4">Shocks (CAC / Rev / COGS)</th>
                            <th className="pr-4">Runway → shocked</th>
                            <th className="pr-4">Tier → stressed</th>
                            <th className="pr-4">Grit</th>
                            <th className="pr-4">Estimate</th>
                            <th>Quality</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={r.scenario_id} className="border-t border-white/5">
                                <td className="py-2 pr-4 text-gray-400">{new Date(r.created_at).toLocaleString()}</td>
                                <td className="pr-4">{r.business}{r.ticker ? ` (${r.ticker})` : ''}</td>
                                <td className="pr-4">{r.period_label || '—'}</td>
                                <td className="pr-4">{r.shocks.cac_shock}% / {r.shocks.rev_shock}% / {r.shocks.cogs_shock}%</td>
                                <td className="pr-4">{fmtRunway(r.runway_months)} → {fmtRunway(r.shocked_runway_months)}</td>
                                <td className="pr-4">{r.fragility_tier} → {r.stressed_tier}</td>
                                <td className="pr-4 font-bold">{r.grit_score}</td>
                                <td className="pr-4">{r.runway_decay_estimate}%</td>
                                <td>{r.quality_score} ({r.quality_issue_count})</td>
                            </tr>
                        ))}
                        {rows.length === 0 && !error && (
                            <tr><td colSpan={9} className="py-6 text-gray-500">No analyses saved yet.</td></tr>
                        )}
                    </tbody>
                </table>
            </div>
        </Layout>
    );
}
