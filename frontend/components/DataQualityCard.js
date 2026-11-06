import React from 'react';
import { ShieldCheck } from 'lucide-react';

const SEVERITY_STYLE = {
    error: 'text-red-400',
    warning: 'text-yellow-400',
    info: 'text-gray-400',
};

// Renders the report produced by backend data_quality.py
export default function DataQualityCard({ report }) {
    if (!report) return null;
    const scoreColor = report.score >= 85 ? 'text-green-400' : report.score >= 60 ? 'text-yellow-400' : 'text-red-400';
    const issues = report.issues || [];

    return (
        <div className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-xl font-bold flex items-center gap-2">
                    <ShieldCheck size={20} className="text-purple-400" /> Data Quality
                </h3>
                <div className={`text-3xl font-black ${scoreColor}`}>
                    {report.score}<span className="text-sm text-gray-500 font-normal"> / 100</span>
                </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
                {Object.entries(report.dimensions || {}).map(([name, d]) => (
                    <div key={name} className="p-3 rounded-xl bg-white/5 border border-white/5">
                        <div className="text-xs text-gray-500 uppercase">{name}</div>
                        <div className="text-lg font-bold">{d.score}</div>
                        <div className="text-[10px] text-gray-500">weight {d.weight} · {d.issues} issue(s)</div>
                    </div>
                ))}
            </div>

            {issues.length === 0 ? (
                <p className="text-sm text-gray-400">No data-quality issues found.</p>
            ) : (
                <ul className="space-y-1 text-sm">
                    {issues.map((issue, idx) => (
                        <li key={`${issue.code}-${idx}`} className="flex gap-2">
                            <span className={`uppercase text-[10px] font-bold mt-1 w-14 shrink-0 ${SEVERITY_STYLE[issue.severity] || ''}`}>{issue.severity}</span>
                            <span className="text-gray-300">{issue.message}</span>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
