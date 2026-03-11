import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Head from "next/head";
import { AnimatePresence, motion } from "framer-motion";
import {
  AlertTriangle,
  Bot,
  BrainCircuit,
  Fuel,
  Loader2,
  MapPin,
  Menu,
  RefreshCcw,
  Sparkles,
  Store,
  TrendingUp,
  X,
} from "lucide-react";
import { gsap } from "gsap";
import AIInsightsPanel from "../components/AIInsightsPanel";
import DealAlerts from "../components/DealAlerts";
import HeroSection from "../components/HeroSection";
import ProductCard from "../components/ProductCard";
import SearchBar from "../components/SearchBar";
import TrendingProducts from "../components/TrendingProducts";
import {
  chatWithAI,
  compareProducts,
  getAIInsights,
  getIntelligence,
  getProductsCatalog,
  getStores,
  searchProducts,
  getLocationSuggestions,
} from "../utils/api";

const ParticleBackground = dynamic(() => import("../components/ParticleBackground"), { ssr: false });
const LocationMap = dynamic(() => import("../components/LocationMap"), {
  ssr: false,
  loading: () => <div className="skeleton h-[340px] w-full rounded-2xl" />,
});

const DEFAULT_LOCATION = { lat: 33.6844, lon: 73.0479 };
const NAV_ITEMS = [
  { id: "optimizer", label: "Optimizer" },
  { id: "insights", label: "AI Insights" },
  { id: "catalog", label: "Catalog" },
  { id: "stores", label: "Stores" },
  { id: "map", label: "Map" },
];

function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function formatDuration(value) {
  const total = Math.round(Number(value) || 0);
  if (!Number.isFinite(total) || total <= 0) return "0m";

  const minute = 1;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;
  const month = 30 * day;
  const year = 365 * day;

  const plural = (numValue, singular, pluralLabel) => (numValue === 1 ? singular : pluralLabel);

  if (total >= year) {
    const years = Math.floor(total / year);
    return `${years} ${plural(years, "year", "years")}`;
  }
  if (total >= month) {
    const months = Math.floor(total / month);
    return `${months} ${plural(months, "month", "months")}`;
  }
  if (total >= week) {
    const weeks = Math.floor(total / week);
    return `${weeks} ${plural(weeks, "week", "weeks")}`;
  }
  if (total >= day) {
    const days = Math.floor(total / day);
    return `${days} ${plural(days, "day", "days")}`;
  }
  if (total >= hour) {
    const hours = Math.floor(total / hour);
    const mins = total % hour;
    const label = hours === 1 ? "hr" : "hrs";
    return mins ? `${hours}${label} ${mins}m` : `${hours}${label}`;
  }
  return `${total}m`;
}

function buildChatMessage(chat) {
  if (!chat) {
    return "I could not generate a response yet. Try asking about price, availability, or alternatives.";
  }
  if (chat.error) {
    return `**Error:** ${chat.error}`;
  }

  const normalizeChatText = (value) => (
    String(value || "")
      .replace(/\r/g, "")
      .replace(/\n{3,}/g, "\n\n")
      .trim()
  );

  if (chat.message) {
    return normalizeChatText(chat.message);
  }

  const parts = [];
  if (chat.no_match) {
    parts.push("No exact match — showing the closest options.");
  }

  const reason = normalizeChatText(chat.reason || chat.reasoning);
  const recommended = normalizeChatText(chat.recommended_product);
  const summary = normalizeChatText(chat.summary);
  if (recommended) parts.push(`**Top pick:** ${recommended}.`);
  if (reason) {
    parts.push(`**Why:** ${reason}`);
  } else if (summary) {
    parts.push(summary);
  }

  const alternatives = Array.isArray(chat.alternatives)
    ? chat.alternatives.filter(Boolean).slice(0, 3)
    : [];
  if (alternatives.length) {
    parts.push(`**Other options:** ${alternatives.join("; ")}.`);
  }

  const suggestions = Array.isArray(chat.suggestions)
    ? chat.suggestions.filter(Boolean).slice(0, 4)
    : [];
  if (suggestions.length) {
    parts.push(`**Try:** ${suggestions.map((item) => `"${item}"`).join(", ")}.`);
  }

  if (!parts.length) {
    return "I could not find enough detail yet. Try rephrasing or ask about alternatives.";
  }

  return parts.join("\n\n");
}

function buildRecommendationContext(recommendation, chatResult) {
  const best = recommendation?.best_overall;
  const fallbackText = String(chatResult?.recommended_product || "").trim();

  const product = String(best?.product || "").trim();
  if (!product) return fallbackText;

  const store = String(best?.branch_name || "").trim();
  const priceValue = Number(best?.product_price);
  let line = product;
  if (store) line += ` at ${store}`;
  if (Number.isFinite(priceValue) && priceValue > 0) {
    line += ` for Rs. ${priceValue.toLocaleString()}`;
  }
  return line;
}

function toRichHtml(value) {
  // escape first to avoid XSS
  let text = String(value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  // **bold** marker
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // break into lines and build paragraphs / lists
  const lines = text.split(/\r?\n/);
  let html = "";
  let inList = false;

  lines.forEach(line => {
    if (/^\s*[-\*•]\s+/.test(line)) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${line.replace(/^\s*[-\*•]\s+/, '')}</li>`;
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      if (line.trim() === '') {
        html += '<br/>';
      } else {
        html += `<p>${line}</p>`;
      }
    }
  });
  if (inList) html += '</ul>';
  return html;
}

function DetailRow({ label, value }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="rounded-lg border border-white/10 bg-white/5 p-2">
      <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">{label}</p>
      <div className="text-sm text-slate-100">{value}</div>
    </div>
  );
}

function buildStoreAbout(store) {
  if (!store) return "";
  const parts = [];
  const type = String(store.type || "").trim().toLowerCase();
  if (type === "online") {
    parts.push("Online-only store with nationwide delivery.");
  } else if (type) {
    parts.push("Physical retail store.");
  }
  if (store.city && store.city !== "Online") {
    parts.push(`Based in ${store.city}.`);
  }
  if (store.address) {
    parts.push(`Address: ${store.address}.`);
  }
  return parts.join(" ");
}

function RecCard({ title, item, color }) {
  if (!item) return null;
  const durationLabel = formatDuration(item.duration_min ?? item.duration ?? 0);
  return (
    <article className="glass-card rounded-2xl border border-white/12 p-4">
      <p className={`text-xs font-semibold uppercase tracking-[0.16em] ${color}`}>{title}</p>
      <h4 className="mt-1 line-clamp-1 text-sm font-bold text-white">{item.product || "N/A"}</h4>
      <p className="line-clamp-1 text-xs text-slate-300">{item.branch_name || "Unknown store"}</p>
      <div className="mt-2 grid grid-cols-2 gap-1 text-[11px] text-slate-300">
        <span>Price: Rs. {num(item.product_price, 0).toLocaleString()}</span>
        <span>Total: Rs. {num(item.grand_total, 0).toLocaleString()}</span>
        <span>{num(item.distance_km, 0).toFixed(1)} km</span>
        <span>Fuel: Rs. {num(item.fuel_cost, 0).toLocaleString()}</span>
        {durationLabel !== "0m" && <span>Time: {durationLabel}</span>}
      </div>
    </article>
  );
}

export default function Home() {
  const [activeView, setActiveView] = useState("optimizer");
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [hasSearched, setHasSearched] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [location, setLocation] = useState(DEFAULT_LOCATION);
  // attempt automatic geolocation once on mount
  useEffect(() => {
    if (navigator.geolocation && window.isSecureContext) {
      navigator.geolocation.getCurrentPosition(
        pos => {
          setLocation({ lat: pos.coords.latitude, lon: pos.coords.longitude });
        },
        () => {},
        { enableHighAccuracy: true, timeout: 15000 }
      );
    }
  }, []);
  const [locationDraft, setLocationDraft] = useState({
    lat: String(DEFAULT_LOCATION.lat),
    lon: String(DEFAULT_LOCATION.lon),
  });
  const [locationStatus, setLocationStatus] = useState("Manual location is active.");
  const [detectingLocation, setDetectingLocation] = useState(false);
  const [locationConfirmed, setLocationConfirmed] = useState(false);
  const [showLocationConfirm, setShowLocationConfirm] = useState(false);
  const [pendingSearchQuery, setPendingSearchQuery] = useState("");

  // text search for location with suggestions
  const [locationText, setLocationText] = useState("");
  const [locSuggestions, setLocSuggestions] = useState([]);
  const [locActiveIndex, setLocActiveIndex] = useState(-1);

  // filter toggle for showing only exact matches
  const [showExactOnly, setShowExactOnly] = useState(false);

  // chat conversation state
  const [chatHistory, setChatHistory] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [catalogDetail, setCatalogDetail] = useState(null);
  const [storeDetail, setStoreDetail] = useState(null);

  // fetch location suggestions whenever the text input or user coords change
  useEffect(() => {
    let cancelled = false;
    const q = locationText.trim();
    if (q.length < 2) {
      setLocSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const items = await getLocationSuggestions(q, location.lat, location.lon, 7);
        if (!cancelled) setLocSuggestions(items);
      } catch {
        if (!cancelled) setLocSuggestions([]);
      }
    }, 220);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [locationText, location.lat, location.lon]);


  const [priority, setPriority] = useState("total_cost");
  const [storeFilter, setStoreFilter] = useState("all");
  const [budget, setBudget] = useState("");
  const [pages, setPages] = useState(1);
  const [sortMode, setSortMode] = useState("recommended");
  const [maxDistance, setMaxDistance] = useState("");
  const [maxTotal, setMaxTotal] = useState("");
  const [minRating, setMinRating] = useState("0");
  const [storeTypeFilter, setStoreTypeFilter] = useState("all");
  const [mapFocus, setMapFocus] = useState(null);
  const closeDetail = useCallback(() => {
    setCatalogDetail(null);
    setStoreDetail(null);
  }, []);
  const openCatalogDetail = useCallback((item) => {
    setStoreDetail(null);
    setCatalogDetail(item);
  }, []);
  const openStoreDetail = useCallback((item) => {
    setCatalogDetail(null);
    setStoreDetail(item);
  }, []);

  const [intelligence, setIntelligence] = useState(null);
  const [chatResult, setChatResult] = useState(null);
  const [fallbackResults, setFallbackResults] = useState([]);
  const [insights, setInsights] = useState(null);
  const [catalog, setCatalog] = useState({ loaded: false, loading: false, items: [], error: "" });
  const [stores, setStores] = useState({ loaded: false, loading: false, items: [], error: "" });
  const [compareState, setCompareState] = useState({
    productA: "",
    productB: "",
    loading: false,
    result: null,
    error: "",
  });
  const searchAnchorRef = useRef(null);
  const chatScrollRef = useRef(null);
  const locationInputRef = useRef(null);

  const recommendation = intelligence?.recommendation || {};
  const rankedProducts = useMemo(() => {
    const options = recommendation?.all_options || [];
    return options.length ? options : fallbackResults;
  }, [recommendation, fallbackResults]);

  // products whose name contains the query as a whole word or phrase
  const exactProductsLegacy = useMemo(() => {
    if (!query) return [];
    try {
      const pattern = new RegExp(`\\b${query.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&")}\\b`, "i");
      return rankedProducts.filter((r) => pattern.test(r.product || r.name || ""));
    } catch {
      return [];
    }
  }, [rankedProducts, query]);

  // strict equality matches for filtering button
  const exactProducts = useMemo(() => {
    if (!query) return [];
    const q = query.trim().toLowerCase();
    return rankedProducts.filter((r) => {
      const name = String(r.product || r.name || "").trim().toLowerCase();
      return name === q;
    });
  }, [rankedProducts, query]);
  const bestBranchId = recommendation?.best_overall?.branch_id;

  const visibleProducts = useMemo(() => {
    const distanceLimit = Number(maxDistance);
    const totalLimit = Number(maxTotal);
    const ratingLimit = Number(minRating);
    let rows = rankedProducts.filter((row) => {
      if (storeFilter !== "all" && String(row.branch_type || "").toLowerCase() !== storeFilter) return false;
      if (Number.isFinite(distanceLimit) && distanceLimit > 0 && num(row.distance_km, Infinity) > distanceLimit) return false;
      if (Number.isFinite(totalLimit) && totalLimit > 0 && num(row.grand_total, num(row.product_price, 0)) > totalLimit) return false;
      if (num(row.product_rating, num(row.rating, 0)) < ratingLimit) return false;
      return true;
    });
    if (sortMode !== "recommended") {
      rows = [...rows].sort((a, b) => {
        if (sortMode === "total_asc") return num(a.grand_total, Infinity) - num(b.grand_total, Infinity);
        if (sortMode === "price_asc") return num(a.product_price, Infinity) - num(b.product_price, Infinity);
        if (sortMode === "distance_asc") return num(a.distance_km, Infinity) - num(b.distance_km, Infinity);
        if (sortMode === "rating_desc") return num(b.product_rating, 0) - num(a.product_rating, 0);
        return 0;
      });
    }
    return rows;
  }, [maxDistance, maxTotal, minRating, rankedProducts, sortMode, storeFilter]);

  // pick which set to display depending on toggle
  const displayProducts = useMemo(() => {
    if (showExactOnly) return exactProducts;
    return visibleProducts;
  }, [showExactOnly, exactProducts, visibleProducts]);

  const filteredStores = useMemo(() => {
    if (storeTypeFilter === "all") return stores.items;
    return stores.items.filter((row) => String(row.type || "").toLowerCase() === storeTypeFilter);
  }, [storeTypeFilter, stores.items]);

  const mapBranches = useMemo(() => {
    if (activeView === "map" && stores.items.length > 0) {
      return stores.items
        .filter((row) => Number.isFinite(Number(row.lat)) && Number.isFinite(Number(row.lon)))
        .map((row) => ({
          branch_name: row.name,
          city: row.city,
          lat: Number(row.lat),
          lon: Number(row.lon),
          product_price: 0,
          distance_km: 0,
        }));
    }
    return (recommendation?.all_options || []).slice(0, 12);
  }, [activeView, stores.items, recommendation]);
  const activeDetail = catalogDetail
    ? { type: "catalog", item: catalogDetail }
    : storeDetail
      ? { type: "store", item: storeDetail }
      : null;
  const detailItem = activeDetail?.item || null;
  const detailType = activeDetail?.type || "";
  const detailTitle = detailType === "catalog"
    ? String(detailItem?.product || detailItem?.name || "Product")
    : String(detailItem?.name || "Store");
  const detailSubtitle = detailType === "catalog"
    ? String(detailItem?.source_store || detailItem?.store || "Unknown store")
    : [detailItem?.city, detailItem?.type].filter(Boolean).join(" • ");

  function handleShowMap(target) {
    if (!target || !Number.isFinite(Number(target.lat)) || !Number.isFinite(Number(target.lon))) return;
    setMapFocus({
      lat: Number(target.lat),
      lon: Number(target.lon),
      branch_name: target.store || target.branch_name || target.name || "Selected Store",
    });
    setActiveView("map");
  }

  useEffect(() => {
    setLocationDraft({
      lat: Number(location.lat).toFixed(6),
      lon: Number(location.lon).toFixed(6),
    });
  }, [location.lat, location.lon]);

  useEffect(() => {
    if (chatScrollRef.current) {
      chatScrollRef.current.scrollTop = chatScrollRef.current.scrollHeight;
    }
  }, [chatHistory, chatBusy]);

  useEffect(() => {
    if (!activeDetail) return;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        closeDetail();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeDetail, closeDetail]);

  function applyManualLocation() {
    const lat = Number(locationDraft.lat);
    const lon = Number(locationDraft.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      setLocationStatus("Invalid coordinates. Latitude must be -90..90 and longitude must be -180..180.");
      return;
    }
    setLocation({ lat, lon });
    setLocationStatus("Manual location applied successfully.");
    setLocationConfirmed(true);
  }

  function pickLocSuggestion(item) {
    setLocation({ lat: Number(item.lat), lon: Number(item.lon) });
    setLocationDraft({ lat: String(item.lat), lon: String(item.lon) });
    setLocationText(item.display_name);
    setLocSuggestions([]);
    setLocActiveIndex(-1);
    setLocationStatus("Location selected from suggestions.");
    setLocationConfirmed(true);
  }

  function detectLocation(silent = false) {
    if (!navigator?.geolocation) {
      if (!silent) {
        setLocationStatus("Auto-detect is not supported on this device or browser.");
      }
      return;
    }
    setDetectingLocation(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({
          lat: position.coords.latitude,
          lon: position.coords.longitude,
        });
        setLocationStatus("Location auto-detected successfully.");
        if (!silent) {
          setLocationConfirmed(true);
        }
        setDetectingLocation(false);
      },
      (geoError) => {
        const message = geoError?.message || "Location permission denied or unavailable.";
        setLocationStatus(`Auto-detect failed: ${message}`);
        setDetectingLocation(false);
      },
      { maximumAge: 120000, timeout: 4000, enableHighAccuracy: false },
    );
  }

  useEffect(() => {
    detectLocation(true);
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      setInsightsLoading(true);
      try {
        const payload = await getAIInsights({ user_lat: location.lat, user_lon: location.lon });
        if (!cancelled) setInsights(payload);
      } catch {
        if (!cancelled) setInsights(null);
      } finally {
        if (!cancelled) setInsightsLoading(false);
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [location.lat, location.lon]);

  useEffect(() => {
    if (activeView === "catalog" && !catalog.loaded && !catalog.loading) loadCatalog(false);
    if ((activeView === "stores" || activeView === "map") && !stores.loaded && !stores.loading) loadStores(false);
  }, [activeView]);

  useEffect(() => {
    let ctx;
    let mounted = true;
    async function bindScroll() {
      const module = await import("gsap/ScrollTrigger");
      if (!mounted) return;
      const { ScrollTrigger } = module;
      gsap.registerPlugin(ScrollTrigger);
      ctx = gsap.context(() => {
        gsap.utils.toArray(".reveal-block").forEach((node) => {
          gsap.fromTo(
            node,
            { y: 24, opacity: 0 },
            { y: 0, opacity: 1, duration: 0.5, ease: "power2.out", scrollTrigger: { trigger: node, start: "top 84%", once: true } },
          );
        });
      });
    }
    bindScroll();
    return () => {
      mounted = false;
      if (ctx) ctx.revert();
    };
  }, [activeView, visibleProducts.length, insights]);

  async function loadCatalog(force) {
    if (catalog.loading || (!force && catalog.loaded)) return;
    setCatalog((p) => ({ ...p, loading: true, error: "" }));
    try {
      const payload = await getProductsCatalog({ pages: 1 });
      setCatalog({ loaded: true, loading: false, items: payload?.products || [], error: "" });
    } catch (err) {
      setCatalog((p) => ({ ...p, loaded: true, loading: false, error: err?.message || "Failed to load catalog" }));
    }
  }

  async function loadStores(force) {
    if (stores.loading || (!force && stores.loaded)) return;
    setStores((p) => ({ ...p, loading: true, error: "" }));
    try {
      const payload = await getStores();
      setStores({ loaded: true, loading: false, items: payload?.stores || [], error: "" });
    } catch (err) {
      setStores((p) => ({ ...p, loaded: true, loading: false, error: err?.message || "Failed to load stores" }));
    }
  }

  async function runSearch(searchQuery) {
    const normalized = String(searchQuery || "").trim();
    if (!normalized) return;
    if (!locationConfirmed) {
      setPendingSearchQuery(normalized);
      setShowLocationConfirm(true);
      return;
    }
    setActiveView("optimizer");
    setHasSearched(true);
    setSearchLoading(true);
    setError("");
    setQuery(normalized);
    setShowExactOnly(false);
    setShowAdvanced(false); // keep filters collapsed on new search
    setChatHistory([]); // reset conversation
    setChatInput("");
    setChatBusy(false);

    try {
      const payload = {
        query: normalized,
        user_lat: location.lat,
        user_lon: location.lon,
        priority,
        store_filter: storeFilter,
        pages,
      };
      const budgetNumber = Number(budget);
      if (Number.isFinite(budgetNumber) && budgetNumber > 0) payload.budget = budgetNumber;

      const data = await getIntelligence(payload);
      if (data?.error) throw new Error(data.error);
      setIntelligence(data);
      setFallbackResults(Array.isArray(data?.category_products) ? data.category_products : []);

      let summaryText = data.summary || "";
      if (data.fallback === "loose_matching") {
        summaryText += " (note: no exact matches found; displaying closest available items.)";
      }

      const initialChat = {
        summary: summaryText,
        recommended_product: data?.best_option?.product || null,
        reason: data?.ai_reasoning || data?.buying_advice?.headline || data?.price_evaluation?.explanation || "",
        no_match: Boolean(data?.no_match),
      };
      setChatResult(initialChat);
      setChatHistory([{ role: "assistant", text: buildChatMessage(initialChat) }]);
      setChatBusy(true);
      chatWithAI(payload)
        .then((chat) => {
          if (chat && !chat.error) {
            setChatResult(chat);
            setChatHistory([{ role: "assistant", text: buildChatMessage(chat) }]);
          }
        })
        .catch(() => {})
        .finally(() => setChatBusy(false));
    } catch (err) {
      setIntelligence(null);
      try {
        const fallback = await searchProducts(normalized);
        const items = fallback?.products || [];
        setFallbackResults(items);
        const reason = String(err?.message || "AI request failed.").trim();
        const lower = reason.toLowerCase();
        let fallbackSummary = "Showing strict keyword fallback results for your query.";
        if (lower.includes("timed out") || lower.includes("timeout")) {
          fallbackSummary = "AI response timed out; strict keyword fallback results are shown.";
        } else if (lower.includes("401") || lower.includes("403") || lower.includes("unauthorized")) {
          fallbackSummary = "AI authentication failed; check GROQ_API_KEY and restart the backend.";
        } else if (lower.includes("groq")) {
          fallbackSummary = "Groq service is currently unreachable; strict keyword fallback results are shown.";
        }
        const fallbackChat = {
          summary: fallbackSummary,
          recommended_product: items[0]?.product || null,
          reason,
          no_match: items.length === 0,
        };
        setChatResult(fallbackChat);
        setChatHistory([{ role: "assistant", text: buildChatMessage(fallbackChat) }]);
        if (!items.length) setError("No products matched this search.");
      } catch (fallbackErr) {
        setFallbackResults([]);
        setChatResult(null);
        setError(fallbackErr?.message || err?.message || "Search failed.");
      }
    } finally {
      setSearchLoading(false);
    }
  }

  function confirmLocationAndSearch() {
    setLocationConfirmed(true);
    setShowLocationConfirm(false);
    if (pendingSearchQuery) {
      const queued = pendingSearchQuery;
      setPendingSearchQuery("");
      runSearch(queued);
    }
  }

  async function runCompare() {
    const a = compareState.productA.trim();
    const b = compareState.productB.trim();
    if (!a || !b) {
      setCompareState((p) => ({ ...p, error: "Enter both products", result: null }));
      return;
    }
    setCompareState((p) => ({ ...p, loading: true, error: "" }));
    try {
      const result = await compareProducts(a, b);
      setCompareState((p) => ({ ...p, loading: false, result }));
    } catch (err) {
      setCompareState((p) => ({ ...p, loading: false, error: err?.message || "Comparison failed" }));
    }
  }

  async function sendChat(messageOverride) {
    const text = String(messageOverride ?? chatInput).trim();
    if (!text || chatBusy) return;
    setChatHistory((h) => [...h, { role: "user", text }]);
    if (!messageOverride) setChatInput("");
    setChatBusy(true);
    try {
      const context = buildRecommendationContext(recommendation, chatResult);
      const fullQuery = context ? `${text}\nContext: Recommended product is ${context}.` : text;
      const payload = {
        query: fullQuery,
        user_lat: location.lat,
        user_lon: location.lon,
        priority,
        store_filter: storeFilter,
        pages,
      };
      const chat = await chatWithAI(payload);
      setChatHistory((h) => [...h, { role: "assistant", text: buildChatMessage(chat) }]);
    } catch (err) {
      setChatHistory((h) => [
        ...h,
        { role: "assistant", text: buildChatMessage({ error: err?.message || "AI chat failed." }) },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  return (
    <>
      <Head>
        <title>price_intelligence | AI Commerce Dashboard</title>
        <meta name="description" content="High scale recommendations based on price, model, distance, fuel and AI predictions." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </Head>

      <div className="relative min-h-screen text-white">
        <ParticleBackground />
        {showLocationConfirm && (
          <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4">
            <div className="glass-card w-full max-w-md rounded-2xl border border-white/15 p-5 text-slate-100">
              <h3 className="text-lg font-semibold text-white">Confirm location</h3>
              <p className="mt-2 text-sm text-slate-300">
                Use the current location ({location.lat.toFixed(4)}, {location.lon.toFixed(4)}) or enter a new one.
              </p>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <button
                  onClick={confirmLocationAndSearch}
                  className="flex-1 rounded-lg border border-cyan-300/40 bg-cyan-400/10 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-400/20"
                >
                  Use current location
                </button>
                <button
                  onClick={() => {
                    setShowLocationConfirm(false);
                    setActiveView("optimizer");
                    locationInputRef.current?.focus();
                  }}
                  className="flex-1 rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-slate-200 hover:bg-white/10"
                >
                  Enter location
                </button>
              </div>
            </div>
          </div>
        )}

        <header className="sticky top-0 z-50 border-b border-white/10 bg-[#090f1de0] backdrop-blur-xl">
          <div className="mx-auto flex max-w-[1380px] items-center justify-between px-4 py-3.5 sm:px-6 lg:px-8">
            <div className="flex items-center gap-3">
              <span className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 via-cyan-500 to-emerald-500 shadow-[0_0_26px_rgba(6,182,212,0.35)]">
                <Sparkles className="h-[18px] w-[18px]" />
              </span>
              <div><p className="text-sm font-semibold uppercase tracking-[0.16em] text-slate-300">price_intelligence</p><p className="text-xs text-slate-500">AI Shopping OS</p></div>
            </div>
            <nav className="hidden items-center gap-2 md:flex">
              {NAV_ITEMS.map((row) => (
                <button key={row.id} onClick={() => setActiveView(row.id)} className={`rounded-lg px-3 py-2 text-sm transition ${activeView === row.id ? "bg-cyan-400/20 text-cyan-200" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>{row.label}</button>
              ))}
            </nav>
            <button onClick={() => setMenuOpen((v) => !v)} className="inline-flex items-center justify-center rounded-lg border border-white/15 bg-white/5 p-2 text-slate-200 md:hidden">{menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}</button>
          </div>
          {menuOpen && (
            <div className="border-t border-white/10 bg-[#0a1122] px-4 py-3 md:hidden">
              {NAV_ITEMS.map((row) => (
                <button key={row.id} onClick={() => { setActiveView(row.id); setMenuOpen(false); }} className={`mb-1 block w-full rounded-lg px-3 py-2 text-left text-sm ${activeView === row.id ? "bg-cyan-400/20 text-cyan-200" : "text-slate-200 hover:bg-white/10"}`}>{row.label}</button>
              ))}
            </div>
          )}
        </header>

        <main className="relative z-10 mx-auto max-w-[1380px] px-4 pb-16 pt-5 sm:px-6 lg:px-8">
          {activeView === "optimizer" && (
            <>
              <HeroSection onSearchClick={() => searchAnchorRef.current?.scrollIntoView({ behavior: "smooth" })} />
              <section ref={searchAnchorRef} className="reveal-block mb-5"><SearchBar onSearch={runSearch} isLoading={searchLoading} /></section>

              {/* location selector always visible */}
              <section className="reveal-block mb-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
                <div className="relative">
                  <input
                    ref={locationInputRef}
                    value={locationText}
                    onChange={(e) => {
                      setLocationText(e.target.value);
                      setLocActiveIndex(-1);
                    }}
                    type="text"
                    placeholder="Type your area/place"
                    className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-white outline-none"
                    onKeyDown={(e) => {
                      if (locSuggestions.length) {
                        if (e.key === "ArrowDown") {
                          e.preventDefault();
                          setLocActiveIndex((i) => Math.min(i + 1, locSuggestions.length - 1));
                        } else if (e.key === "ArrowUp") {
                          e.preventDefault();
                          setLocActiveIndex((i) => (i <= 0 ? locSuggestions.length - 1 : i - 1));
                        } else if (e.key === "Enter") {
                          e.preventDefault();
                          const sel = locSuggestions[locActiveIndex] || locSuggestions[0];
                          if (sel) pickLocSuggestion(sel);
                        }
                      }
                    }}
                  />
                  {locSuggestions.length > 0 && (
                    <ul className="absolute z-50 mt-1 max-h-40 w-full overflow-auto rounded-lg bg-white text-black shadow-lg">
                      {locSuggestions.map((item, idx) => (
                        <li
                          key={`${item.display_name}-${idx}`}
                          className={`px-3 py-2 hover:bg-indigo-500/20 ${locActiveIndex === idx ? 'bg-indigo-500/30' : ''}`}
                          onMouseDown={(e) => { e.preventDefault(); pickLocSuggestion(item); }}
                        >
                          {item.display_name}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <input
                  value={locationDraft.lat}
                  onChange={(e) => setLocationDraft((prev) => ({ ...prev, lat: e.target.value }))}
                  type="text"
                  placeholder="Latitude"
                  className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-white outline-none"
                />
                <input
                  value={locationDraft.lon}
                  onChange={(e) => setLocationDraft((prev) => ({ ...prev, lon: e.target.value }))}
                  type="text"
                  placeholder="Longitude"
                  className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-white outline-none"
                />
                <button onClick={applyManualLocation} className="tilt-left-btn rounded-lg border border-cyan-300/30 bg-cyan-400/10 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-400/20">Apply Location</button>
                <button onClick={() => detectLocation(false)} disabled={detectingLocation} className="tilt-left-btn rounded-lg border border-emerald-300/30 bg-emerald-400/10 px-3 py-2 text-sm font-semibold text-emerald-100 hover:bg-emerald-400/20 disabled:cursor-not-allowed disabled:opacity-70">{detectingLocation ? "Detecting..." : "Auto Detect"}</button>
                <div className="rounded-lg border border-white/10 bg-white/5 px-2 py-2 text-xs text-slate-300 md:col-span-2 lg:col-span-2 xl:col-span-4">
                  Location: {location.lat.toFixed(4)}, {location.lon.toFixed(4)} | {locationStatus}
                </div>
                <div className="rounded-lg border border-cyan-400/25 bg-cyan-400/10 px-2 py-2 text-xs text-cyan-100 md:col-span-2 lg:col-span-2 xl:col-span-4 line-clamp-2">{query || "No active query"}</div>
              </section>

              <div className="mb-4 text-center">
                <button
                  onClick={() => setShowAdvanced((v) => !v)}
                  className="inline-flex items-center gap-2 rounded-lg border border-white/20 bg-white/5 px-4 py-2 text-sm text-slate-200 hover:bg-white/10"
                >
                  {showAdvanced ? "Hide filters" : "Show filters"}
                </button>
              </div>

              {showAdvanced && (
                <section className="reveal-block mb-5 grid grid-cols-1 gap-3 rounded-2xl border border-white/10 bg-[#0b1327]/70 p-4 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">
                  <select value={priority} onChange={(e) => setPriority(e.target.value)} className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-slate-100 outline-none"><option value="total_cost">Total Cost</option><option value="price">Cheapest Item</option><option value="distance">Nearest</option></select>
                  <select value={storeFilter} onChange={(e) => setStoreFilter(e.target.value)} className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-slate-100 outline-none"><option value="all">All Stores</option><option value="physical">Physical</option><option value="online">Online</option></select>
                  <input value={budget} onChange={(e) => setBudget(e.target.value)} type="number" min="0" placeholder="Budget PKR" className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-white outline-none" />
                  <select value={pages} onChange={(e) => setPages(Number(e.target.value))} className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-slate-100 outline-none"><option value={1}>Pages 1</option><option value={2}>Pages 2</option><option value={3}>Pages 3</option></select>
                </section>
              )}

              {error && <div className="reveal-block mb-5 flex items-start gap-3 rounded-2xl border border-rose-300/30 bg-rose-400/10 px-4 py-3 text-sm text-rose-100"><AlertTriangle className="mt-0.5 h-[18px] w-[18px] shrink-0" /><span>{error}</span></div>}


              {/* results and recommendation area only */}
              <div className="space-y-5">
                <div className="reveal-block grid grid-cols-1 gap-3 md:grid-cols-3">
                  <RecCard title="Best Overall" item={recommendation?.best_overall} color="text-cyan-200" />
                  <RecCard title="Cheapest" item={recommendation?.cheapest_item} color="text-emerald-200" />
                  <RecCard title="Nearest" item={recommendation?.nearest_branch} color="text-amber-200" />
                </div>

                <article className="reveal-block glass-card rounded-2xl border border-white/10 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm text-cyan-200"><Bot className="h-[18px] w-[18px]" />AI Recommendation Summary</div>
                  <p className="text-sm text-slate-200">
                    {intelligence?.summary || chatResult?.summary ? (
                      <span dangerouslySetInnerHTML={{ __html: toRichHtml(intelligence?.summary || chatResult?.summary) }} />
                    ) : (
                      "Search to generate AI recommendation text."
                    )}
                  </p>
                  {chatResult?.recommended_product && <p className="mt-2 text-sm font-semibold text-white">Recommended: {chatResult.recommended_product}</p>}
                </article>

                <article className="reveal-block glass-card rounded-2xl border border-white/10 p-4">
                  <div className="mb-2 flex items-center gap-2 text-sm text-cyan-200"><BrainCircuit className="h-4 w-4" />AI Reasoning and Prediction</div>
                  <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                    <div className="rounded-xl border border-white/10 bg-white/5 p-3"><p className="text-xs text-slate-400">Buying Advice</p><p className="text-sm font-bold text-white">{intelligence?.buying_advice?.action || "N/A"}</p><p className="text-xs text-slate-300">{intelligence?.buying_advice?.headline || "No advice yet."}</p></div>
                    <div className="rounded-xl border border-white/10 bg-white/5 p-3"><p className="text-xs text-slate-400">Price Prediction</p><p className="text-sm font-bold text-white">{intelligence?.price_prediction?.direction || intelligence?.price_prediction?.price_prediction || "N/A"}</p><p className="text-xs text-slate-300">{intelligence?.price_prediction?.explanation || intelligence?.price_prediction?.reason || "No trend details."}</p></div>
                    <div className="rounded-xl border border-white/10 bg-white/5 p-3"><p className="text-xs text-slate-400">Savings</p><p className="text-sm font-bold text-emerald-300">Rs. {num(intelligence?.savings_opportunity?.max_savings_on_total || intelligence?.savings_opportunity?.max_savings_on_price, 0).toLocaleString()}</p><p className="text-xs text-slate-300">{intelligence?.savings_opportunity?.explanation || "No savings data yet."}</p></div>
                  </div>
                  <div className="mt-3 rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200"><span dangerouslySetInnerHTML={{ __html: toRichHtml(intelligence?.ai_reasoning || "AI reasoning is not available for this query yet.") }} /></div>
                </article>

                <section className="reveal-block grid grid-cols-1 gap-3 rounded-2xl border border-white/10 bg-[#0b1327]/70 p-4 lg:grid-cols-5">
                  <select value={sortMode} onChange={(e) => setSortMode(e.target.value)} className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-slate-100 outline-none"><option value="recommended">Recommended</option><option value="total_asc">Total Low to High</option><option value="price_asc">Price Low to High</option><option value="distance_asc">Nearest First</option><option value="rating_desc">Highest Rated</option></select>
                  <input value={maxDistance} onChange={(e) => setMaxDistance(e.target.value)} type="number" min="0" placeholder="Max km" className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-white outline-none" />
                  <input value={maxTotal} onChange={(e) => setMaxTotal(e.target.value)} type="number" min="0" placeholder="Max total PKR" className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-white outline-none" />
                  <select value={minRating} onChange={(e) => setMinRating(e.target.value)} className="rounded-lg border border-white/15 bg-white/5 px-2 py-2 text-sm text-slate-100 outline-none"><option value="0">Any rating</option><option value="3">3+</option><option value="4">4+</option><option value="4.5">4.5+</option></select>
                  <button onClick={() => { setSortMode("recommended"); setMaxDistance(""); setMaxTotal(""); setMinRating("0"); }} className="tilt-left-btn rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-slate-200 hover:bg-white/10">Reset</button>
                  {/* filter toggle */}
                  {query && exactProducts.length > 0 && (
                    <div className="flex items-center gap-2 mt-2 lg:mt-0">
                      <button
                        onClick={() => setShowExactOnly(false)}
                        className={`rounded-lg px-3 py-1 text-xs font-semibold ${!showExactOnly ? "bg-cyan-400/20 text-cyan-200" : "bg-white/5 text-slate-200"}`}
                      >All ({visibleProducts.length})</button>
                      <button
                        onClick={() => setShowExactOnly(true)}
                        className={`rounded-lg px-3 py-1 text-xs font-semibold ${showExactOnly ? "bg-cyan-400/20 text-cyan-200" : "bg-white/5 text-slate-200"}`}
                      >Filter ({exactProducts.length})</button>
                    </div>
                  )}
                </section>

                <div className="reveal-block grid grid-cols-1 gap-4 md:grid-cols-2">
                  {searchLoading ? [1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-[300px] w-full rounded-2xl" />) : displayProducts.slice(0, 16).map((row, i) => <ProductCard key={`${row.branch_id || row.product}-${i}`} item={row} index={i} isBest={Boolean(bestBranchId) && row.branch_id === bestBranchId} onShowMap={handleShowMap} />)}
                  {!searchLoading && !displayProducts.length && <div className="glass-card col-span-full rounded-2xl border border-white/10 p-8 text-center text-slate-300">Search to get AI-ranked product recommendations with price, distance, fuel and prediction.</div>}
                </div>
                {/* Chat area */}
                {hasSearched && (
                  <section className="mt-6">
                    <div className="glass-card rounded-2xl border border-white/10 p-4">
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div>
                          <h4 className="text-lg font-bold text-white">Ask about this recommendation</h4>
                          <p className="text-xs text-slate-400">Clarify reasoning, alternatives, and availability.</p>
                        </div>
                        <span className={`rounded-full border px-3 py-1 text-[11px] uppercase tracking-[0.2em] ${chatBusy ? "border-cyan-400/40 bg-cyan-400/10 text-cyan-200" : "border-white/10 bg-white/5 text-slate-400"}`}>
                          {chatBusy ? "AI typing" : "Ready"}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-2">
                        {[
                          "Why was this item recommended?",
                          "Any cheaper alternatives?",
                          "Is there an online option?",
                          "How does the price compare to average?",
                        ].map((prompt) => (
                          <button
                            key={prompt}
                            type="button"
                            onClick={() => sendChat(prompt)}
                            className="rounded-full border border-white/20 bg-white/10 px-3 py-1.5 text-xs text-slate-200 transition hover:border-cyan-300/40 hover:bg-cyan-400/15"
                          >
                            {prompt}
                          </button>
                        ))}
                      </div>

                      <div ref={chatScrollRef} className="mt-4 max-h-72 overflow-auto space-y-3 pr-1">
                        <AnimatePresence initial={false}>
                          {chatHistory.map((msg, idx) => {
                            const isUser = msg.role === "user";
                            return (
                              <motion.div
                                key={`${msg.role}-${idx}`}
                                initial={{ opacity: 0, y: 10 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={{ opacity: 0, y: -6 }}
                                transition={{ duration: 0.2 }}
                                className={`flex ${isUser ? "justify-end" : "justify-start"}`}
                              >
                                <div
                                  className={`max-w-[85%] rounded-2xl border px-4 py-3 text-sm shadow-sm ${isUser ? "border-cyan-300/50 bg-cyan-400/30 text-cyan-50" : "border-white/20 bg-white/10 text-slate-100"}`}
                                >
                                  <div className="text-[10px] uppercase tracking-[0.2em] text-slate-400">
                                    {isUser ? "You" : "AI"}
                                  </div>
                                  <div
                                    className="mt-1 text-sm leading-relaxed text-slate-100 [&_ul]:ml-4 [&_ul]:list-disc [&_li]:mb-1 [&_p]:mb-2 [&_p:last-child]:mb-0"
                                    dangerouslySetInnerHTML={{ __html: toRichHtml(msg.text) }}
                                  />
                                </div>
                              </motion.div>
                            );
                          })}
                        </AnimatePresence>
                        {!chatHistory.length && (
                          <div className="rounded-xl border border-white/20 bg-white/10 px-3 py-3 text-xs text-slate-300">
                            Chat with the AI about your search results.
                          </div>
                        )}
                        {chatBusy && (
                          <div className="flex justify-start">
                            <div className="max-w-[70%] rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-xs text-slate-300 typing-cursor">
                              Thinking
                            </div>
                          </div>
                        )}
                      </div>

                      <form
                        className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center"
                        onSubmit={(e) => {
                          e.preventDefault();
                          sendChat();
                        }}
                      >
                        <input
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          disabled={chatBusy}
                          className="flex-1 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none disabled:opacity-70"
                          placeholder="Ask a question about the recommendation"
                        />
                        <button
                          type="submit"
                          disabled={chatBusy}
                          className="tilt-left-btn rounded-lg border border-cyan-300/30 bg-cyan-400/10 px-3 py-2 text-sm font-semibold text-cyan-100 hover:bg-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {chatBusy ? "Sending..." : "Send"}
                        </button>
                      </form>
                    </div>
                  </section>
                )}

                {hasSearched && (
                  <section className="mt-6">
                    <div className="glass-card rounded-2xl border border-white/10 p-4">
                      <h3 className="mb-3 text-lg font-bold text-white">Quick Compare</h3>
                      <div className="space-y-2">
                        <input value={compareState.productA} onChange={(e) => setCompareState((p) => ({ ...p, productA: e.target.value, error: "" }))} className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none" placeholder="Product A" />
                        <input value={compareState.productB} onChange={(e) => setCompareState((p) => ({ ...p, productB: e.target.value, error: "" }))} className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-white outline-none" placeholder="Product B" />
                        <div className="flex justify-end">
                          <button onClick={runCompare} className="ripple-btn rounded-lg bg-gradient-to-r from-indigo-500 to-cyan-500 px-3 py-1.5 text-xs font-semibold text-white">
                            {compareState.loading ? "Comparing..." : "Compare with AI"}
                          </button>
                        </div>
                        {compareState.error && <p className="text-xs text-rose-300">{compareState.error}</p>}
                        {compareState.result?.winner && <p className="text-xs text-emerald-300">Winner: {compareState.result.winner}</p>}
                      </div>
                    </div>
                  </section>
                )}
              </div>
            </>
          )}

          {activeView === "insights" && (
            <section className="reveal-block mb-8">
              <AIInsightsPanel
                insights={insights}
                intelligence={intelligence || chatResult}
                isLoading={insightsLoading}
              />
            </section>
          )}

          {activeView === "catalog" && (
            <section className="reveal-block space-y-4">
              <div className="flex items-center justify-between"><h2 className="text-2xl font-bold text-white">All Products Catalog</h2><button onClick={() => loadCatalog(true)} className="inline-flex items-center gap-2 rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-slate-200"><RefreshCcw className="h-4 w-4" />Refresh</button></div>
              {catalog.error && <div className="rounded-xl border border-rose-300/30 bg-rose-400/10 px-3 py-2 text-sm text-rose-200">{catalog.error}</div>}
              {catalog.loading ? <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{[1, 2, 3, 4, 5, 6].map((i) => <div key={i} className="skeleton h-40 w-full rounded-2xl" />)}</div> : <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{catalog.items.slice(0, 90).map((item, i) => <button key={`${item.product || "p"}-${i}`} type="button" onClick={() => openCatalogDetail(item)} className="glass-card rounded-2xl border border-white/10 p-4 text-left transition hover:border-cyan-300/40 hover:bg-white/5"><h3 className="line-clamp-2 text-sm font-bold text-white">{item.product || item.name}</h3><p className="mt-1 text-xs text-slate-300">{item.source_store || item.store || "Unknown store"}</p><p className="mt-2 text-base font-bold text-emerald-300">Rs. {num(item.price, 0).toLocaleString()}</p><p className="mt-1 text-xs text-slate-400">Rating: {num(item.rating, 0).toFixed(1)} | Reviews: {num(item.reviews, 0)}</p></button>)}</div>}
            </section>
          )}

          {activeView === "stores" && (
            <section className="reveal-block space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-2xl font-bold text-white">Store Directory</h2>
                <div className="flex items-center gap-2">
                  {["all", "physical", "online"].map((t) => <button key={t} onClick={() => setStoreTypeFilter(t)} className={`rounded-full px-3 py-1.5 text-xs uppercase tracking-[0.12em] ${storeTypeFilter === t ? "bg-cyan-400/20 text-cyan-200" : "border border-white/15 bg-white/5 text-slate-300"}`}>{t}</button>)}
                  <button onClick={() => loadStores(true)} className="inline-flex items-center gap-2 rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-slate-200"><RefreshCcw className="h-4 w-4" />Refresh</button>
                </div>
              </div>
              {stores.error && <div className="rounded-xl border border-rose-300/30 bg-rose-400/10 px-3 py-2 text-sm text-rose-200">{stores.error}</div>}
              {stores.loading ? <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{[1, 2, 3, 4].map((i) => <div key={i} className="skeleton h-32 w-full rounded-2xl" />)}</div> : <div className="grid grid-cols-1 gap-3 md:grid-cols-2">{filteredStores.map((row, i) => <button key={`${row.id || row.name}-${i}`} type="button" onClick={() => openStoreDetail(row)} className="glass-card rounded-2xl border border-white/10 p-4 text-left transition hover:border-cyan-300/40 hover:bg-white/5"><div className="flex items-start justify-between gap-2"><div><h3 className="text-base font-bold text-white">{row.name}</h3><p className="text-xs text-slate-300">{row.city}</p></div><span className={`rounded-full px-2.5 py-1 text-[11px] uppercase tracking-[0.1em] ${String(row.type).toLowerCase() === "online" ? "bg-emerald-400/15 text-emerald-200" : "bg-indigo-400/15 text-indigo-200"}`}>{row.type}</span></div><p className="mt-2 text-xs text-slate-400">{row.address || "Address unavailable"}</p><div className="mt-2 flex items-center gap-3 text-xs text-slate-300"><span className="inline-flex items-center gap-1"><Store className="h-3.5 w-3.5 text-cyan-300" />{row.url ? "Website available" : "No website"}</span><span className="inline-flex items-center gap-1"><MapPin className="h-3.5 w-3.5 text-cyan-300" />{num(row.lat, 0).toFixed(3)}, {num(row.lon, 0).toFixed(3)}</span></div></button>)}</div>}
            </section>
          )}

          {activeView === "map" && (
            <section className="reveal-block space-y-4">
              <div className="flex items-center justify-between"><h2 className="text-2xl font-bold text-white">Interactive Store Map</h2>{stores.loading ? <span className="inline-flex items-center gap-2 text-sm text-slate-300"><Loader2 className="h-4 w-4 animate-spin" />Loading stores</span> : <span className="text-sm text-slate-400">{mapBranches.length} mapped locations</span>}</div>
              <LocationMap branches={mapBranches} focus={mapFocus} />
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200">Ranking factors: price, distance, fuel cost, travel time, store reliability.</div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 inline-flex items-center gap-2"><Fuel className="h-4 w-4 text-amber-300" />Fuel is included in total cost; travel time is shown separately.</div>
                <div className="rounded-xl border border-white/10 bg-white/5 p-3 text-sm text-slate-200 inline-flex items-center gap-2"><TrendingUp className="h-4 w-4 text-cyan-300" />Price prediction confidence shown in recommendations.</div>
              </div>
            </section>
          )}

          <AnimatePresence>
            {activeDetail && (
              <motion.div
                className="fixed inset-0 z-[200] flex items-center justify-center bg-[#05070f]/80 px-4 py-6 backdrop-blur-sm"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={closeDetail}
              >
                <motion.div
                  initial={{ opacity: 0, y: 12, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 8, scale: 0.98 }}
                  transition={{ duration: 0.18 }}
                  onClick={(event) => event.stopPropagation()}
                  role="dialog"
                  aria-modal="true"
                  className="glass-card w-full max-w-2xl rounded-2xl border border-white/15 p-5 text-left shadow-2xl"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-xl font-bold text-white">{detailTitle}</h3>
                      {detailSubtitle && <p className="text-sm text-slate-300">{detailSubtitle}</p>}
                    </div>
                    <button
                      type="button"
                      onClick={closeDetail}
                      className="rounded-full border border-white/15 bg-white/5 p-2 text-slate-200 hover:bg-white/10"
                      aria-label="Close details"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>

                  {detailType === "catalog" && detailItem && (
                    <div className="mt-4 space-y-4">
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <DetailRow label="Price" value={`Rs. ${num(detailItem.price, 0).toLocaleString()}`} />
                        <DetailRow label="Rating" value={num(detailItem.rating, 0).toFixed(1)} />
                        <DetailRow label="Reviews" value={num(detailItem.reviews, 0).toLocaleString()} />
                        <DetailRow label="Category" value={detailItem.category || detailItem.category_label || "Electronics"} />
                        {typeof detailItem.in_stock === "boolean" && (
                          <DetailRow label="Availability" value={detailItem.in_stock ? "In stock" : "Out of stock"} />
                        )}
                      </div>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">Description</p>
                        <p className="mt-1 text-sm text-slate-200">
                          {detailItem.description || "No description provided yet."}
                        </p>
                      </div>
                      {(detailItem.product_url || detailItem.url || detailItem.source_url) && (
                        <div className="flex flex-wrap gap-2">
                          <a
                            href={detailItem.product_url || detailItem.url || detailItem.source_url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-lg border border-cyan-300/40 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-400/20"
                          >
                            Open product page
                          </a>
                        </div>
                      )}
                    </div>
                  )}

                  {detailType === "store" && detailItem && (
                    <div className="mt-4 space-y-4">
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <DetailRow label="Type" value={detailItem.type || "N/A"} />
                        <DetailRow label="City" value={detailItem.city || "N/A"} />
                        <DetailRow label="Phone" value={detailItem.phone || "N/A"} />
                        {Number.isFinite(Number(detailItem.lat)) && Number.isFinite(Number(detailItem.lon)) && (
                          <DetailRow label="Coordinates" value={`${Number(detailItem.lat).toFixed(3)}, ${Number(detailItem.lon).toFixed(3)}`} />
                        )}
                      </div>
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">About</p>
                        <p className="mt-1 text-sm text-slate-200">
                          {buildStoreAbout(detailItem) || "No additional details available."}
                        </p>
                      </div>
                      {detailItem.address && (
                        <div>
                          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-400">Address</p>
                          <p className="mt-1 text-sm text-slate-200">{detailItem.address}</p>
                        </div>
                      )}
                      <div className="flex flex-wrap gap-2">
                        {detailItem.url && (
                          <a
                            href={detailItem.url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-lg border border-cyan-300/40 bg-cyan-400/10 px-3 py-2 text-xs font-semibold text-cyan-100 hover:bg-cyan-400/20"
                          >
                            Visit website
                          </a>
                        )}
                        {String(detailItem.type || "").toLowerCase() === "physical" && Number.isFinite(Number(detailItem.lat)) && Number.isFinite(Number(detailItem.lon)) && (
                          <button
                            type="button"
                            onClick={() => {
                              handleShowMap(detailItem);
                              closeDetail();
                            }}
                            className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-white hover:bg-white/10"
                          >
                            Show on map
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </main>
      </div>
    </>
  );
}
