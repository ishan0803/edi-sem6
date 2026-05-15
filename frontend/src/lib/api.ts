import axios from 'axios';

const api = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api',
});

// ── Existing Centre types & API ──────────────────────────────────────────────

export interface Centre {
    id: string;
    name: string;
    lat: number;
    lon: number;
    colour_idx: number;
}

export const fetchCentres = async (): Promise<Centre[]> => {
    const response = await api.get('/centres/');
    return response.data;
};

export const addCentre = async (data: { name: string; lat: number; lon: number }): Promise<Centre> => {
    const response = await api.post('/centres/', data);
    return response.data;
};

export const deleteCentre = async (id: string): Promise<void> => {
    await api.delete(`/centres/${id}`);
};

export const fetchCoverage = async (): Promise<any> => {
    const response = await api.get('/centres/coverage');
    return response.data;
};

// ── Dispatch (VRP) API ───────────────────────────────────────────────────────

export interface DispatchOrder {
    order_id: string;
    lat: number;
    lon: number;
    address_text: string;
}

export interface DispatchPayload {
    orders: DispatchOrder[];
    available_riders?: number;
}

export const dispatchOrders = async (payload: DispatchPayload): Promise<any> => {
    const response = await api.post('/dispatch', payload);
    return response.data;
};

// ── Customer ETA API ─────────────────────────────────────────────────────────

export interface CustomerETAPayload {
    lat: number;
    lon: number;
}

export interface CustomerETAResult {
    nearest_store_id?: string;
    nearest_store_name?: string;
    distance_m?: number;
    base_transit_sec?: number;
    tier_factor?: number;
    tier_label?: string;
    estimated_time_sec?: number;
    error?: string;
}

export const getCustomerETA = async (payload: CustomerETAPayload): Promise<CustomerETAResult> => {
    const response = await api.post('/eta/customer', payload);
    return response.data;
};

// ── Synthetic GNN (legacy) ───────────────────────────────────────────────────

export const trainSynthetic = async (): Promise<any> => {
    const response = await api.post('/inventory/train-synthetic');
    return response.data;
};

export const getInventoryRecommendations = async (): Promise<any> => {
    const response = await api.get('/inventory/recommendations');
    return response.data;
};

export const getInventoryData = async (): Promise<any> => {
    const response = await api.get('/inventory/data');
    return response.data;
};

// ── Custom SKU Catalogue ─────────────────────────────────────────────────────

export interface SKU {
    id: string;
    name: string;
    category: string;
    unit_cost: number;
}

export const listSKUs = async (): Promise<SKU[]> => {
    const response = await api.get('/skus');
    return response.data;
};

export const createSKU = async (data: { id: string; name: string; category: string; unit_cost: number }): Promise<SKU> => {
    const response = await api.post('/skus', data);
    return response.data;
};

export const deleteSKU = async (skuId: string): Promise<void> => {
    await api.delete(`/skus/${skuId}`);
};

// ── Real Hub Inventory ───────────────────────────────────────────────────────

export interface StockItem {
    id: number;
    hub_id: string;
    sku_id: string;
    quantity: number;
    hub_name?: string;
    sku_name?: string;
}

export interface HubInventorySummary {
    hub_id: string;
    hub_name: string;
    total_skus: number;
    total_quantity: number;
    items: StockItem[];
}

export const getAllInventory = async (): Promise<HubInventorySummary[]> => {
    const response = await api.get('/inventory/all');
    return response.data;
};

export const upsertStock = async (data: { hub_id: string; sku_id: string; quantity: number }): Promise<StockItem> => {
    const response = await api.post('/inventory/stock', data);
    return response.data;
};

export const deleteStock = async (recordId: number): Promise<void> => {
    await api.delete(`/inventory/stock/${recordId}`);
};

// ── GNN Rebalance on Real Inventory ──────────────────────────────────────────

export const rebalanceInventory = async (): Promise<any> => {
    const response = await api.post('/inventory/rebalance');
    return response.data;
};
