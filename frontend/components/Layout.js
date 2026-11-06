import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { BarChart3, Activity, ShieldAlert, Cpu, MessageSquare, Menu, X, Rocket, History, Building2 } from 'lucide-react';
import { useBusiness } from '../context/BusinessContext';

const Layout = ({ children }) => {
    const router = useRouter();
    const { data, loading } = useBusiness();
    const [isSidebarOpen, setIsSidebarOpen] = useState(true);

    const navItems = [
        { name: 'Overview', href: '/', icon: BarChart3 },
        { name: 'Financial Profile', href: '/profile', icon: Activity },
        { name: 'Stress Test', href: '/stress', icon: Rocket },
        { name: 'Risk Matrix', href: '/risk', icon: ShieldAlert },
        { name: 'AI Strategy', href: '/advisor', icon: MessageSquare },
        { name: 'Real Companies', href: '/companies', icon: Building2 },
        { name: 'History', href: '/history', icon: History },
    ];

    const gritColor = data?.grit_score > 70 ? 'text-green-400' : data?.grit_score > 40 ? 'text-yellow-400' : 'text-red-400';

    return (
        <div className="min-h-screen bg-[#0a0b10] text-[#e2e8f0] font-sans selection:bg-purple-500/30">
            {/* Background Effects */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-purple-900/10 rounded-full blur-[120px]"></div>
                <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-900/10 rounded-full blur-[120px]"></div>
            </div>

            {/* Sidebar */}
            <aside className={`fixed top-0 left-0 h-full bg-[#11131a]/80 backdrop-blur-xl border-r border-white/5 transition-all duration-300 z-50 ${isSidebarOpen ? 'w-64' : 'w-20'}`}>
                <div className="p-6 flex items-center justify-between border-b border-white/5 mb-6">
                    {isSidebarOpen ? (
                        <div className="flex items-center gap-2">
                            <div className="p-2 bg-gradient-to-tr from-purple-600 to-blue-600 rounded-lg">
                                <Cpu size={20} className="text-white" />
                            </div>
                            <span className="font-bold text-xl tracking-tight bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">GritOS</span>
                        </div>
                    ) : (
                        <Cpu className="text-purple-500 mx-auto" />
                    )}
                </div>

                <nav className="px-3 space-y-1">
                    {navItems.map((item) => {
                        const isActive = router.pathname === item.href;
                        const Icon = item.icon;
                        return (
                            <Link key={item.name} href={item.href} className={`flex items-center gap-4 px-4 py-3 rounded-xl transition-all group ${isActive ? 'bg-gradient-to-r from-purple-600/20 to-blue-600/20 text-white border border-white/10' : 'text-gray-400 hover:text-white hover:bg-white/5'}`}>
                                <Icon size={20} className={`${isActive ? 'text-purple-400 shadow-[0_0_10px_rgba(168,85,247,0.4)]' : 'group-hover:text-purple-400'}`} />
                                {isSidebarOpen && <span className="font-medium text-sm">{item.name}</span>}
                            </Link>
                        );
                    })}
                </nav>

                {isSidebarOpen && (
                    <div className="absolute bottom-10 left-6 right-6 p-4 rounded-2xl bg-white/5 border border-white/5">
                        <div className="text-xs text-gray-500 mb-2 uppercase tracking-widest font-bold">Grit Score</div>
                        <div className={`text-3xl font-black ${gritColor} flex items-center gap-2`}>
                            {loading ? '---' : data?.grit_score || '0'}
                            <span className="text-xs text-gray-500 font-normal mt-2">/ 100</span>
                        </div>
                    </div>
                )}
            </aside>

            {/* Main Content */}
            <main className={`transition-all duration-300 min-h-screen ${isSidebarOpen ? 'pl-64' : 'pl-20'}`}>
                <header className="h-20 border-b border-white/5 flex items-center justify-between px-10 bg-[#0a0b10]/50 backdrop-blur-md sticky top-0 z-40">
                    <button onClick={() => setIsSidebarOpen(!isSidebarOpen)} className="p-2 hover:bg-white/5 rounded-lg text-gray-400 transition-colors">
                        {isSidebarOpen ? <X size={20} /> : <Menu size={20} />}
                    </button>

                    <div className="flex items-center gap-6">
                        {loading && <div className="animate-spin rounded-full h-4 w-4 border-2 border-purple-500 border-t-transparent"></div>}
                        <div className="h-10 w-10 rounded-full bg-gradient-to-tr from-purple-500/20 to-blue-500/20 border border-white/10 flex items-center justify-center text-xs font-bold text-white uppercase">
                            GR
                        </div>
                    </div>
                </header>

                <div className="p-10 max-w-7xl mx-auto">
                    {data?.error && (
                        <div className="mb-8 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 text-sm text-red-300">
                            <div className="font-bold">{data.message}</div>
                            {(data.details || []).map((d) => <div key={d}>{d}</div>)}
                        </div>
                    )}
                    {children}
                </div>
            </main>
        </div>
    );
};

export default Layout;
