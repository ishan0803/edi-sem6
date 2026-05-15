"use client";
import { useState, useEffect, useRef, memo } from "react";
import { Plus, Trash2, Package, RefreshCw, Tag, X, ChevronDown, ChevronRight, Boxes } from "lucide-react";
import {
    Centre, SKU, HubInventorySummary,
    listSKUs, createSKU, deleteSKU,
    getAllInventory, upsertStock, deleteStock,
} from "@/lib/api";

interface InventoryTabProps {
    centres: Centre[];
}

/* ── Collapsible hub card with smooth height animation ──────────────────── */
function HubCard({
    hub,
    isOpen,
    onToggle,
    onDeleteStock,
}: {
    hub: HubInventorySummary;
    isOpen: boolean;
    onToggle: () => void;
    onDeleteStock: (id: number) => void;
}) {
    const contentRef = useRef<HTMLDivElement>(null);
    const [height, setHeight] = useState(0);

    useEffect(() => {
        if (isOpen && contentRef.current) {
            setHeight(contentRef.current.scrollHeight);
        } else {
            setHeight(0);
        }
    }, [isOpen, hub.items.length]);

    const stockLevel = hub.total_quantity === 0 ? "empty" :
        hub.total_skus < 3 ? "low" : "good";
    const dotColor = stockLevel === "good" ? "bg-green-500" :
        stockLevel === "low" ? "bg-yellow-500" : "bg-red-500";

    return (
        <div className={`rounded-2xl bg-[#121214] border transition-colors duration-200 ${
            isOpen ? 'border-blue-500/30' : 'border-white/10 hover:border-white/20'
        }`}>
            {/* Header — always visible */}
            <button
                onClick={onToggle}
                className="w-full flex items-center justify-between p-5 text-left group"
            >
                <div className="flex items-center gap-4">
                    <div className={`w-11 h-11 rounded-xl flex items-center justify-center transition-colors duration-200 ${
                        isOpen ? 'bg-blue-600/20 border border-blue-500/30' : 'bg-white/5 border border-white/10'
                    }`}>
                        <Boxes size={20} className={isOpen ? 'text-blue-400' : 'text-gray-500'} />
                    </div>
                    <div>
                        <div className="font-semibold text-white flex items-center gap-2">
                            {hub.hub_name}
                            <span className={`w-2 h-2 rounded-full ${dotColor}`} />
                        </div>
                        <div className="text-xs text-gray-500 mt-0.5">
                            {hub.total_skus} SKU{hub.total_skus !== 1 ? 's' : ''} · {hub.total_quantity} units
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {!isOpen && hub.items.length > 0 && (
                        <div className="hidden sm:flex gap-1">
                            {hub.items.slice(0, 3).map(item => (
                                <span key={item.id} className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-gray-400">
                                    {item.sku_name?.split(' ')[0]}
                                </span>
                            ))}
                            {hub.items.length > 3 && (
                                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 text-gray-500">
                                    +{hub.items.length - 3}
                                </span>
                            )}
                        </div>
                    )}
                    <ChevronDown
                        size={18}
                        className={`text-gray-500 transition-transform duration-300 ${isOpen ? 'rotate-180' : ''}`}
                    />
                </div>
            </button>

            {/* Expandable content — animated height */}
            <div
                className="overflow-hidden transition-[max-height] duration-300 ease-in-out"
                style={{ maxHeight: isOpen ? `${height + 20}px` : '0px' }}
            >
                <div ref={contentRef} className="border-t border-white/5 px-5 pb-5">
                    {hub.items.length === 0 ? (
                        <div className="text-sm text-gray-500 py-6 text-center">
                            No stock at this hub. Use &quot;Add Stock&quot; above.
                        </div>
                    ) : (
                        <table className="w-full text-sm mt-3">
                            <thead>
                                <tr className="border-b border-white/10">
                                    <th className="text-left py-2.5 text-gray-500 text-xs uppercase font-medium">Product</th>
                                    <th className="text-left py-2.5 text-gray-500 text-xs uppercase font-medium hidden sm:table-cell">SKU ID</th>
                                    <th className="text-right py-2.5 text-gray-500 text-xs uppercase font-medium">Qty</th>
                                    <th className="text-right py-2.5 text-gray-500 text-xs uppercase font-medium w-10"></th>
                                </tr>
                            </thead>
                            <tbody>
                                {hub.items.map(item => (
                                    <tr key={item.id} className="border-b border-white/5 group/row hover:bg-white/[0.02] transition-colors">
                                        <td className="py-3">
                                            <span className="text-white">{item.sku_name}</span>
                                        </td>
                                        <td className="py-3 hidden sm:table-cell">
                                            <span className="text-gray-600 text-xs font-mono">{item.sku_id}</span>
                                        </td>
                                        <td className="py-3 text-right">
                                            <span className={`font-mono font-medium ${
                                                item.quantity > 50 ? 'text-green-400' :
                                                item.quantity > 10 ? 'text-yellow-400' :
                                                'text-red-400'
                                            }`}>
                                                {item.quantity}
                                            </span>
                                        </td>
                                        <td className="py-3 text-right">
                                            <button onClick={() => onDeleteStock(item.id)}
                                                className="text-gray-600 hover:text-red-400 transition-colors p-1 opacity-0 group-hover/row:opacity-100">
                                                <Trash2 size={13} />
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ── Main Inventory Tab ──────────────────────────────────────────────────── */
function InventoryTabInner({ centres }: InventoryTabProps) {
    const [skus, setSkus] = useState<SKU[]>([]);
    const [inventory, setInventory] = useState<HubInventorySummary[]>([]);
    const [loading, setLoading] = useState(false);

    // SKU form
    const [skuId, setSkuId] = useState("");
    const [skuName, setSkuName] = useState("");
    const [skuCategory, setSkuCategory] = useState("general");
    const [skuCost, setSkuCost] = useState("1.0");
    const [showSkuForm, setShowSkuForm] = useState(false);

    // Stock form
    const [stockHub, setStockHub] = useState("");
    const [stockSku, setStockSku] = useState("");
    const [stockQty, setStockQty] = useState("");
    const [showStockForm, setShowStockForm] = useState(false);

    // Multi-expand: Set of open hub IDs
    const [openHubs, setOpenHubs] = useState<Set<string>>(new Set());

    const toggleHub = (hubId: string) => {
        setOpenHubs(prev => {
            const next = new Set(prev);
            if (next.has(hubId)) {
                next.delete(hubId);
            } else {
                next.add(hubId);
            }
            return next;
        });
    };

    const expandAll = () => setOpenHubs(new Set(inventory.map(h => h.hub_id)));
    const collapseAll = () => setOpenHubs(new Set());

    const loadData = async () => {
        setLoading(true);
        try {
            const [s, inv] = await Promise.all([listSKUs(), getAllInventory()]);
            setSkus(s);
            setInventory(inv);
        } catch (e) { console.error(e); }
        setLoading(false);
    };

    useEffect(() => { loadData(); }, []);

    const handleAddSku = async () => {
        if (!skuId || !skuName) return;
        try {
            await createSKU({ id: skuId, name: skuName, category: skuCategory, unit_cost: parseFloat(skuCost) || 1.0 });
            setSkuId(""); setSkuName(""); setSkuCategory("general"); setSkuCost("1.0");
            setShowSkuForm(false);
            await loadData();
        } catch (e: any) { alert(e?.response?.data?.detail || "Error adding SKU"); }
    };

    const handleDeleteSku = async (id: string) => {
        if (!confirm(`Delete SKU ${id} and all its inventory?`)) return;
        try { await deleteSKU(id); await loadData(); } catch (e) { console.error(e); }
    };

    const handleAddStock = async () => {
        if (!stockHub || !stockSku || !stockQty) return;
        try {
            await upsertStock({ hub_id: stockHub, sku_id: stockSku, quantity: parseInt(stockQty) || 0 });
            setStockQty("");
            // Auto-expand the hub we just added stock to
            setOpenHubs(prev => new Set(prev).add(stockHub));
            await loadData();
        } catch (e: any) { alert(e?.response?.data?.detail || "Error adding stock"); }
    };

    const handleDeleteStock = async (id: number) => {
        try { await deleteStock(id); await loadData(); } catch (e) { console.error(e); }
    };

    const categories = ["general", "beverages", "food", "pharma", "electronics", "personal_care", "dairy", "bakery", "snacks"];

    return (
        <div className="flex-1 overflow-y-auto">
            <div className="max-w-6xl mx-auto p-6 space-y-6">

                {/* Top Bar */}
                <div className="flex items-center justify-between flex-wrap gap-3">
                    <div>
                        <h2 className="text-2xl font-bold">Inventory Management</h2>
                        <p className="text-sm text-gray-500 mt-1">Manage SKU catalogue and hub stock levels</p>
                    </div>
                    <div className="flex gap-2 flex-wrap">
                        <button onClick={() => setShowSkuForm(!showSkuForm)}
                            className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors ${showSkuForm ? 'bg-red-600 hover:bg-red-700' : 'bg-purple-600 hover:bg-purple-700'}`}>
                            {showSkuForm ? <X size={16} /> : <Tag size={16} />}
                            {showSkuForm ? 'Cancel' : 'Add SKU'}
                        </button>
                        <button onClick={() => setShowStockForm(!showStockForm)}
                            className={`px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition-colors ${showStockForm ? 'bg-red-600 hover:bg-red-700' : 'bg-blue-600 hover:bg-blue-700'}`}>
                            {showStockForm ? <X size={16} /> : <Package size={16} />}
                            {showStockForm ? 'Cancel' : 'Add Stock'}
                        </button>
                        <button onClick={loadData} disabled={loading}
                            className="px-4 py-2 rounded-xl text-sm font-semibold bg-white/5 hover:bg-white/10 border border-white/10 flex items-center gap-2">
                            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} /> Refresh
                        </button>
                    </div>
                </div>

                {/* Add SKU Form */}
                {showSkuForm && (
                    <div className="rounded-2xl bg-[#121214] border border-purple-500/20 p-6">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-purple-400 mb-4 flex items-center gap-2">
                            <Tag size={16} /> New SKU
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
                            <input value={skuId} onChange={e => setSkuId(e.target.value)} placeholder="SKU ID (e.g. SKU011)"
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-purple-500" />
                            <input value={skuName} onChange={e => setSkuName(e.target.value)} placeholder="Product Name"
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-purple-500" />
                            <select value={skuCategory} onChange={e => setSkuCategory(e.target.value)}
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-purple-500">
                                {categories.map(c => <option key={c} value={c}>{c}</option>)}
                            </select>
                            <input value={skuCost} onChange={e => setSkuCost(e.target.value)} placeholder="Unit Cost (₹)" type="number" step="0.1"
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-purple-500" />
                            <button onClick={handleAddSku} className="bg-purple-600 hover:bg-purple-700 rounded-lg px-4 py-2.5 text-sm font-semibold flex items-center justify-center gap-2 transition-colors">
                                <Plus size={16} /> Add SKU
                            </button>
                        </div>
                    </div>
                )}

                {/* Add Stock Form */}
                {showStockForm && (
                    <div className="rounded-2xl bg-[#121214] border border-blue-500/20 p-6">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-blue-400 mb-4 flex items-center gap-2">
                            <Package size={16} /> Add/Update Stock
                        </h3>
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
                            <select value={stockHub} onChange={e => setStockHub(e.target.value)}
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-blue-500">
                                <option value="">Select Hub</option>
                                {centres.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                            </select>
                            <select value={stockSku} onChange={e => setStockSku(e.target.value)}
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-blue-500">
                                <option value="">Select SKU</option>
                                {skus.map(s => <option key={s.id} value={s.id}>{s.name} ({s.id})</option>)}
                            </select>
                            <input value={stockQty} onChange={e => setStockQty(e.target.value)} placeholder="Quantity" type="number"
                                className="bg-black/50 border border-white/10 rounded-lg px-3 py-2.5 text-sm outline-none focus:border-blue-500" />
                            <button onClick={handleAddStock} className="bg-blue-600 hover:bg-blue-700 rounded-lg px-4 py-2.5 text-sm font-semibold flex items-center justify-center gap-2 transition-colors">
                                <Plus size={16} /> Set Stock
                            </button>
                        </div>
                    </div>
                )}

                {/* SKU Catalogue */}
                <div className="rounded-2xl bg-[#121214] border border-white/10 p-6">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 flex items-center gap-2">
                            <Tag size={16} className="text-purple-400" /> SKU Catalogue
                        </h3>
                        <span className="bg-purple-600/20 text-purple-400 text-xs px-2.5 py-1 rounded-full font-medium">{skus.length} SKUs</span>
                    </div>
                    {skus.length === 0 ? (
                        <div className="text-center py-8 text-gray-500 border border-dashed border-white/10 rounded-xl">
                            No SKUs defined. Add your first SKU above.
                        </div>
                    ) : (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                            {skus.map(s => (
                                <div key={s.id} className="group p-4 bg-white/[0.03] border border-white/5 rounded-xl flex items-center justify-between hover:bg-white/[0.06] transition-colors">
                                    <div>
                                        <div className="text-sm font-medium text-white">{s.name}</div>
                                        <div className="text-xs text-gray-500 mt-0.5">{s.id} · {s.category} · ₹{s.unit_cost}</div>
                                    </div>
                                    <button onClick={() => handleDeleteSku(s.id)} className="text-gray-600 hover:text-red-400 transition-colors p-1 opacity-0 group-hover:opacity-100">
                                        <Trash2 size={14} />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>

                {/* Hub Inventory — Accordion */}
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <h3 className="text-sm font-bold uppercase tracking-wider text-gray-400 flex items-center gap-2">
                            <Package size={16} className="text-blue-400" /> Hub Inventory
                        </h3>
                        {inventory.length > 0 && (
                            <div className="flex gap-2">
                                <button onClick={expandAll}
                                    className="text-xs text-gray-500 hover:text-white px-3 py-1 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
                                    Expand All
                                </button>
                                <button onClick={collapseAll}
                                    className="text-xs text-gray-500 hover:text-white px-3 py-1 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
                                    Collapse All
                                </button>
                            </div>
                        )}
                    </div>

                    {inventory.length === 0 ? (
                        <div className="text-center py-12 text-gray-500 border border-dashed border-white/10 rounded-xl">
                            No hubs with inventory. Add hubs on the Map tab, then add stock here.
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {inventory.map(hub => (
                                <HubCard
                                    key={hub.hub_id}
                                    hub={hub}
                                    isOpen={openHubs.has(hub.hub_id)}
                                    onToggle={() => toggleHub(hub.hub_id)}
                                    onDeleteStock={handleDeleteStock}
                                />
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

const InventoryTab = memo(InventoryTabInner, (prev, next) =>
    prev.centres.length === next.centres.length &&
    prev.centres.every((c, i) => c.id === next.centres[i]?.id)
);
export default InventoryTab;
