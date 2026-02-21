"use client";

import { useMemo } from 'react';
import { Map } from 'react-map-gl/maplibre';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
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

// NOTE: Mapbox requires a token for its base maps. However, we can use Carto's free basemaps natively within MapboxGL.
const CARTO_DARK_MATTER = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json';

interface MapProps {
    centres: any[];
    coverageData: any;
    mode: 'distance' | 'time';
}

export default function MapComponent({ centres, coverageData, mode }: MapProps) {

    const initialViewState = useMemo(() => {
        return {
            longitude: centres.length > 0 ? centres[0].lon : 78.0,
            latitude: centres.length > 0 ? centres[0].lat : 20.0,
            zoom: centres.length > 0 ? 11 : 4.5,
            pitch: 0,
            bearing: 0
        };
    }, [centres.length > 0 ? centres[0].id : null]);

    // Transform coverageData dict into a single FeatureCollection for DeckGL rendering
    const layers = useMemo(() => {
        if (!coverageData) return [];

        const geoJsonLayers: any[] = [];

        // We want to render them in a specific order: red (largest) on bottom, green (smallest) on top.
        const colors = ['red', 'blue', 'green'];

        colors.forEach((color, idx) => {
            // Build a unified feature collection for this color band
            const features: any[] = [];
            Object.keys(coverageData).forEach((cid) => {
                const geojson = coverageData[cid]?.[color];
                if (geojson) {
                    features.push({
                        type: 'Feature',
                        geometry: geojson,
                        properties: { color: color }
                    });
                }
            });

            if (features.length > 0) {
                const opacity = 0.3 + (2 - idx) * 0.15; // match original opacity logic
                const rgb = BND_COLORS[color as keyof typeof BND_COLORS];

                geoJsonLayers.push(
                    new GeoJsonLayer({
                        id: `band-${color}-${mode}`,
                        data: { type: 'FeatureCollection', features } as any,
                        stroked: true,
                        filled: true,
                        lineWidthMinPixels: 2,
                        getLineColor: [...rgb, 200] as [number, number, number, number], // slightly transparent borders
                        getFillColor: [...rgb, Math.floor(opacity * 255)] as [number, number, number, number],
                        pickable: true,
                    })
                );
            }
        });

        // Add Centre Markers as a scatterplot layer natively mapped to WebGL
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
                    pointType: 'circle+text',
                    stroked: true,
                    filled: true,
                    getFillColor: ((d: any) => [...CENTRE_COLORS[d.properties.colour_idx % 3], 255]) as any,
                    getLineColor: [255, 255, 255, 255] as [number, number, number, number],
                    getLineWidth: 2,
                    lineWidthMinPixels: 2,
                    getPointRadius: 200, // Adjust relative to zoom
                    pointRadiusMinPixels: 6,
                    pointRadiusMaxPixels: 15,
                    getText: (d: any) => d.properties.name,
                    getTextSize: 14,
                    getTextColor: [255, 255, 255, 255] as [number, number, number, number],
                    getTextPixelOffset: [0, -20],
                    textFontFamily: 'Inter',
                })
            );
        }

        return geoJsonLayers;
    }, [coverageData, mode, centres]);

    return (
        <div className="w-full h-[calc(100vh-80px)] rounded-xl overflow-hidden shadow-[0_0_40px_-15px_rgba(59,130,246,0.3)] border border-white/5 relative bg-[#1f2937]">
            <DeckGL
                initialViewState={initialViewState}
                controller={true}
                layers={layers}
            >
                <Map
                    mapStyle={CARTO_DARK_MATTER}
                    reuseMaps
                />
            </DeckGL>
        </div>
    );
}
