"use client";
import { useState, useEffect } from "react";
import dynamic from "next/dynamic";
import { Plus, Trash2, Map, Clock, RefreshCw } from "lucide-react";
import { fetchCentres, addCentre, deleteCentre, fetchCoverage, Centre } from "@/lib/api";

const MapComponent = dynamic(() => import("@/components/MapComponent"), { ssr: false });

export default function Dashboard() {
    const [centres, setCentres] = useState<Centre[]>([]);
    const [coverage, setCoverage] = useState<any>(null);
    const [loading, setLoading] = useState(true);
    const [mode, setMode] = useState<'distance' | 'time'>('distance');

    const [newName, setNewName] = useState("");
    const [newLat, setNewLat] = useState("20.0");
    const [newLon, setNewLon] = useState("78.0");

    const loadData = async () => {
        setLoading(true);
        try {
            const cData = await fetchCentres();
            setCentres(cData);
            const covData = await fetchCoverage();
            setCoverage(covData);
        } catch (e) {
            console.error(e);
        }
        setLoading(false);
    };

    useEffect(() => {
        loadData();
    }, []);

    const handleAdd = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!newName) return;
        setLoading(true);
        try {
            await addCentre({ name: newName, lat: parseFloat(newLat), lon: parseFloat(newLon) });
            setNewName("");
            await loadData();
        } catch (e) {
            console.error(e);
            setLoading(false);
        }
    };

    const handleDelete = async (id: string) => {
        setLoading(true);
        try {
            await deleteCentre(id);
            await loadData();
        } catch (e) {
            console.error(e);
            setLoading(false);
        }
    };

    return (
        <div className="flex h-full w-full">
            {/* Sidebar */}
            <div className="w-80 bg-[#121214] border-r border-white/10 flex flex-col shadow-2xl z-20 overflow-y-auto">
                <div className="p-6 border-b border-white/10">
                    <h2 className="text-xl font-bold flex items-center gap-2">
                        <span className="w-3 h-3 rounded-full bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.8)]"></span>
                        Ozark Engine
                    </h2>
                    <p className="text-xs text-gray-500 mt-2">Fulfillment Operations Center</p>
                </div>

                {/* Mode Toggle */}
                <div className="p-6 border-b border-white/10">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-4">View Mode</h3>
                    <div className="flex bg-white/5 rounded-lg p-1">
                        <button
                            onClick={() => setMode('distance')}
                            className={`flex-1 py-2 text-sm font-medium rounded-md flex items-center justify-center gap-2 transition-colors ${mode === 'distance' ? 'bg-blue-600' : 'hover:bg-white/10'}`}>
                            <Map size={16} /> Distance
                        </button>
                        <button
                            onClick={() => setMode('time')}
                            className={`flex-1 py-2 text-sm font-medium rounded-md flex items-center justify-center gap-2 transition-colors ${mode === 'time' ? 'bg-blue-600' : 'hover:bg-white/10'}`}>
                            <Clock size={16} /> Time
                        </button>
                    </div>
                </div>

                {/* Add Centre */}
                <div className="p-6 border-b border-white/10">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400 mb-4">Add Location</h3>
                    <form onSubmit={handleAdd} className="flex flex-col gap-3">
                        <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Hub Name" className="bg-black/50 border border-white/10 rounded-md px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all" />
                        <div className="flex gap-2">
                            <input value={newLat} onChange={e => setNewLat(e.target.value)} placeholder="Lat" className="w-1/2 bg-black/50 border border-white/10 rounded-md px-3 py-2 text-sm outline-none focus:border-blue-500 transition-all" />
                            <input value={newLon} onChange={e => setNewLon(e.target.value)} placeholder="Lon" className="w-1/2 bg-black/50 border border-white/10 rounded-md px-3 py-2 text-sm outline-none focus:border-blue-500 transition-all" />
                        </div>
                        <button disabled={loading} type="submit" className="mt-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium py-2 rounded-md transition-colors flex items-center justify-center gap-2">
                            {loading ? <RefreshCw size={16} className="animate-spin" /> : <Plus size={16} />}
                            Add Node
                        </button>
                    </form>
                </div>

                {/* Centre List */}
                <div className="p-6 flex-1">
                    <div className="flex items-center justify-between mb-4">
                        <h3 className="text-sm font-semibold uppercase tracking-wider text-gray-400">Active Nodes</h3>
                        <span className="bg-blue-600/20 text-blue-400 text-xs px-2 py-0.5 rounded-full font-medium">{centres.length}</span>
                    </div>
                    <div className="flex flex-col gap-2">
                        {centres.map(c => {
                            const colors = ["bg-green-500", "bg-blue-500", "bg-red-500"];
                            return (
                                <div key={c.id} className="group p-3 bg-white/5 border border-white/10 rounded-lg flex items-center justify-between hover:bg-white/10 transition-colors">
                                    <div className="flex items-center gap-3">
                                        <span className={`w-3 h-3 rounded-full ${colors[c.colour_idx % 3]} shadow-lg`} />
                                        <div className="flex flex-col">
                                            <span className="text-sm font-medium">{c.name}</span>
                                            <span className="text-xs text-gray-500">{c.lat.toFixed(2)}, {c.lon.toFixed(2)}</span>
                                        </div>
                                    </div>
                                    <button onClick={() => handleDelete(c.id)} disabled={loading} className="text-gray-500 hover:text-red-400 transition-colors p-1">
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                            );
                        })}
                        {centres.length === 0 && (
                            <div className="text-center p-4 border border-dashed border-white/10 rounded-lg text-sm text-gray-500">
                                No active nodes. Add a location to compute coverage.
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Main Map Area */}
            <div className="flex-1 relative bg-black p-4">
                <div className="absolute inset-0 bg-[url('/grid.svg')] bg-center opacity-5 pointer-events-none" />

                {loading && (
                    <div className="absolute inset-0 z-50 flex flex-col items-center justify-center bg-black/60 backdrop-blur-sm">
                        <RefreshCw className="w-10 h-10 text-blue-500 animate-spin mb-4" />
                        <div className="text-lg font-medium text-white/80">Computing spatial topology...</div>
                    </div>
                )}

                <div className="w-full h-full relative z-10">
                    <MapComponent centres={centres} coverageData={coverage?.[mode] || {}} mode={mode} />
                </div>
            </div>
        </div>
    );
}
