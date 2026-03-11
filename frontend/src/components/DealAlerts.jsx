import { motion } from "framer-motion";
import { Zap } from "lucide-react";

const FALLBACK = [
  { product: "MacBook Pro M3", discount_percent: 12, ai_message: "Strong short-term discount detected." },
  { product: "Samsung S24", discount_percent: 9, ai_message: "Price touched weekly low across stores." },
];

export default function DealAlerts({ alerts = [] }) {
  const items = alerts.length ? alerts : FALLBACK;
  return (
    <section className="glass-card relative overflow-hidden rounded-2xl border border-amber-300/25 p-4">
      <div className="pointer-events-none absolute -right-8 -top-10 h-28 w-28 rounded-full bg-amber-300/20 blur-3xl" />

      <div className="mb-3 flex items-center gap-2">
        <span className="relative inline-flex h-8 w-8 items-center justify-center rounded-full bg-amber-400/20">
          <span className="absolute h-5 w-5 animate-ping rounded-full bg-amber-300/45" />
          <Zap className="relative z-10 h-4 w-4 text-amber-300" />
        </span>
        <h3 className="text-lg font-bold text-white">AI Deal Alerts</h3>
      </div>

      <div className="space-y-2.5">
        {items.slice(0, 4).map((alert, index) => (
          <motion.div
            key={`${alert.product}-${index}`}
            initial={{ opacity: 0, x: 16 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, amount: 0.4 }}
            transition={{ duration: 0.32, delay: index * 0.06 }}
            className="rounded-xl border border-amber-300/20 bg-amber-300/5 p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="line-clamp-1 text-sm font-semibold text-white">{alert.product}</p>
              <span className="rounded-full bg-amber-300/20 px-2 py-0.5 text-xs font-bold text-amber-200">
                -{alert.discount_percent || 0}%
              </span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-slate-300">
              {alert.ai_message || "AI detected an unusual price drop for this listing."}
            </p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}
