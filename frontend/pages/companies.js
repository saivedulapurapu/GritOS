import React, { useEffect, useState } from 'react';
import Layout from '../components/Layout';
import DataQualityCard from '../components/DataQualityCard';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceLine } from 'recharts';

const API = 'http://localhost:8000';

const BADGE = {
    REAL: 'bg-green-500/15 text-green-300 border-green-500/30',
    DERIVED: 'bg-blue-500/15 text-blue-300 border-blue-500/30',
    PROXY: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30',
    ASSUMED: 'bg-gray-500/15 text-gray-300 border-gray-500/30',
    MISSING: 'bg-red-500/15 text-red-300 border-red-500/30',
};

const INPUT_ROWS = [
    ['revenue', 'Revenue / month', 'revenue'],
    ['cogs', 'COGS / month', 'cogs'],
    ['ad_spend', 'Ad spend / month', 'ad_spend'],
    ['fixed_costs', 'Fixed costs / month', 'fixed_costs'],
    ['shipping_cost', 'Shipping / month', 'shipping_cost'],
    ['rto_cost', 'Returns / month', 'rto_cost'],
    ['cash_in_bank', 'Cash at quarter end', 'cash_in_bank'],
    ['stock_units', 'Inventory at cost ($)', 'stock_units'],
    ['daily_velocity', 'COGS per day ($)', 'daily_velocity'],
    [null, 'Platform / supplier concentration', 'concentration'],
];

const usd = (v) => (v === null || v === undefined ? '—' : `$${Math.round(v).toLocaleString()}`);
const musd = (v) => (v === null || v === undefined ? null : Math.round(v / 1e5) / 10);

export default function Companies() {
    const [companies, setCompanies] = useState([]);
    const [ticker, setTicker] = useState('');
    const [quarters, setQuarters] = useState([]);
    const [quarter, setQuarter] = useState('');
    const [shocks, setShocks] = useState({ cac_shock: 0, rev_shock: 0, cogs_shock: 0, ad_spend_behaviour: 'fixed' });
    const [result, setResult] = useState(null);
    const [validation, setValidation] = useState(null);
    const [error, setError] = useState(null);

    useEffect(() => {
        fetch(`${API}/api/companies`).then((r) => r.json()).then((cs) => {
            setCompanies(cs);
            if (cs.length) setTicker(cs[0].ticker);
        }).catch((e) => setError(`Could not load companies: ${e.message}`));
    }, []);

    useEffect(() => {
        if (!ticker) return;
        setResult(null);
        fetch(`${API}/api/companies/${ticker}/quarters`).then((r) => r.json()).then((qs) => {
            const usable = qs.filter((q) => q.analysable);
            setQuarters(usable);
            setQuarter(usable.length ? usable[usable.length - 1].quarter : '');
        });
        fetch(`${API}/api/validation?ticker=${ticker}`).then((r) => r.json()).then(setValidation);
    }, [ticker]);

    const analyse = async () => {
        setError(null);
        const r = await fetch(`${API}/api/analyze/company/${ticker}?quarter=${quarter}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(shocks),
        });
        const body = await r.json();
        if (!r.ok) {
            setError(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail));
            return;
        }
        setResult(body);
    };

    const chartData = (validation?.rows || []).map((r) => ({
        quarter: r.quarter,
        gritos: musd(r.gritos_monthly_net),
        ocf: musd(r.ocf_monthly),
        addback: r.error_after_addback === null ? null : musd(r.ocf_monthly + r.error_after_addback),
    }));
    const v = validation?.overall;

    return (
        <Layout>
            <div className="mb-8">
                <h1 className="text-4xl font-black tracking-tight mb-2">Real Companies (SEC EDGAR)</h1>
                <p className="text-gray-400">
                    Quarterly figures from 10-K / 10-Q filings, normalised and mapped to GritOS inputs. Every input shows where it came from.
                </p>
            </div>

            {error && <div className="mb-6 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-sm text-red-300">{error}</div>}
            {companies.length === 0 && !error && (
                <div className="mb-6 text-gray-400 text-sm">No companies loaded. Run the EDGAR ETL (see backend/etl/README.md).</div>
            )}

            <div className="p-6 rounded-3xl bg-[#11131a] border border-white/5 mb-8 flex flex-wrap gap-4 items-end">
                <label className="text-xs text-gray-500 uppercase">Company
                    <select value={ticker} onChange={(e) => setTicker(e.target.value)} className="block mt-1 bg-[#0a0b10] border border-white/10 rounded-xl px-3 py-2 text-white text-sm">
                        {companies.map((c) => <option key={c.ticker} value={c.ticker}>{c.ticker} — {c.name}</option>)}
                    </select>
                </label>
                <label className="text-xs text-gray-500 uppercase">Quarter (by period end)
                    <select value={quarter} onChange={(e) => setQuarter(e.target.value)} className="block mt-1 bg-[#0a0b10] border border-white/10 rounded-xl px-3 py-2 text-white text-sm">
                        {quarters.map((q) => <option key={q.quarter} value={q.quarter}>{q.quarter}</option>)}
                    </select>
                </label>
                {[['rev_shock', 'Revenue drop %', 100], ['cac_shock', 'CAC spike %', 300], ['cogs_shock', 'COGS rise %', 300]].map(([id, label, max]) => (
                    <label key={id} className="text-xs text-gray-500 uppercase">{label}
                        <input type="number" min={0} max={max} value={shocks[id]}
                            onChange={(e) => setShocks({ ...shocks, [id]: Math.min(max, Math.max(0, parseFloat(e.target.value) || 0)) })}
                            className="block mt-1 w-28 bg-[#0a0b10] border border-white/10 rounded-xl px-3 py-2 text-white text-sm" />
                    </label>
                ))}
                <label className="text-xs text-gray-500 uppercase">Ad spend when revenue falls
                    <select value={shocks.ad_spend_behaviour} onChange={(e) => setShocks({ ...shocks, ad_spend_behaviour: e.target.value })} className="block mt-1 bg-[#0a0b10] border border-white/10 rounded-xl px-3 py-2 text-white text-sm">
                        <option value="fixed">stays fixed</option>
                        <option value="scales">scales with volume</option>
                    </select>
                </label>
                <button onClick={analyse} disabled={!quarter} className="px-6 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-blue-600 font-bold text-white disabled:opacity-40">
                    Analyse
                </button>
            </div>

            {result && (
                <>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                        {[
                            ['Grit Score', `${result.grit_score} / 100`],
                            ['Runway-decay estimate (6 mo)', `${result.runway_decay_estimate}%`],
                            ['Runway → shocked', `${result.baseline.runway_months ?? '∞'} → ${result.simulation.runway ?? '∞'} mo`],
                            ['Tier', `${result.fragility.class} → ${result.fragility.stressed_class}`],
                        ].map(([label, value]) => (
                            <div key={label} className="p-5 rounded-2xl bg-[#11131a] border border-white/5">
                                <div className="text-xs text-gray-500 uppercase mb-1">{label}</div>
                                <div className="text-xl font-bold">{value}</div>
                            </div>
                        ))}
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-8">
                        <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5 overflow-x-auto">
                            <h3 className="text-xl font-bold mb-1">Inputs — {result.company.name}, {result.quarter}</h3>
                            <p className="text-xs text-gray-500 mb-4">Period {result.period.start} → {result.period.end}. Monthly values are quarterly / 3.</p>
                            <table className="w-full text-sm">
                                <tbody>
                                    {INPUT_ROWS.map(([key, label, provKey]) => {
                                        const p = result.provenance[provKey];
                                        return (
                                            <tr key={label} className="border-t border-white/5 align-top">
                                                <td className="py-2 pr-3 text-gray-400">{label}</td>
                                                <td className="py-2 pr-3 font-mono">{key ? usd(result.inputs[key]) : '—'}</td>
                                                <td className="py-2 pr-3">
                                                    <span className={`px-2 py-0.5 rounded-md border text-[10px] font-bold ${BADGE[p.status]}`}>{p.status}</span>
                                                </td>
                                                <td className="py-2 text-xs text-gray-500">{p.note}</td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                            {result.adjustments.length > 0 && (
                                <div className="mt-4 text-xs text-yellow-300">Adjustments: {result.adjustments.join('; ')}</div>
                            )}
                        </div>
                        <DataQualityCard report={result.data_quality} />
                    </div>
                </>
            )}

            <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
                <h3 className="text-xl font-bold mb-1">Validation: GritOS monthly net vs reported operating cash flow ({ticker})</h3>
                <p className="text-sm text-gray-500 mb-4">
                    $M per month. GritOS net = operating income; the gap is mostly non-cash stock comp and D&A, plus working capital.
                    {v && v.quarters > 0 && ` Median |error| ${v.median_abs_error_pct_revenue}% of revenue (${v.median_abs_error_pct_revenue_after_addback}% after adding back SBC + D&A), ${v.quarters} quarters.`}
                </p>
                <div className="h-[320px]">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" />
                            <XAxis dataKey="quarter" stroke="#64748b" fontSize={11} />
                            <YAxis stroke="#64748b" fontSize={11} unit="M" />
                            <Tooltip contentStyle={{ background: '#1e293b', border: 'none' }} formatter={(val) => (val === null ? '—' : `$${val}M`)} />
                            <Legend />
                            <ReferenceLine y={0} stroke="#ffffff30" />
                            <Line type="monotone" dataKey="gritos" name="GritOS net / month" stroke="#8b5cf6" strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="ocf" name="Operating cash flow / month" stroke="#22c55e" strokeWidth={2} dot={false} />
                            <Line type="monotone" dataKey="addback" name="GritOS net + SBC + D&A" stroke="#3b82f6" strokeDasharray="4 3" dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </div>
        </Layout>
    );
}
