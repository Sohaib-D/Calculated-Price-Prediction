import axios from "axios";

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:5000").replace(/\/+$/, "");

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 45000,
});

function normalizeError(error, fallbackMessage) {
  const apiMessage = error?.response?.data?.error;
  const statusText = error?.response?.statusText;
  return apiMessage || statusText || fallbackMessage;
}

export async function getAIInsights(params = {}) {
  try {
    const response = await apiClient.get("/api/ai-insights", { params });
    return response.data || {};
  } catch (error) {
    throw new Error(normalizeError(error, "Unable to load AI insights"));
  }
}

export async function getSearchSuggestions(query, limit = 8) {
  if (!query || !query.trim()) {
    return [];
  }
  try {
    const response = await apiClient.get("/api/search/suggestions", {
      params: {
        q: query.trim(),
        limit,
      },
    });
    return response.data?.suggestions || [];
  } catch {
    return [];
  }
}

export async function getLocationSuggestions(query, lat = null, lon = null, limit = 7) {
  if (!query || !query.trim()) return [];
  try {
    const params = { q: query.trim(), limit };
    if (lat !== null && lon !== null) {
      params.lat = lat;
      params.lon = lon;
    }
    const response = await apiClient.get("/api/location/suggest", { params });
    return response.data?.suggestions || [];
  } catch {
    return [];
  }
}

// the function above already handles optional lat/lon, so no need for this duplicate
// export async function getLocationSuggestions(query, lat, lon, limit = 7) {
//   if (!query || !query.trim()) {
//     return [];
//   }
//   try {
//     const response = await apiClient.get("/api/location/suggest", {
//       params: {
//         q: query.trim(),
//         limit,
//         lat,
//         lon,
//       },
//     });
//     return response.data?.suggestions || [];
//   } catch {
//     return [];
//   }
//}

export async function searchProducts(query) {
  if (!query || !query.trim()) {
    return { query: "", products: [], count: 0 };
  }
  try {
    const response = await apiClient.get("/api/search", {
      params: { q: query.trim() },
    });
    return response.data || { query: query.trim(), products: [], count: 0 };
  } catch (error) {
    throw new Error(normalizeError(error, "Search request failed"));
  }
}

export async function getIntelligence(payload) {
  try {
    const response = await apiClient.post("/api/intelligence", payload);
    return response.data || {};
  } catch (error) {
    throw new Error(normalizeError(error, "AI intelligence request failed"));
  }
}

export async function chatWithAI(payload) {
  try {
    const response = await apiClient.post("/api/ai-chat", payload);
    return response.data || {};
  } catch (error) {
    throw new Error(normalizeError(error, "AI chat request failed"));
  }
}

export async function compareProducts(productA, productB) {
  try {
    const response = await apiClient.post("/api/compare", {
      product_a: productA,
      product_b: productB,
    });
    return response.data || {};
  } catch (error) {
    throw new Error(normalizeError(error, "Product comparison request failed"));
  }
}

export async function getProductsCatalog(params = {}) {
  try {
    const response = await apiClient.get("/api/products/electronics", { params });
    return response.data || { products: [], count: 0 };
  } catch (error) {
    throw new Error(normalizeError(error, "Failed to load catalog"));
  }
}

export async function getStores() {
  try {
    const response = await apiClient.get("/api/stores");
    return response.data || { stores: [], total: 0 };
  } catch (error) {
    throw new Error(normalizeError(error, "Failed to load stores"));
  }
}

export default apiClient;
