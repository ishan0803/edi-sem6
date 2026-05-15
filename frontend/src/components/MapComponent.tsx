"use client";

import { useMemo, useState, useCallback, memo, useRef, useEffect } from 'react';
import { Map } from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, PathLayer, ScatterplotLayer } from '@deck.gl/layers';
import 'maplibre-gl/dist/maplibre-gl.css';

const BND_COLORS = {
    green: [44, 160, 44],
    blue: [31, 119, 180],
    red: [214, 39, 40]
} as const;
const CENTRE_COLORS = [
    [44, 160, 44],
    [31, 119, 180],
    [214, 39, 40]
] as const;
const RIDER_COLORS = [
    [0, 255, 200],
    [255, 100, 50],
    [100, 150, 255],
    [255, 220, 50],
    [180, 80, 255],
    [50, 255, 100],
] as const;

const CARTO_DARK_MATTER = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

interface ETAPopupData {
    nearest_store_id?: string;
    nearest_store_name?: string;
    distance_m?: number;
    base_transit_sec?: number;
    tier_factor?: number;
    tier_label?: string;
    prep_time_sec?: number;
    estimated_time_sec?: number;
    error?: string;
}

interface MapProps {
    centres: any[];
    coverageData: any;
    mode: 'distance' | 'time';
    vrpRoutes?: any[];
    pinMode?: boolean;
    onPinDrop?: (lat: number, lon: number) => void;
    etaPopup?: { lat: number; lon: number; data: ETAPopupData } | null;
    etaLoading?: boolean;
}

const formatTime = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.round(sec % 60);
    return m > 0 ? `${m}m ${s}s` : `${s}`;
};

function MapComponentInner({
    centres, coverageData, mode, vrpRoutes, pinMode, onPinDrop, etaPopup, etaLoading
}: MapProps) {
    const [hoverInfo, setHoverInfo] = useState<any>(null);
    const hoverCb = useCallback((info: any) => {
        setHoverInfo(info.object ? { ...info, stop: info.object } : null);
    }, []);

    // Stable initial view — only changes when first centre appears
    const firstCentreId = centres.length > 0 ? centres[0].id : null;
    const initialViewState = useMemo(() => ({
        longitude: centres.length > 0 ? centres[0].lon : 78.0,
        latitude: centres.length > 0 ? centres[0].lat : 20.0,
        zoom: centres.length > 0 ? 11 : 4.5,
        pitch: 0,
        bearing: 0,
    }), [firstCentreId]);

    const handleClick = useCallback((info: any) => {
        if (pinMode && onPinDrop && info.coordinate) {
            onPinDrop(info.coordinate[1], info.coordinate[0]);
        }
    }, [pinMode, onPinDrop]);

    // Serialize coverage keys to avoid re-creating layers on same data
    const coverageKey = useMemo(() => {
        if (!coverageData) return '';
        return JSON.stringify(Object.keys(coverageData));
    }, [coverageData]);

    // Memoize heavy coverage layers separately (they change rarely)
    const coverageLayers = useMemo(() => {
        if (!coverageData) return [];
        const out: any[] = [];
        const colors = ['red', 'blue', 'green'] as const;

        colors.forEach((color, idx) => {
            const features: any[] = [];
            const ids = Object.keys(coverageData);
            for (let i = 0; i < ids.length; i++) {
                const geojson = coverageData[ids[i]]?.[color];
                if (geojson) {
                    features.push({ type: 'Feature', geometry: geojson, properties: { color } });
                }
            }
            if (features.length > 0) {
                const opacity = 0.3 + (2 - idx) * 0.15;
                const rgb = BND_COLORS[color];
                out.push(
                    new GeoJsonLayer({
                        id: `band-${color}-${mode}`,
                        data: { type: 'FeatureCollection', features } as any,
                        stroked: true, filled: true, lineWidthMinPixels: 2,
                        getLineColor: [...rgb, 200] as [number, number, number, number],
                        getFillColor: [...rgb, Math.floor(opacity * 255)] as [number, number, number, number],
                        pickable: false,  // not interactive → saves GPU cycles
                    })
                );
            }
        });
        return out;
    }, [coverageKey, mode]);

    // Centre marker layer — changes only when centres list changes
    const centreIds = centres.map(c => c.id).join(',');
    const centreLayer = useMemo(() => {
        if (centres.length === 0) return [];
        const features = centres.map(c => ({
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
            properties: { name: c.name, colour_idx: c.colour_idx }
        }));
        return [new GeoJsonLayer({
            id: 'centres-layer',
            data: { type: 'FeatureCollection', features } as any,
            pointType: 'circle+text', stroked: true, filled: true,
            getFillColor: ((d: any) => [...CENTRE_COLORS[d.properties.colour_idx % 3], 255]) as any,
            getLineColor: [255, 255, 255, 255] as [number, number, number, number],
            getLineWidth: 2, lineWidthMinPixels: 2,
            getPointRadius: 200, pointRadiusMinPixels: 6, pointRadiusMaxPixels: 15,
            getText: (d: any) => d.properties.name,
            getTextSize: 14,
            getTextColor: [255, 255, 255, 255] as [number, number, number, number],
            getTextPixelOffset: [0, -20],
            textFontFamily: 'Inter',
            pickable: false,
        })];
    }, [centreIds]);

    // VRP route layers — only when vrpRoutes changes
    const vrpKey = vrpRoutes ? vrpRoutes.map(r => r.rider_id).join(',') : '';
    const vrpLayers = useMemo(() => {
        if (!vrpRoutes || vrpRoutes.length === 0) return [];
        const out: any[] = [];
        vrpRoutes.forEach((rider: any, rIdx: number) => {
            const pathCoords: [number, number][] = [[rider.store_lon, rider.store_lat]];
            rider.route.forEach((stop: any) => pathCoords.push([stop.lon, stop.lat]));
            pathCoords.push([rider.store_lon, rider.store_lat]);
            const rColor = RIDER_COLORS[rIdx % RIDER_COLORS.length];

            out.push(new PathLayer({
                id: `vrp-path-${rIdx}`,
                data: [{ path: pathCoords }],
                getPath: (d: any) => d.path,
                getColor: rColor as [number, number, number],
                getWidth: 4, widthMinPixels: 3, widthMaxPixels: 8,
                pickable: false,
            }));
            // All stops for this rider in ONE layer instead of N separate layers
            out.push(new ScatterplotLayer({
                id: `vrp-stops-${rIdx}`,
                data: rider.route,
                getPosition: (d: any) => [d.lon, d.lat],
                getFillColor: rColor as [number, number, number],
                getLineColor: [255, 255, 255],
                stroked: true, lineWidthMinPixels: 2,
                getRadius: 150, radiusMinPixels: 5, radiusMaxPixels: 12,
                pickable: true,
                onHover: hoverCb,
            }));
        });
        return out;
    }, [vrpKey, hoverCb]);

    // ETA pin layer
    const pinKey = etaPopup ? `${etaPopup.lat},${etaPopup.lon}` : '';
    const pinLayer = useMemo(() => {
        if (!etaPopup) return [];
        return [new ScatterplotLayer({
            id: 'eta-pin',
            data: [etaPopup],
            getPosition: (d: any) => [d.lon, d.lat],
            getFillColor: [255, 50, 80, 220],
            getLineColor: [255, 255, 255, 255],
            stroked: true, lineWidthMinPixels: 3,
            getRadius: 250, radiusMinPixels: 8, radiusMaxPixels: 18,
            radiusUnits: 'meters' as const,
            pickable: false,
        })];
    }, [pinKey]);

    // Combine all layers — array concat is cheap
    const layers = useMemo(() => [
        ...coverageLayers,
        ...centreLayer,
        ...vrpLayers,
        ...pinLayer,
    ], [coverageLayers, centreLayer, vrpLayers, pinLayer]);

    const getCursor = useCallback(() => pinMode ? 'crosshair' : 'grab', [pinMode]);

    return (
        <div className="w-full h-[calc(100vh-80px)] rounded-xl overflow-hidden shadow-[0_0_40px_-15px_rgba(59,130,246,0.3)] border border-white/5 relative bg-[#1f2937]">
            <DeckGL
                initialViewState={initialViewState}
                controller={true}
                layers={layers}
                onClick={handleClick}
                getCursor={getCursor}
                useDevicePixels={false}
            >
                <Map mapStyle={CARTO_DARK_MATTER} reuseMaps />
            </DeckGL>

            {/* Pin Mode indicator */}
            {pinMode && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-red-500/90 text-white text-xs font-bold tracking-wider uppercase flex items-center gap-2 shadow-lg animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-white" />
                    ETA Pin Mode — Click anywhere
                </div>
            )}

            {/* ETA Loading */}
            {etaLoading && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-blue-600/90 text-white text-xs font-bold tracking-wider">
                    Calculating ETA...
                </div>
            )}

            {/* ETA Popup */}
            {etaPopup && etaPopup.data && !etaLoading && (
                <div className="absolute bottom-6 left-6 z-50 w-80 rounded-2xl bg-[#111113]/95 border border-white/10 p-5 shadow-2xl">
                    <div className="flex items-center gap-2 mb-3">
                        <span className="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_10px_rgba(255,50,80,0.6)]" />
                        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Customer ETA</h3>
                    </div>
                    {etaPopup.data.error ? (
                        <div className="text-sm text-red-400">{etaPopup.data.error}</div>
                    ) : (
                        <div className="space-y-2 text-sm">
                            <div className="flex justify-between">
                                <span className="text-gray-400">Nearest Store</span>
                                <span className="text-white font-medium">{etaPopup.data.nearest_store_name}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Distance</span>
                                <span className="text-white font-medium">{((etaPopup.data.distance_m || 0) / 1000).toFixed(2)} km</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Prep Time</span>
                                <span className="text-yellow-400 font-mono">{formatTime(etaPopup.data.prep_time_sec || 0)}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Transit Time</span>
                                <span className="text-white font-mono">{formatTime(etaPopup.data.base_transit_sec || 0)}</span>
                            </div>
                            <div className="flex justify-between">
                                <span className="text-gray-400">Traffic</span>
                                <span className={`font-medium ${
                                    etaPopup.data.tier_label === 'metro' ? 'text-red-400' :
                                    etaPopup.data.tier_label === 'tier1' ? 'text-orange-400' :
                                    etaPopup.data.tier_label === 'tier2' ? 'text-green-400' :
                                    'text-gray-400'
                                }`}>
                                    {etaPopup.data.tier_label} ({etaPopup.data.tier_factor}×)
                                </span>
                            </div>
                            <div className="border-t border-white/10 pt-2 mt-2 flex justify-between">
                                <span className="text-white font-bold">Est. Delivery</span>
                                <span className="text-blue-400 font-bold text-lg font-mono">
                                    {formatTime(etaPopup.data.estimated_time_sec || 0)}
                                </span>
                            </div>
                        </div>
                    )}
                </div>
            )}

            {/* VRP Stop Tooltip */}
            {hoverInfo && hoverInfo.stop && (
                <div className="absolute z-50 w-72 rounded-xl bg-[#111113]/95 border border-white/10 p-4 shadow-2xl pointer-events-none"
                    style={{ left: (hoverInfo.x || 0) + 15, top: (hoverInfo.y || 0) - 10 }}>
                    <h4 className="text-xs font-bold text-white uppercase tracking-wider mb-2">
                        Order {hoverInfo.stop.order_id}
                    </h4>
                    <div className="space-y-1.5 text-xs">
                        <div className="flex justify-between">
                            <span className="text-gray-400">Base Transit</span>
                            <span className="text-white font-mono">{formatTime(hoverInfo.stop.base_transit_sec)}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Tier Penalty ({hoverInfo.stop.tier_label})</span>
                            <span className="text-orange-400 font-mono">×{hoverInfo.stop.tier_factor}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Address Penalty (SAP)</span>
                            <span className="text-yellow-400 font-mono">+{formatTime(hoverInfo.stop.sap_sec)}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Z-Axis Friction (ZAFI)</span>
                            <span className="text-purple-400 font-mono">+{formatTime(hoverInfo.stop.zafi_sec)}</span>
                        </div>
                        {hoverInfo.stop.zafi_breakdown && (
                            <div className="ml-2 text-[10px] text-gray-500 space-y-0.5">
                                {hoverInfo.stop.zafi_breakdown.floor_extracted > 0 && (
                                    <div>Floor: {hoverInfo.stop.zafi_breakdown.floor_extracted}</div>
                                )}
                                {hoverInfo.stop.zafi_breakdown.building_type && (
                                    <div>Type: {hoverInfo.stop.zafi_breakdown.building_type}</div>
                                )}
                                {hoverInfo.stop.zafi_breakdown.extraction_method && hoverInfo.stop.zafi_breakdown.extraction_method !== "none" && (
                                    <div>Method: <span className="text-purple-300">{hoverInfo.stop.zafi_breakdown.extraction_method}</span></div>
                                )}
                            </div>
                        )}
                        <div className="border-t border-white/10 pt-1.5 mt-1.5 flex justify-between">
                            <span className="text-white font-bold">Total ETA</span>
                            <span className="text-blue-400 font-bold font-mono">{formatTime(hoverInfo.stop.total_eta_sec)}</span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

const MapComponent = memo(MapComponentInner);
export default MapComponent;
