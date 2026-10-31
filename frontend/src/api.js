
import axios from "axios";

const api = axios.create({
  baseURL: `${import.meta.env.VITE_API_URL || "http://localhost:5000"}/api`,
});

export const getDistricts = () => api.get("/districts");

// Fetch all school records, including records on later pages
export const getSchools = async () => {
  const firstResponse = await api.get("/schools?page=1&limit=1000");

  const totalPages = firstResponse.data.totalPages || 1;

  const remainingResponses = await Promise.all(
    Array.from({ length: totalPages - 1 }, (_, index) =>
      api.get(`/schools?page=${index + 2}&limit=1000`)
    )
  );

  const allSchools = [
    ...(firstResponse.data.data || []),
    ...remainingResponses.flatMap(response => response.data.data || [])
  ];

  return {
    ...firstResponse,
    data: allSchools
  };
};

export const getAdministrators = () => api.get("/administrators");

export default api;
