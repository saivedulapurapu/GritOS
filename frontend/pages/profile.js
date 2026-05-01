import React from 'react';
import Layout from '../components/Layout';
import { useBusiness } from '../context/BusinessContext';
import { Save, Info } from 'lucide-react';

export default function Profile() {
    const { business, setBusiness, fetchAnalysis, loading } = useBusiness();

    const handleChange = (field, value) => {
        const numValue = parseFloat(value) || 0;
        const newBusiness = { ...business, [field]: numValue };
        setBusiness(newBusiness);
    };

    const inputGroups = [
        {
            title: 'Revenue & Sales',
            fields: [
                { id: 'revenue', label: 'Monthly Revenue (₹)', type: 'number' },
            ]
        },
        {
            title: 'Variable Costs',
            fields: [
                { id: 'ad_spend', label: 'Ad Spend (CAC) (₹)', type: 'number' },
                { id: 'cogs', label: 'COGS (₹)', type: 'number' },
                { id: 'shipping_cost', label: 'Shipping Cost (₹)', type: 'number' },
                { id: 'rto_cost', label: 'RTO (Returns) Cost (₹)', type: 'number' },
            ]
        },
        {
            title: 'Overheads & Liquidity',
            fields: [
                { id: 'fixed_costs', label: 'Fixed Costs (Rent/Salaries) (₹)', type: 'number' },
                { id: 'cash_in_bank', label: 'Cash in Bank (₹)', type: 'number' },
            ]
        }
    ];

    return (
        <Layout>
            <div className="flex justify-between items-center mb-10">
                <div>
                    <h1 className="text-4xl font-black tracking-tight mb-2">Financial Profile</h1>
                    <p className="text-gray-400">Manage your core business metrics and cost structure.</p>
                </div>
                <button
                    onClick={() => fetchAnalysis()}
                    disabled={loading}
                    className={`px-8 py-3 bg-white text-black rounded-xl font-bold flex items-center gap-2 hover:bg-gray-200 transition-all ${loading ? 'opacity-50 cursor-not-not-allowed' : ''}`}
                >
                    <Save size={18} />
                    {loading ? 'Recalculating...' : 'Update Baseline'}
                </button>
            </div>

            <div className="grid grid-cols-1 gap-10">
                {inputGroups.map((group) => (
                    <div key={group.title} className="p-8 rounded-3xl bg-[#11131a] border border-white/5">
                        <h3 className="text-xl font-bold mb-8 flex items-center gap-2">
                            <div className="w-1 h-6 bg-purple-500 rounded-full"></div>
                            {group.title}
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                            {group.fields.map((field) => (
                                <div key={field.id} className="space-y-3">
                                    <div className="flex items-center justify-between">
                                        <label htmlFor={field.id} className="text-sm font-bold text-gray-400 uppercase tracking-wider">{field.label}</label>
                                        <Info size={14} className="text-gray-600 hover:text-purple-400 cursor-help" />
                                    </div>
                                    <input
                                        id={field.id}
                                        type={field.type}
                                        value={business[field.id]}
                                        onChange={(e) => handleChange(field.id, e.target.value)}
                                        className="w-full bg-[#0a0b10] border border-white/10 rounded-xl px-5 py-4 text-xl font-mono text-white focus:outline-none focus:border-purple-500/50 focus:ring-4 focus:ring-purple-500/10 transition-all"
                                        placeholder="0.00"
                                    />
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </div>

            <div className="mt-8 p-6 rounded-2xl bg-gradient-to-r from-blue-600/10 to-purple-600/10 border border-white/5 flex items-center gap-4">
                <div className="p-3 bg-blue-500/20 rounded-full">
                    <Info className="text-blue-400" />
                </div>
                <div>
                    <h4 className="font-bold text-sm text-white">Pro Tip</h4>
                    <p className="text-sm text-gray-400">Updating these baseline values recalculates your overall Grit Score and Survival Trajectory across the entire system.</p>
                </div>
            </div>
        </Layout>
    );
}
