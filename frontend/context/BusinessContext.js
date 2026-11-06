import React, { createContext, useContext, useState, useEffect } from 'react';
import { API_URL } from '../lib/api';

const BusinessContext = createContext();

export const useBusiness = () => useContext(BusinessContext);

export const BusinessProvider = ({ children }) => {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState(null);
    const [business, setBusiness] = useState({
        business_name: 'My business',  // groups saved scenarios on the History page
        currency: 'INR',  // 'INR' | 'USD' — backend schemas.FullBusinessState
        revenue: 1000000,
        top_platform_rev: 800000,
        ad_spend: 300000,
        cogs: 400000,
        shipping_cost: 50000,
        rto_cost: 20000,
        fixed_costs: 150000,
        cash_in_bank: 500000,
        stock_units: 5000,
        cost_per_unit: 400,
        daily_velocity: 100,
        top_supplier_spend: 200000,
        total_purchases: 300000,
        platform_shares: null,  // optional % list -> exact HHI (backend dependency_index.py)
        supplier_shares: null,
    });

    const [shocks, setShocks] = useState({
        cac_shock: 0,
        rev_shock: 0,
        cogs_shock: 0,
        ad_spend_behaviour: 'fixed'  // 'fixed' | 'scales' — see backend shock_engine.apply_shocks
    });

    const [chatMessages, setChatMessages] = useState([
        { role: 'model', content: "Hello! I'm your GritOS Strategic Partner. I've analyzed your current business metrics and I'm ready to help you optimize for growth and resilience. What's on your mind today?" }
    ]);

    const fetchAnalysis = async (currentBusiness = business, currentShocks = shocks) => {
        setLoading(true);
        try {
            const response = await fetch(`${API_URL}/api/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...currentBusiness, ...currentShocks })
            });
            if (response.ok) {
                const result = await response.json();
                setData(result);
            } else if (response.status === 422) {
                // Validation errors from backend schemas.py: show them instead of a generic failure
                const body = await response.json();
                const messages = (body.detail || []).map((e) => `${(e.loc || []).slice(1).join('.') || 'input'}: ${e.msg}`);
                setData({ error: true, message: 'Invalid input', details: messages });
            } else {
                setData({ error: true, message: "Engine Offline" });
            }
        } catch (err) {
            setData({ error: true, message: "Connection Error" });
        } finally {
            setLoading(false);
        }
    };

    const randomizeMockData = async () => {
        setLoading(true);
        try {
            const response = await fetch(`${API_URL}/api/mock`);
            const mockBiz = await response.json();
            // Keep name, currency and share lists; the [business, shocks] effect re-runs the analysis once.
            setBusiness((prev) => ({ ...prev, ...mockBiz }));
        } catch (err) {
            console.error("Mock fetch error", err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const handler = setTimeout(() => {
            fetchAnalysis();
        }, 300);
        return () => clearTimeout(handler);
    }, [shocks, business]);

    return (
        <BusinessContext.Provider value={{
            business, setBusiness,
            shocks, setShocks,
            data, setData,
            loading, setLoading,
            chatMessages, setChatMessages,
            fetchAnalysis,
            randomizeMockData
        }}>
            {children}
        </BusinessContext.Provider>
    );
};
