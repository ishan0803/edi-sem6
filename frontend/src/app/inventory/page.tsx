"use client";
import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, Cpu, Play, RefreshCw, TrendingUp, AlertTriangle, CheckCircle, ArrowRightLeft, BarChart3, Activity } from "lucide-react";
import { trainSynthetic, getInventoryRecommendations, getInventoryData } from "@/lib/api";
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
    LineChart, Line, Area, AreaChart,
} from "recharts";

const TERMINAL_MESSAGES = [
    "Initializing synthetic market engine...",
    "Generating 30-day demand time-series...",
    "Injecting localized demand spikes (heatwave → water +250%)...",
    "Simulating weekend consumption patterns...",
    "Creating inter-store stock imbalances...",
    "Building bipartite store-SKU graph...",
    "Training 2-layer GCN (100 epochs)...",
    "Computing loss gradients...",
    "Generating transfer weight matrix...",
    "Model converged. Extracting recommendations...",
];

export default function InventoryPortal() {
    const [training, setTraining] = useState(false);
    const [trained, setTrained] = useState(false);
    const [terminalLines, setTerminalLines] = useState<string[]>([]);
    const [recommendations, setRecommendations] = useState<any>(null);
    const [chartData, setChartData] = useState<any>(null);
    const [trainResult, setTrainResult] = useState<any>(null);

    const runSimulation = async () => {
        setTraining(true);
        setTerminalLines([]);
        setTrained(false);
        setRecommendations(null);
        setChartData(null);

        // Animate terminal messages
        for (let i = 0; i < TERMINAL_MESSAGES.length; i++) {
            await new Promise(r => setTimeout(r, 400 + Math.random() * 300));
            setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${TERMINAL_MESSAGES[i]}`]);
        }

        try {
            const result = await trainSynthetic();
            setTrainResult(result);
            setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ✓ Training complete. ${result.stores_processed} stores × ${result.skus_simulated} SKUs × ${result.days_simulated} days.`]);

            // Fetch recommendations
            const recs = await getInventoryRecommendations();
            setRecommendations(recs);

            // Fetch chart data
            const data = await getInventoryData();
            setChartData(data);

            setTrained(true);
            setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ✓ Dashboard loaded. ${recs.transfers?.length || 0} transfer recommendations generated.`]);
        } catch (e: any) {
            setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ✗ Error: ${e.message}`]);
        }
        setTraining(false);
    };

    // Aggregate chart data by store
    const storeBarData = recommendations?.store_summaries?.map((s: any) => ({
        name: s.store_name?.substring(0, 12) || s.store_id,
        stock: s.total_avg_stock,
        demand: s.total_avg_demand,
        predicted: s.total_predicted_demand,
    })) || [];

    // Build daily trend from chartData
    const dailyTrend = (() => {
        if (!chartData?.daily_aggregates) return [];
        const byDate: Record<string, { date: string; orders: number; stock: number }> = {};
        for (const r of chartData.daily_aggregates) {
            if (!byDate[r.date]) byDate[r.date] = { date: r.date, orders: 0, stock: 0 };
            byDate[r.date].orders += r.total_orders;
            byDate[r.date].stock += r.total_stock;
        }
        return Object.values(byDate).sort((a, b) => a.date.localeCompare(b.date))
            .map(d => ({ ...d, date: d.date.slice(5) })); // trim year for display
    })();

    const metrics = recommendations?.metrics;

    return (
        <div className="h-full flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-[#121214]">
                <div className="flex items-center gap-4">
                    <Link href="/dashboard" className="p-2 rounded-lg hover:bg-white/5 transition-colors">
                        <ArrowLeft size={20} className="text-gray-400" />
                    </Link>
                    <div>
                        <h1 className="text-lg font-bold flex items-center gap-2">
                            <Cpu size={20} className="text-purple-400" />
                            Inventory Intelligence Portal
                        </h1>
                        <p className="text-xs text-gray-500">GNN-Powered Demand Prediction & Rebalancing</p>
                    </div>
                </div>
                <button onClick={runSimulation} disabled={training}
                    className={`px-5 py-2.5 rounded-xl font-semibold text-sm flex items-center gap-2 transition-all ${
                        training ? 'bg-purple-600/50 cursor-wait' : 'bg-purple-600 hover:bg-purple-700 shadow-[0_0_30px_rgba(168,85,247,0.3)] hover:shadow-[0_0_40px_rgba(168,85,247,0.5)]'}`}>
                    {training ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
                    {training ? 'Training...' : 'Run Market Simulation'}
                </button>
            </div>

            <div className="flex-1 overflow-y-auto">
                <div className="max-w-7xl mx-auto p-6 space-y-6">

                    {/* Terminal Output */}
                    {terminalLines.length > 0 && (
                        <div className="rounded-2xl bg-[#0d0d0f] border border-white/10 overflow-hidden">
                            <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10 bg-white/[0.02]">
                                <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                                <span className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
                                <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                                <span className="text-xs text-gray-500 ml-2 font-mono">gnn-pipeline</span>
                            </div>
                            <div className="p-4 font-mono text-xs space-y-1 max-h-60 overflow-y-auto">
                                {terminalLines.map((line, i) => (
                                    <div key={i} className={`${line.includes('✓') ? 'text-emerald-400' : line.includes('✗') ? 'text-red-400' : 'text-gray-400'}`}>
                                        {line}
                                    </div>
                                ))}
                                {training && <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse" />}
                            </div>
                        </div>
                    )}

                    {/* Metrics Cards */}
                    {trained && metrics && (
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                            <MetricCard icon={<AlertTriangle className="text-yellow-400" size={20} />}
                                label="Stockouts Prevented" value={metrics.stockouts_prevented} color="yellow" />
                            <MetricCard icon={<ArrowRightLeft className="text-blue-400" size={20} />}
                                label="Units Shifted" value={Math.round(metrics.total_value_shifted)} color="blue" />
                            <MetricCard icon={<CheckCircle className="text-emerald-400" size={20} />}
                                label="Network Balance" value={`${metrics.network_balance_score}%`} color="emerald" />
                            <MetricCard icon={<Activity className="text-purple-400" size={20} />}
                                label="Model Loss" value={metrics.model_loss?.toFixed(4) || 'N/A'} color="purple" />
                        </div>
                    )}

                    {/* Charts */}
                    {trained && (
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            {/* Stock vs Demand per Store */}
                            {storeBarData.length > 0 && (
                                <div className="rounded-2xl bg-[#121214] border border-white/10 p-6">
                                    <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 mb-4 flex items-center gap-2">
                                        <BarChart3 size={16} className="text-blue-400" /> Stock vs Demand by Store
                                    </h3>
                                    <ResponsiveContainer width="100%" height={300}>
                                        <BarChart data={storeBarData} barGap={2}>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                                            <XAxis dataKey="name" tick={{ fill: '#666', fontSize: 11 }} />
                                            <YAxis tick={{ fill: '#666', fontSize: 11 }} />
                                            <Tooltip contentStyle={{ backgroundColor: '#1a1a1d', border: '1px solid #333', borderRadius: '12px', fontSize: 12 }}
                                                labelStyle={{ color: '#999' }} />
                                            <Legend wrapperStyle={{ fontSize: 11 }} />
                                            <Bar dataKey="stock" fill="#3b82f6" name="Avg Stock" radius={[4,4,0,0]} />
                                            <Bar dataKey="demand" fill="#f97316" name="Avg Demand" radius={[4,4,0,0]} />
                                            <Bar dataKey="predicted" fill="#a855f7" name="Predicted" radius={[4,4,0,0]} />
                                        </BarChart>
                                    </ResponsiveContainer>
                                </div>
                            )}

                            {/* Daily Trend */}
                            {dailyTrend.length > 0 && (
                                <div className="rounded-2xl bg-[#121214] border border-white/10 p-6">
                                    <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 mb-4 flex items-center gap-2">
                                        <TrendingUp size={16} className="text-emerald-400" /> 30-Day Demand Trend
                                    </h3>
                                    <ResponsiveContainer width="100%" height={300}>
                                        <AreaChart data={dailyTrend}>
                                            <defs>
                                                <linearGradient id="colorOrders" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#f97316" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="#f97316" stopOpacity={0} />
                                                </linearGradient>
                                                <linearGradient id="colorStock" x1="0" y1="0" x2="0" y2="1">
                                                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                                                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                                                </linearGradient>
                                            </defs>
                                            <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                                            <XAxis dataKey="date" tick={{ fill: '#666', fontSize: 10 }} />
                                            <YAxis tick={{ fill: '#666', fontSize: 11 }} />
                                            <Tooltip contentStyle={{ backgroundColor: '#1a1a1d', border: '1px solid #333', borderRadius: '12px', fontSize: 12 }}
                                                labelStyle={{ color: '#999' }} />
                                            <Legend wrapperStyle={{ fontSize: 11 }} />
                                            <Area type="monotone" dataKey="stock" stroke="#3b82f6" fill="url(#colorStock)" name="Stock" strokeWidth={2} />
                                            <Area type="monotone" dataKey="orders" stroke="#f97316" fill="url(#colorOrders)" name="Orders" strokeWidth={2} />
                                        </AreaChart>
                                    </ResponsiveContainer>
                                </div>
                            )}
                        </div>
                    )}

                    {/* Transfer Recommendations */}
                    {trained && recommendations?.transfers && recommendations.transfers.length > 0 && (
                        <div className="rounded-2xl bg-[#121214] border border-white/10 p-6">
                            <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 mb-4 flex items-center gap-2">
                                <ArrowRightLeft size={16} className="text-cyan-400" /> GNN Transfer Recommendations
                            </h3>
                            <div className="overflow-x-auto">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-white/10">
                                            <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase">SKU</th>
                                            <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase">From Store</th>
                                            <th className="text-center py-3 px-4 text-gray-500 font-medium text-xs uppercase">→</th>
                                            <th className="text-left py-3 px-4 text-gray-500 font-medium text-xs uppercase">To Store</th>
                                            <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">Qty</th>
                                            <th className="text-right py-3 px-4 text-gray-500 font-medium text-xs uppercase">Priority</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {recommendations.transfers.map((t: any, i: number) => (
                                            <tr key={i} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                                                <td className="py-3 px-4">
                                                    <span className="text-white font-medium">{t.sku_name}</span>
                                                    <span className="text-gray-500 text-xs ml-1">({t.sku_id})</span>
                                                </td>
                                                <td className="py-3 px-4 text-orange-400">{t.from_name || t.from_store}</td>
                                                <td className="py-3 px-4 text-center text-gray-600">→</td>
                                                <td className="py-3 px-4 text-emerald-400">{t.to_name || t.to_store}</td>
                                                <td className="py-3 px-4 text-right font-mono text-white">{t.transfer_qty}</td>
                                                <td className="py-3 px-4 text-right">
                                                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                                                        t.priority === 'high' ? 'bg-red-500/20 text-red-400' : 'bg-yellow-500/20 text-yellow-400'}`}>
                                                        {t.priority}
                                                    </span>
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    )}

                    {/* Empty State */}
                    {!trained && terminalLines.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-32 text-center">
                            <div className="w-24 h-24 rounded-3xl bg-purple-600/10 border border-purple-500/20 flex items-center justify-center mb-6">
                                <Cpu size={40} className="text-purple-400" />
                            </div>
                            <h2 className="text-2xl font-bold mb-3">Inventory Intelligence Engine</h2>
                            <p className="text-gray-400 max-w-md mb-8 leading-relaxed">
                                Generate synthetic market demand data across your dark stores and train a Graph Neural Network to predict optimal inventory rebalancing flows.
                            </p>
                            <button onClick={runSimulation}
                                className="px-8 py-4 bg-purple-600 hover:bg-purple-700 rounded-xl font-semibold flex items-center gap-3 transition-all shadow-[0_0_40px_rgba(168,85,247,0.3)] hover:shadow-[0_0_60px_rgba(168,85,247,0.5)]">
                                <Play size={20} /> Run Market Simulation
                            </button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

function MetricCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: any; color: string }) {
    const borderColors: Record<string, string> = {
        yellow: 'border-yellow-500/20', blue: 'border-blue-500/20',
        emerald: 'border-emerald-500/20', purple: 'border-purple-500/20',
    };
    return (
        <div className={`rounded-2xl bg-[#121214] border ${borderColors[color] || 'border-white/10'} p-5`}>
            <div className="flex items-center gap-3 mb-3">{icon}<span className="text-xs text-gray-400 uppercase tracking-wider">{label}</span></div>
            <div className="text-3xl font-bold font-mono">{value}</div>
        </div>
    );
}
