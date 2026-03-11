import { motion } from "framer-motion";
import { ArrowUpRight, Flame } from "lucide-react";

export default function TrendingProducts({ isLoading = false, products = [] }) {
  const rows = products.length
    ? products
    : [
        { product: "iPhone 15", avg_price: 262000, trend: "rising", confidence: 76 },
        { product: "RTX 4060 Laptop", avg_price: 319000, trend: "stable", confidence: 61 },
        { product: "Pixel 8", avg_price: 195000, trend: "rising", confidence: 70 },
      ];

  return (
    <section className="glass-card rounded-2xl border border-white/10 p-4">
      <div className="mb-3 flex items-center gap-2">
        <Flame className="h-[18px] w-[18px] animate-pulse text-rose-300" />
        <h3 className="text-lg font-bold text-white">Trending Products</h3>
      </div>

      <div className="space-y-2">
        {isLoading
          ? [1, 2, 3].map((item) => <div key={item} className="skeleton h-12 w-full rounded-xl" />)
          : rows.slice(0, 5).map((item, index) => (
              <motion.div
                key={`${item.product}-${index}`}
                initial={{ opacity: 0, x: 14 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, amount: 0.35 }}
                transition={{ duration: 0.28, delay: index * 0.05 }}
                className="flex items-center justify-between gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5"
              >
                <div className="min-w-0">
                  <p className="line-clamp-1 text-sm font-semibold text-white">{item.product}</p>
                  <p className="text-xs text-slate-400">
                    Rs. {Number(item.avg_price || 0).toLocaleString()} avg
                  </p>
                </div>
                <div className="inline-flex items-center gap-1 rounded-full bg-emerald-400/15 px-2 py-1 text-xs font-semibold text-emerald-300">
                  <ArrowUpRight className="h-3.5 w-3.5" />
                  {item.confidence || 0}%
                </div>
              </motion.div>
            ))}
      </div>
    </section>
  );
}
