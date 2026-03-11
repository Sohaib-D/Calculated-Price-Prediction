import { motion } from "framer-motion";
import { BarChart3, BrainCircuit, Flame, Lightbulb, Percent, Sparkles } from "lucide-react";

function insightCardVariants(delay = 0) {
  return {
    hidden: { opacity: 0, y: 18, scale: 0.98 },
    show: {
      opacity: 1,
      y: 0,
      scale: 1,
      transition: { duration: 0.42, ease: "easeOut", delay },
    },
  };
}

function renderMetric(title, value, Icon, delay = 0) {
  return (
    <motion.div
      key={title}
      variants={insightCardVariants(delay)}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.3 }}
      className="glass-card rounded-2xl border border-white/10 p-4"
    >
      <div className="mb-2 flex items-center gap-2 text-sm text-slate-300">
        <Icon className="h-4 w-4 text-cyan-300" />
        {title}
      </div>
      <p className="text-2xl font-extrabold text-white">{value}</p>
    </motion.div>
  );
}

function listItem(title, subtitle, trailing) {
  return (
    <div
      key={`${title}-${subtitle || ""}`}
      className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2.5"
    >
      <div className="min-w-0">
        <p className="line-clamp-1 text-sm font-semibold text-white">{title}</p>
        {subtitle ? <p className="line-clamp-1 text-xs text-slate-400">{subtitle}</p> : null}
      </div>
      <div className="shrink-0 text-xs font-semibold text-cyan-200">{trailing}</div>
    </div>
  );
}

export default function AIInsightsPanel({ insights, intelligence, isLoading = false }) {
  if (isLoading) {
    return (
      <section className="space-y-4">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="skeleton h-[94px] w-full rounded-2xl" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {[1, 2].map((item) => (
            <div key={item} className="skeleton h-56 w-full rounded-2xl" />
          ))}
        </div>
      </section>
    );
  }

  const trending = insights?.trending_products || [];
  const drops = insights?.biggest_price_drops || [];
  const deals = insights?.best_deals_today || [];
  const categories = insights?.popular_categories || [];

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-xl font-bold sm:text-2xl">
          <BrainCircuit className="h-5 w-5 text-indigo-300" />
          AI Insights Panel
        </h2>
        {insights?.generated_at && (
          <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-400">
            Updated: {new Date(insights.generated_at).toLocaleTimeString()}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {renderMetric("Trending Products", trending.length, Flame, 0)}
        {renderMetric("Biggest Price Drops", drops.length, Percent, 0.05)}
        {renderMetric("Best Deals Today", deals.length, Sparkles, 0.1)}
        {renderMetric("Popular Categories", categories.length, BarChart3, 0.15)}
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <motion.div
          variants={insightCardVariants(0)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.25 }}
          className="glass-card rounded-2xl border border-white/10 p-4"
        >
          <h3 className="mb-3 text-lg font-bold text-white">Trending Products</h3>
          <div className="space-y-2">
            {(trending.length ? trending : [{ product: "No data yet", trend: "stable", confidence: 0 }])
              .slice(0, 5)
              .map((item) =>
                listItem(item.product, `${item.trend || "stable"} trend`, `${item.confidence || 0}%`),
              )}
          </div>
        </motion.div>

        <motion.div
          variants={insightCardVariants(0.05)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.25 }}
          className="glass-card rounded-2xl border border-white/10 p-4"
        >
          <h3 className="mb-3 text-lg font-bold text-white">Biggest Price Drops</h3>
          <div className="space-y-2">
            {(drops.length ? drops : [{ product: "No large drops detected", discount_percent: 0 }])
              .slice(0, 5)
              .map((item) => listItem(item.product, item.ai_message, `${item.discount_percent || 0}% off`))}
          </div>
        </motion.div>

        <motion.div
          variants={insightCardVariants(0.1)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.25 }}
          className="glass-card rounded-2xl border border-white/10 p-4"
        >
          <h3 className="mb-3 text-lg font-bold text-white">Best Deals Today</h3>
          <div className="space-y-2">
            {(deals.length ? deals : [{ product: "No deals yet", store: "", discount_percent: 0 }])
              .slice(0, 5)
              .map((item) => listItem(item.product, item.store, `${item.discount_percent || 0}%`))}
          </div>
        </motion.div>

        <motion.div
          variants={insightCardVariants(0.15)}
          initial="hidden"
          whileInView="show"
          viewport={{ once: true, amount: 0.25 }}
          className="glass-card rounded-2xl border border-white/10 p-4"
        >
          <h3 className="mb-3 text-lg font-bold text-white">AI Recommendations</h3>
          <div className="space-y-3">
            <p className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-200">
              {intelligence?.summary || "Search for a product to generate personalized AI buying guidance."}
            </p>
            <div className="space-y-2">
              {(insights?.popular_categories || []).slice(0, 4).map((item) =>
                listItem(item.category, "Category popularity", `${item.count || 0} items`),
              )}
            </div>
            {!categories.length && (
              <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-slate-300">
                <Lightbulb className="h-4 w-4 text-amber-300" />
                Run search to unlock category-level recommendations.
              </div>
            )}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
