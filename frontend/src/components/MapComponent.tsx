"use client";

import { useMemo, useState, useCallback } from 'react';
import { Map } from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer, PathLayer, ScatterplotLayer, TextLayer } from '@deck.gl/layers';
import 'maplibre-gl/dist/maplibre-gl.css';

const BND_COLORS = {
    green: [44, 160, 44],
    blue: [31, 119, 180],
    red: [214, 39, 40]
};
const CENTRE_COLORS = [
    [44, 160, 44],
    [31, 119, 180],
    [214, 39, 40]
];
const RIDER_COLORS = [
    [0, 255, 200],
    [255, 100, 50],
    [100, 150, 255],
    [255, 220, 50],
    [180, 80, 255],
    [50, 255, 100],
];

const CARTO_DARK_MATTER = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

interface ETAPopupData {
    nearest_store_id?: string;
    nearest_store_name?: string;
    distance_m?: number;
    base_transit_sec?: number;
    tier_factor?: number;
    tier_label?: string;
    estimated_time_sec?: number;
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

export default function MapComponent({
    centres, coverageData, mode, vrpRoutes, pinMode, onPinDrop, etaPopup, etaLoading
}: MapProps) {
    const [hoverInfo, setHoverInfo] = useState<any>(null);

    const initialViewState = useMemo(() => {
        return {
            longitude: centres.length > 0 ? centres[0].lon : 78.0,
            latitude: centres.length > 0 ? centres[0].lat : 20.0,
            zoom: centres.length > 0 ? 11 : 4.5,
            pitch: 0,
            bearing: 0
        };
    }, [centres.length > 0 ? centres[0].id : null]);

    const handleClick = useCallback((info: any) => {
        if (pinMode && onPinDrop && info.coordinate) {
            onPinDrop(info.coordinate[1], info.coordinate[0]);
        }
    }, [pinMode, onPinDrop]);

    const layers = useMemo(() => {
        if (!coverageData) return [];
        const geoJsonLayers: any[] = [];
        const colors = ['red', 'blue', 'green'];

        colors.forEach((color, idx) => {
            const features: any[] = [];
            Object.keys(coverageData).forEach((cid) => {
                const geojson = coverageData[cid]?.[color];
                if (geojson) {
                    features.push({ type: 'Feature', geometry: geojson, properties: { color } });
                }
            });
            if (features.length > 0) {
                const opacity = 0.3 + (2 - idx) * 0.15;
                const rgb = BND_COLORS[color as keyof typeof BND_COLORS];
                geoJsonLayers.push(
                    new GeoJsonLayer({
                        id: `band-${color}-${mode}`,
                        data: { type: 'FeatureCollection', features } as any,
                        stroked: true, filled: true, lineWidthMinPixels: 2,
                        getLineColor: [...rgb, 200] as [number, number, number, number],
                        getFillColor: [...rgb, Math.floor(opacity * 255)] as [number, number, number, number],
                        pickable: true,
                    })
                );
            }
        });

        // Centre markers
        if (centres.length > 0) {
            const centreFeatures = centres.map(c => ({
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
                properties: { name: c.name, colour_idx: c.colour_idx }
            }));
            geoJsonLayers.push(
                new GeoJsonLayer({
                    id: 'centres-layer',
                    data: { type: 'FeatureCollection', features: centreFeatures } as any,
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
                })
            );
        }

        // VRP route paths
        if (vrpRoutes && vrpRoutes.length > 0) {
            vrpRoutes.forEach((rider: any, rIdx: number) => {
                const pathCoords: [number, number][] = [[rider.store_lon, rider.store_lat]];
                rider.route.forEach((stop: any) => {
                    pathCoords.push([stop.lon, stop.lat]);
                });
                // Return to store
                pathCoords.push([rider.store_lon, rider.store_lat]);

                const rColor = RIDER_COLORS[rIdx % RIDER_COLORS.length];
                geoJsonLayers.push(
                    new PathLayer({
                        id: `vrp-path-${rIdx}`,
                        data: [{ path: pathCoords, rider }],
                        getPath: (d: any) => d.path,
                        getColor: rColor as [number, number, number],
                        getWidth: 4,
                        widthMinPixels: 3,
                        widthMaxPixels: 8,
                        pickable: true,
                        getDashArray: [8, 4],
                        dashJustified: true,
                    })
                );

                // Order stop markers
                rider.route.forEach((stop: any, sIdx: number) => {
                    geoJsonLayers.push(
                        new ScatterplotLayer({
                            id: `vrp-stop-${rIdx}-${sIdx}`,
                            data: [stop],
                            getPosition: (d: any) => [d.lon, d.lat],
                            getFillColor: rColor as [number, number, number],
                            getLineColor: [255, 255, 255],
                            stroked: true, lineWidthMinPixels: 2,
                            getRadius: 150, radiusMinPixels: 5, radiusMaxPixels: 12,
                            pickable: true,
                            onHover: (info: any) => setHoverInfo(info.object ? { ...info, stop: info.object } : null),
                        })
                    );
                });
            });
        }

        // ETA pin marker
        if (etaPopup) {
            geoJsonLayers.push(
                new ScatterplotLayer({
                    id: 'eta-pin',
                    data: [etaPopup],
                    getPosition: (d: any) => [d.lon, d.lat],
                    getFillColor: [255, 50, 80, 220],
                    getLineColor: [255, 255, 255, 255],
                    stroked: true, lineWidthMinPixels: 3,
                    getRadius: 250, radiusMinPixels: 8, radiusMaxPixels: 18,
                    radiusUnits: 'meters',
                })
            );
        }

        return geoJsonLayers;
    }, [coverageData, mode, centres, vrpRoutes, etaPopup]);

    const formatTime = (sec: number) => {
        const m = Math.floor(sec / 60);
        const s = Math.round(sec % 60);
        return m > 0 ? `${m}m ${s}s` : `${s}s`;
    };

    return (
        <div className="w-full h-[calc(100vh-80px)] rounded-xl overflow-hidden shadow-[0_0_40px_-15px_rgba(59,130,246,0.3)] border border-white/5 relative bg-[#1f2937]">
            <DeckGL
                initialViewState={initialViewState}
                controller={true}
                layers={layers}
                onClick={handleClick}
                getCursor={() => pinMode ? 'crosshair' : 'grab'}
            >
                <Map mapStyle={CARTO_DARK_MATTER} reuseMaps />
            </DeckGL>

            {/* Pin Mode indicator */}
            {pinMode && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-red-500/90 backdrop-blur text-white text-xs font-bold tracking-wider uppercase flex items-center gap-2 shadow-lg animate-pulse">
                    <span className="w-2 h-2 rounded-full bg-white" />
                    ETA Pin Mode — Click anywhere
                </div>
            )}

            {/* ETA Loading */}
            {etaLoading && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-full bg-blue-600/90 backdrop-blur text-white text-xs font-bold tracking-wider">
                    Calculating ETA...
                </div>
            )}

            {/* ETA Popup */}
            {etaPopup && etaPopup.data && !etaLoading && (
                <div className="absolute bottom-6 left-6 z-50 w-80 rounded-2xl bg-[#111113]/95 backdrop-blur-xl border border-white/10 p-5 shadow-2xl">
                    <div className="flex items-center gap-2 mb-3">
                        <span className="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_10px_rgba(255,50,80,0.6)]" />
                        <h3 className="text-sm font-bold text-white uppercase tracking-wider">Customer ETA</h3>
                    </div>
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
                            <span className="text-gray-400">Base Transit</span>
                            <span className="text-white font-mono">{formatTime(etaPopup.data.base_transit_sec || 0)}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-gray-400">Tier</span>
                            <span className={`font-medium ${etaPopup.data.tier_label === 'metro' ? 'text-orange-400' : 'text-green-400'}`}>
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
                </div>
            )}

            {/* VRP Stop Tooltip */}
            {hoverInfo && hoverInfo.stop && (
                <div className="absolute z-50 w-72 rounded-xl bg-[#111113]/95 backdrop-blur-xl border border-white/10 p-4 shadow-2xl pointer-events-none"
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
