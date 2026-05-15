"use client";
import { useState, memo } from "react";
import { Brain, Play, RefreshCw, AlertTriangle, CheckCircle, ArrowRightLeft, Activity, TrendingUp, BarChart3, DollarSign } from "lucide-react";
import { rebalanceInventory } from "@/lib/api";
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

const TERMINAL_MESSAGES = [
    "Loading hub inventory from database...",
    "Resolving SKU catalogue...",
    "Building hub-SKU bipartite graph...",
    "Computing inter-hub haversine distance matrix...",
    "Constructing node features [stock, avg, ratio, lat, lon]...",
    "Training 2-layer GCN (150 epochs)...",
    "Running gradient descent on MSE loss...",
    "Generating distance-weighted transfer recommendations...",
    "Sorting by cost-effectiveness score...",
    "Rebalancing complete. Extracting results...",
];

function RebalanceTabInner() {
    const [running, setRunning] = useState(false);
    const [done, setDone] = useState(false);
    const [terminalLines, setTerminalLines] = useState<string[]>([]);
    const [result, setResult] = useState<any>(null);

    const runRebalance = async () => {
        setRunning(true);
        setDone(false);
        setTerminalLines([]);
        setResult(null);

        for (let i = 0; i < TERMINAL_MESSAGES.length; i++) {
            await new Promise(r => setTimeout(r, 300 + Math.random() * 250));
            setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ${TERMINAL_MESSAGES[i]}`]);
        }

        try {
            const res = await rebalanceInventory();
            if (res.error) {
                setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ✗ ${res.error}`]);
            } else {
                setResult(res);
                setDone(true);
                setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ✓ ${res.transfers?.length || 0} transfer recommendations generated.`]);
            }
        } catch (e: any) {
            setTerminalLines(prev => [...prev, `[${new Date().toLocaleTimeString()}] ✗ Error: ${e.message}`]);
        }
        setRunning(false);
    };

    const metrics = result?.metrics;
    const hubBarData = result?.hub_summaries?.map((h: any) => ({
        name: h.hub_name?.substring(0, 14) || h.hub_id,
        actual: h.total_stock,
        ideal: h.ideal_stock,
    })) || [];

    const priorityColors: Record<string, string> = {
        high: "bg-red-500/20 text-red-400",
        medium: "bg-yellow-500/20 text-yellow-400",
        low: "bg-blue-500/20 text-blue-400",
    };

    return (
        <div className="flex-1 overflow-y-auto">
            <div className="max-w-6xl mx-auto p-6 space-y-6">

                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h2 className="text-2xl font-bold flex items-center gap-3">
                            <Brain size={24} className="text-purple-400" />
                            GNN Inventory Rebalancing
                        </h2>
                        <p className="text-sm text-gray-500 mt-1">Cost-effective inventory transfers using Graph Neural Networks</p>
                    </div>
                    <button onClick={runRebalance} disabled={running}
                        className={`px-6 py-3 rounded-xl font-semibold text-sm flex items-center gap-2 transition-all ${
                            running ? 'bg-purple-600/50 cursor-wait' : 'bg-purple-600 hover:bg-purple-700 shadow-[0_0_30px_rgba(168,85,247,0.3)] hover:shadow-[0_0_40px_rgba(168,85,247,0.5)]'}`}>
                        {running ? <RefreshCw size={16} className="animate-spin" /> : <Play size={16} />}
                        {running ? 'Processing...' : 'Run GNN Rebalance'}
                    </button>
                </div>

                {/* Terminal */}
                {terminalLines.length > 0 && (
                    <div className="rounded-2xl bg-[#0d0d0f] border border-white/10 overflow-hidden">
                        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-white/10 bg-white/[0.02]">
                            <span className="w-2.5 h-2.5 rounded-full bg-red-500" />
                            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
                            <span className="w-2.5 h-2.5 rounded-full bg-green-500" />
                            <span className="text-xs text-gray-500 ml-2 font-mono">gnn-rebalance</span>
                        </div>
                        <div className="p-4 font-mono text-xs space-y-1 max-h-52 overflow-y-auto">
                            {terminalLines.map((line, i) => (
                                <div key={i} className={`${line.includes('✓') ? 'text-emerald-400' : line.includes('✗') ? 'text-red-400' : 'text-gray-400'}`}>
                                    {line}
                                </div>
                            ))}
                            {running && <span className="inline-block w-2 h-4 bg-purple-400 animate-pulse" />}
                        </div>
                    </div>
                )}

                {/* Metrics */}
                {done && metrics && (
                    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                        <MetricCard icon={<AlertTriangle className="text-yellow-400" size={20} />}
                            label="Understocked Hubs" value={metrics.stockouts_prevented} color="yellow" />
                        <MetricCard icon={<ArrowRightLeft className="text-blue-400" size={20} />}
                            label="Units to Shift" value={metrics.total_units_shifted} color="blue" />
                        <MetricCard icon={<DollarSign className="text-emerald-400" size={20} />}
                            label="Transfer Cost (₹)" value={`₹${metrics.total_transfer_cost?.toLocaleString()}`} color="emerald" />
                        <MetricCard icon={<CheckCircle className="text-purple-400" size={20} />}
                            label="Network Balance" value={`${metrics.network_balance_score}%`} color="purple" />
                    </div>
                )}

                {/* Stock Distribution Chart */}
                {done && hubBarData.length > 0 && (
                    <div className="rounded-2xl bg-[#121214] border border-white/10 p-6">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 mb-4 flex items-center gap-2">
                            <BarChart3 size={16} className="text-blue-400" /> Stock Distribution vs Ideal
                        </h3>
                        <ResponsiveContainer width="100%" height={280}>
                            <BarChart data={hubBarData} barGap={4}>
                                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff08" />
                                <XAxis dataKey="name" tick={{ fill: '#666', fontSize: 11 }} />
                                <YAxis tick={{ fill: '#666', fontSize: 11 }} />
                                <Tooltip contentStyle={{ backgroundColor: '#1a1a1d', border: '1px solid #333', borderRadius: '12px', fontSize: 12 }}
                                    labelStyle={{ color: '#999' }} />
                                <Legend wrapperStyle={{ fontSize: 11 }} />
                                <Bar dataKey="actual" fill="#3b82f6" name="Actual Stock" radius={[4,4,0,0]} />
                                <Bar dataKey="ideal" fill="#a855f7" name="GNN Ideal" radius={[4,4,0,0]} />
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                )}

                {/* Transfer Recommendations */}
                {done && result?.transfers?.length > 0 && (
                    <div className="rounded-2xl bg-[#121214] border border-white/10 p-6">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 mb-4 flex items-center gap-2">
                            <ArrowRightLeft size={16} className="text-cyan-400" /> Transfer Recommendations (Cost-Optimized)
                        </h3>
                        <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="border-b border-white/10">
                                        <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase">SKU</th>
                                        <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase">From</th>
                                        <th className="text-center py-3 px-1 text-gray-500 font-medium text-xs uppercase">→</th>
                                        <th className="text-left py-3 px-3 text-gray-500 font-medium text-xs uppercase">To</th>
                                        <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase">Qty</th>
                                        <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase">Dist</th>
                                        <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase">Cost</th>
                                        <th className="text-right py-3 px-3 text-gray-500 font-medium text-xs uppercase">Priority</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {result.transfers.map((t: any, i: number) => (
                                        <tr key={i} className="border-b border-white/5 hover:bg-white/[0.02] transition-colors">
                                            <td className="py-3 px-3">
                                                <span className="text-white font-medium">{t.sku_name}</span>
                                                <span className="text-gray-600 text-xs ml-1">({t.sku_id})</span>
                                            </td>
                                            <td className="py-3 px-3 text-orange-400">{t.from_name}</td>
                                            <td className="py-3 px-1 text-center text-gray-600">→</td>
                                            <td className="py-3 px-3 text-emerald-400">{t.to_name}</td>
                                            <td className="py-3 px-3 text-right font-mono text-white">{t.transfer_qty}</td>
                                            <td className="py-3 px-3 text-right font-mono text-gray-400">{t.distance_km}km</td>
                                            <td className="py-3 px-3 text-right font-mono text-yellow-400">₹{t.estimated_cost?.toLocaleString()}</td>
                                            <td className="py-3 px-3 text-right">
                                                <span className={`text-xs px-2 py-1 rounded-full font-medium ${priorityColors[t.priority] || ''}`}>
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
                {!done && terminalLines.length === 0 && (
                    <div className="flex flex-col items-center justify-center py-24 text-center">
                        <div className="w-24 h-24 rounded-3xl bg-purple-600/10 border border-purple-500/20 flex items-center justify-center mb-6">
                            <Brain size={40} className="text-purple-400" />
                        </div>
                        <h2 className="text-2xl font-bold mb-3">GNN Rebalancing Engine</h2>
                        <p className="text-gray-400 max-w-md mb-8 leading-relaxed">
                            Run the Graph Neural Network on your real inventory data to generate cost-effective transfer recommendations weighted by hub-to-hub distance.
                        </p>
                        <button onClick={runRebalance}
                            className="px-8 py-4 bg-purple-600 hover:bg-purple-700 rounded-xl font-semibold flex items-center gap-3 transition-all shadow-[0_0_40px_rgba(168,85,247,0.3)] hover:shadow-[0_0_60px_rgba(168,85,247,0.5)]">
                            <Play size={20} /> Run GNN Rebalance
                        </button>
                    </div>
                )}
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

const RebalanceTab = memo(RebalanceTabInner);
export default RebalanceTab;
