import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Compass, MapPinned } from "lucide-react";

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function markerCoordinates(branches) {
  if (!branches.length) return [];
  const latitudes = branches.map((item) => Number(item.lat)).filter((value) => Number.isFinite(value));
  const longitudes = branches.map((item) => Number(item.lon)).filter((value) => Number.isFinite(value));
  if (!latitudes.length || !longitudes.length) {
    return branches.map((item, index) => ({
      ...item,
      markerX: clamp(12 + (index * 19) % 76, 8, 92),
      markerY: clamp(20 + (index * 17) % 68, 10, 90),
    }));
  }

  const minLat = Math.min(...latitudes);
  const maxLat = Math.max(...latitudes);
  const minLon = Math.min(...longitudes);
  const maxLon = Math.max(...longitudes);

  const latRange = Math.max(0.0001, maxLat - minLat);
  const lonRange = Math.max(0.0001, maxLon - minLon);

  return branches.map((item) => {
    const lat = Number(item.lat);
    const lon = Number(item.lon);
    const markerX = Number.isFinite(lon) ? clamp(((lon - minLon) / lonRange) * 78 + 10, 8, 92) : 50;
    const markerY = Number.isFinite(lat) ? clamp((1 - (lat - minLat) / latRange) * 70 + 14, 10, 90) : 50;
    return { ...item, markerX, markerY };
  });
}

export default function LocationMap({ branches = [], focus = null }) {
  const [activeStore, setActiveStore] = useState(null);
  const focusBranch = focus && Number.isFinite(Number(focus.lat)) && Number.isFinite(Number(focus.lon))
    ? {
        branch_name: focus.branch_name || "Selected Store",
        city: focus.city || "Pakistan",
        lat: Number(focus.lat),
        lon: Number(focus.lon),
        product_price: focus.product_price || 0,
        distance_km: focus.distance_km || 0,
        isFocus: true,
      }
    : null;

  const baseBranches = branches.length
    ? branches.slice(0, 8)
    : [
        { branch_name: "Store One", city: "Islamabad", lat: 33.6844, lon: 73.0479, product_price: 238000, distance_km: 6.1 },
        { branch_name: "Store Two", city: "Lahore", lat: 31.5204, lon: 74.3587, product_price: 242000, distance_km: 8.7 },
        { branch_name: "Store Three", city: "Karachi", lat: 24.8607, lon: 67.0011, product_price: 245000, distance_km: 11.2 },
      ];

  const displayBranches = focusBranch
    ? [focusBranch, ...baseBranches.filter((item) => item.branch_name !== focusBranch.branch_name)].slice(0, 8)
    : baseBranches;

  const markers = useMemo(() => markerCoordinates(displayBranches), [displayBranches]);
  const center = (focusBranch && { lat: focusBranch.lat, lon: focusBranch.lon }) || markers[0] || { lat: 33.6844, lon: 73.0479 };
  const bbox = `${center.lon - 1.7},${center.lat - 1.2},${center.lon + 1.7},${center.lat + 1.2}`;
  const mapSrc = `https://www.openstreetmap.org/export/embed.html?bbox=${encodeURIComponent(
    bbox,
  )}&layer=mapnik&marker=${center.lat},${center.lon}`;

  return (
    <section className="glass-card relative overflow-hidden rounded-2xl border border-white/10 p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-lg font-bold text-white">
          <MapPinned className="h-[18px] w-[18px] text-cyan-300" />
          Store Map
        </h3>
        <span className="inline-flex items-center gap-1 rounded-full border border-cyan-300/30 bg-cyan-400/10 px-2.5 py-1 text-xs text-cyan-200">
          <Compass className="h-3.5 w-3.5 animate-spin" />
          Live
        </span>
      </div>

      <div className="relative h-[320px] overflow-hidden rounded-xl border border-white/12">
        <iframe
          title="Store map"
          src={mapSrc}
          className="h-full w-full border-0 opacity-70 saturate-0"
          loading="lazy"
          referrerPolicy="no-referrer-when-downgrade"
        />

        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-transparent via-[#091122]/25 to-[#091122]/45" />

        {markers.map((store, index) => (
          <motion.button
            key={`${store.branch_name}-${index}`}
            type="button"
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.28, delay: index * 0.04 }}
            onMouseEnter={() => setActiveStore(store)}
            onMouseLeave={() => setActiveStore(null)}
            onClick={() => setActiveStore((prev) => (prev?.branch_name === store.branch_name ? null : store))}
            className={`absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white shadow-[0_0_18px_rgba(34,211,238,0.75)] transition hover:scale-125 ${store.isFocus ? "h-5 w-5 bg-emerald-400" : "h-4 w-4 bg-cyan-400"}`}
            style={{ left: `${store.markerX}%`, top: `${store.markerY}%` }}
            aria-label={store.branch_name || "Store marker"}
          >
            <span className="absolute inset-0 animate-ping rounded-full bg-cyan-300/50" />
          </motion.button>
        ))}

        <AnimatePresence>
          {activeStore && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="glass-card absolute bottom-3 left-3 right-3 z-20 rounded-xl border border-white/15 p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="line-clamp-1 text-sm font-bold text-white">{activeStore.branch_name || "Store"}</p>
                  <p className="line-clamp-1 text-xs text-slate-400">{activeStore.city || "Pakistan"}</p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-extrabold text-emerald-300">
                    Rs. {Number(activeStore.product_price || 0).toLocaleString()}
                  </p>
                  <p className="text-xs text-slate-400">{Number(activeStore.distance_km || 0).toFixed(1)} km</p>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </section>
  );
}
