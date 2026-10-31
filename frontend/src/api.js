
import axios from "axios";

const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL || "http://localhost:5000"}/api`,
});

export const getDistricts = () => api.get("/districts");

export const getSchools = () => api.get("/schools");

export const getAdministrators = () => api.get("/administrators");

export default api;
