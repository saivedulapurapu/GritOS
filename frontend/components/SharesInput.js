import React, { useEffect, useState } from 'react';

// Comma-separated percentages -> array of numbers (or null when empty).
// Validation (each 0-100, sum <= 100) happens in the backend schema; this only parses.
export const parseShares = (text) => {
    const parts = text.split(',').map((s) => s.trim()).filter(Boolean).map(Number);
    if (parts.length === 0) return null;
    return parts.every((n) => Number.isFinite(n)) ? parts : undefined; // undefined = unparseable
};

export default function SharesInput({ label, value, onChange }) {
    const [text, setText] = useState((value || []).join(', '));
    const [invalid, setInvalid] = useState(false);

    useEffect(() => {
        setText((value || []).join(', '));
    }, [value]);

    return (
        <label className="block text-xs font-bold text-gray-500 uppercase tracking-tighter">
            {label}
            <input
                value={text}
                placeholder="e.g. 60, 25, 15"
                onChange={(e) => setText(e.target.value)}
                onBlur={() => {
                    const parsed = parseShares(text);
                    setInvalid(parsed === undefined);
                    if (parsed !== undefined) onChange(parsed);
                }}
                className={`w-full mt-1 bg-[#0a0b10] border rounded-xl px-4 py-2 text-sm font-mono text-white outline-none ${invalid ? 'border-red-500/60' : 'border-white/10'}`}
            />
            {invalid && <span className="normal-case text-red-400 font-normal">Enter numbers separated by commas</span>}
        </label>
    );
}
