import { useMemo, useState } from "react";
import clsx from "clsx";
import { motion } from "framer-motion";
import { Fuel, Gauge, MapPin, Sparkles, Star, Tag, Timer } from "lucide-react";

const FALLBACK_IMAGE = "https://images.unsplash.com/photo-1526738549149-8e07eca6c147?auto=format&fit=crop&w=800&q=80";

function formatDuration(value) {
  const total = Math.round(Number(value) || 0);
  if (!Number.isFinite(total) || total <= 0) return "0m";

  const minute = 1;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;
  const month = 30 * day;
  const year = 365 * day;

  const plural = (num, singular, pluralLabel) => (num === 1 ? singular : pluralLabel);

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

export default function ProductCard({ item, index = 0, isBest = false, onShowMap }) {
  const [tilt, setTilt] = useState({ rotateX: 0, rotateY: 0 });

  const normalized = useMemo(() => {
    const row = item || {};
    const aiScoreRaw = Number(row.selection_score ?? row.score ?? 0);
    const aiScore = aiScoreRaw > 1 ? Math.round(aiScoreRaw) : Math.round(aiScoreRaw * 100);
    return {
      name: row.product || row.name || "Unknown Product",
      store: row.branch_name || row.source_store || row.store || "Unknown Store",
      price: Number(row.product_price ?? row.price ?? 0),
      totalCost: Number(row.grand_total ?? row.total_cost ?? row.product_price ?? row.price ?? 0),
      rating: Number(row.product_rating ?? row.rating ?? 0),
      distanceKm: Number(row.distance_km ?? 0),
      fuelCost: Number(row.fuel_cost ?? 0),
      durationMin: Number(row.duration_min ?? 0),
      // include coordinates so navigation buttons can function
      lat: Number(row.lat ?? row.branch_lat ?? row.latitude ?? 0),
      lon: Number(row.lon ?? row.branch_lon ?? row.longitude ?? 0),
      aiScore: Number.isFinite(aiScore) ? Math.max(0, aiScore) : 0,
      discountPercent: Number(row.discount_percent ?? 0),
      dealDetected: Boolean(row.deal_detected) || Number(row.discount_percent ?? 0) > 0,
      image: row.image || FALLBACK_IMAGE,
      prediction: row.price_prediction || "",
      confidence: Number(row.confidence ?? 0),
      branchType: row.branch_type || row.store_type || "",
    };
  }, [item]);

  const cardMotion = {
    hidden: { opacity: 0, y: 24 },
    show: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.45,
        ease: "easeOut",
        delay: index * 0.06,
      },
    },
  };

  function onMouseMove(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const px = x / rect.width;
    const py = y / rect.height;
    setTilt({
      rotateX: (0.5 - py) * 7,
      rotateY: (px - 0.5) * 9,
    });
  }

  return (
    <motion.article
      variants={cardMotion}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-30px" }}
      whileHover={{ y: -6, scale: 1.01 }}
      onMouseMove={onMouseMove}
      onMouseLeave={() => setTilt({ rotateX: 0, rotateY: 0 })}
      style={{
        rotateX: tilt.rotateX,
        rotateY: tilt.rotateY,
        transformPerspective: 1000,
        transformStyle: "preserve-3d",
      }}
      className={clsx(
        "group glass-card relative overflow-hidden rounded-2xl border border-white/15 p-4 transition-all duration-300 sm:p-5",
        isBest && "neo-glow border-indigo-400/60",
      )}
    >
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-indigo-500/12 via-transparent to-cyan-500/12 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />

      <div className="relative z-10 mb-3 flex items-start justify-between gap-2">
        <div className="flex flex-wrap gap-2">
          {isBest && (
            <span className="inline-flex items-center gap-1 rounded-full bg-indigo-500/20 px-2.5 py-1 text-[11px] font-semibold text-indigo-100">
              <Sparkles className="h-3.5 w-3.5" />
              AI Pick
            </span>
          )}
          {normalized.dealDetected && (
            <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/35 bg-emerald-400/15 px-2.5 py-1 text-[11px] font-bold text-emerald-300">
              <Tag className="h-3.5 w-3.5" />
              {normalized.discountPercent > 0 ? `${normalized.discountPercent}% Deal` : "Deal"}
            </span>
          )}
        </div>
        {normalized.rating > 0 && (
          <div className="inline-flex items-center gap-1 rounded-full border border-white/15 bg-white/10 px-2 py-1 text-xs font-semibold text-slate-200">
            <Star className="h-3.5 w-3.5 fill-amber-300 text-amber-300" />
            {normalized.rating.toFixed(1)}
          </div>
        )}
      </div>

      <div className="relative z-10 mb-4 overflow-hidden rounded-xl border border-white/10">
        <img
          src={normalized.image}
          alt={normalized.name}
          className="h-36 w-full object-cover transition-transform duration-500 group-hover:scale-105 sm:h-40"
          loading="lazy"
        />
      </div>

      <div className="relative z-10 space-y-2">
        <h3 className="line-clamp-2 text-base font-bold text-white sm:text-lg">{normalized.name}</h3>
        <p className="line-clamp-1 text-sm text-slate-300">
          {normalized.store}
          {normalized.branchType ? (
            <span className="ml-2 rounded-full border border-white/15 bg-white/10 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-300">
              {normalized.branchType}
            </span>
          ) : null}
        </p>
        <div className="flex items-end justify-between gap-2 pt-2">
          <div>
            <p className="text-[11px] uppercase tracking-[0.16em] text-slate-400">Price</p>
            <p className="text-xl font-extrabold text-white sm:text-2xl">Rs. {normalized.price.toLocaleString()}</p>
            {normalized.totalCost > 0 && (
              <p className="mt-1 text-xs font-semibold text-emerald-300">
                Total: Rs. {normalized.totalCost.toLocaleString()}
              </p>
            )}
          </div>
          <div className="text-right text-xs text-slate-300">
            <div className="mb-1 inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-1">
              <Gauge className="h-3.5 w-3.5 text-cyan-300" />
              AI {normalized.aiScore}
            </div>
            {normalized.distanceKm > 0 && (
              <div className="inline-flex items-center gap-1 text-[11px] text-slate-400">
                <MapPin className="h-3.5 w-3.5 text-indigo-300" />
                {normalized.distanceKm.toFixed(1)} km
              </div>
            )}
          </div>
          {/* route/navigation controls */}
          {(normalized.lat && normalized.lon) && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onShowMap?.(normalized)}
                className="rounded-lg border border-white/15 bg-white/5 px-3 py-1 text-xs font-semibold text-white hover:bg-white/10"
              >
                Show on Map
              </button>
            </div>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-[11px] text-slate-300">
          {normalized.fuelCost > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/10 px-2 py-1 text-amber-200">
              <Fuel className="h-3.5 w-3.5" />
              Fuel Rs. {normalized.fuelCost.toLocaleString()}
            </span>
          )}
          {normalized.durationMin > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-violet-400/10 px-2 py-1 text-violet-200">
              <Timer className="h-3.5 w-3.5" />
              Time {formatDuration(normalized.durationMin)}
            </span>
          )}
          {normalized.prediction && (
            <span className="inline-flex items-center gap-1 rounded-full bg-cyan-400/10 px-2 py-1 text-cyan-200">
              {normalized.prediction}
              {normalized.confidence > 0 ? ` (${normalized.confidence}%)` : ""}
            </span>
          )}
        </div>
      </div>
    </motion.article>
  );
}
