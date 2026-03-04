import axios from 'axios';

const api = axios.create({
    baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api',
});

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
