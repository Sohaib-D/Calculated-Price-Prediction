import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2, Search, Sparkles, X } from "lucide-react";
import { getSearchSuggestions } from "../utils/api";

const STATIC_SUGGESTIONS = ["iPhone 15", "iPhone 14 Pro", "Samsung S24", "Google Pixel 8"];
const PLACEHOLDERS = [
  "Try: cheap gaming laptop under 200k",
  "Try: iPhone 15 official PTA",
  "Try: best OLED TV deal today",
  "Try: compare MacBook vs Spectre",
];

export default function SearchBar({ onSearch, isLoading = false }) {
  const inputRef = useRef(null);
  const panelRef = useRef(null);
  const [query, setQuery] = useState("");
  const [isFocused, setIsFocused] = useState(false);
  const [suggestions, setSuggestions] = useState(STATIC_SUGGESTIONS);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [fetchingSuggestions, setFetchingSuggestions] = useState(false);

  const visibleSuggestions = useMemo(
    () => (suggestions.length ? suggestions.slice(0, 7) : STATIC_SUGGESTIONS),
    [suggestions],
  );

  useEffect(() => {
    const id = setInterval(() => {
      setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDERS.length);
    }, 2400);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const onShortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onShortcut);
    return () => window.removeEventListener("keydown", onShortcut);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const value = query.trim();
    const timeoutId = setTimeout(async () => {
      if (!value) {
        setSuggestions(STATIC_SUGGESTIONS);
        setActiveIndex(-1);
        return;
      }

      setFetchingSuggestions(true);
      const items = await getSearchSuggestions(value, 8);
      if (!cancelled) {
        setSuggestions(items.length ? items : STATIC_SUGGESTIONS);
        setActiveIndex(-1);
        setFetchingSuggestions(false);
      }
    }, 180);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [query]);

  function triggerSearch(nextQuery) {
    const trimmed = (nextQuery || "").trim();
    if (!trimmed || isLoading) return;
    setIsFocused(false);
    setActiveIndex(-1);
    onSearch(trimmed);
  }

  function handleKeyDown(event) {
    const hasPanel = isFocused && visibleSuggestions.length > 0;
    if (!hasPanel) {
      if (event.key === "Enter") {
        event.preventDefault();
        triggerSearch(query);
      }
      return;
    }

    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((prev) => (prev + 1) % visibleSuggestions.length);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? visibleSuggestions.length - 1 : prev - 1));
      return;
    }
    if (event.key === "Escape") {
      setIsFocused(false);
      setActiveIndex(-1);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0 && activeIndex < visibleSuggestions.length) {
        const selected = visibleSuggestions[activeIndex];
        setQuery(selected);
        triggerSearch(selected);
      } else {
        triggerSearch(query);
      }
    }
  }

  return (
    <div className="relative z-40 mx-auto w-full max-w-4xl px-1">
      <form
        onSubmit={(event) => {
          event.preventDefault();
          triggerSearch(query);
        }}
        className={`glass-card relative flex w-full items-center overflow-hidden rounded-2xl border transition-all duration-300 ${
          isFocused
            ? "border-indigo-400/75 shadow-[0_0_0_1px_rgba(99,102,241,0.3),0_0_24px_rgba(6,182,212,0.24)]"
            : "border-white/15"
        }`}
      >
        <div className="pl-4 sm:pl-5">
          {isLoading ? (
            <Loader2 className="h-5 w-5 animate-spin text-indigo-300" />
          ) : (
            <Search className="h-5 w-5 text-slate-300" />
          )}
        </div>

        <input
          ref={inputRef}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onFocus={() => setIsFocused(true)}
          onBlur={() => setTimeout(() => setIsFocused(false), 120)}
          onKeyDown={handleKeyDown}
          className="w-full bg-transparent px-3 py-4 text-base text-white outline-none placeholder:text-slate-400 sm:px-4 sm:py-5 sm:text-lg"
          placeholder={PLACEHOLDERS[placeholderIndex]}
          aria-label="Search for products"
        />

        {!!query && (
          <button
            type="button"
            onClick={() => {
              setQuery("");
              setSuggestions(STATIC_SUGGESTIONS);
              setActiveIndex(-1);
              inputRef.current?.focus();
            }}
            className="rounded-full p-2 text-slate-400 transition hover:text-white"
            aria-label="Clear search text"
          >
            <X className="h-[18px] w-[18px]" />
          </button>
        )}

        <button
          type="submit"
          onMouseDown={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            event.currentTarget.style.setProperty("--ripple-x", `${event.clientX - rect.left}px`);
            event.currentTarget.style.setProperty("--ripple-y", `${event.clientY - rect.top}px`);
          }}
          className="ripple-btn relative m-1 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-500 via-cyan-500 to-emerald-500 px-4 py-3 text-sm font-bold text-white transition hover:brightness-110 sm:px-5 sm:py-3.5"
          disabled={isLoading}
        >
          <Sparkles className="h-4 w-4" />
          <span className="hidden sm:inline">AI Search</span>
        </button>
      </form>

      <AnimatePresence>
        {isFocused && (
          <motion.div
            ref={panelRef}
            initial={{ opacity: 0, y: -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.18 }}
            className="glass-card neon-border absolute left-0 right-0 top-[calc(100%+0.65rem)] rounded-2xl border border-white/15 p-3 sm:p-4"
          >
            <div className="mb-2.5 flex items-center justify-between px-1 text-xs text-slate-400 sm:text-sm">
              <span>{query.trim() ? "AI Suggestions" : "Trending Searches"}</span>
              <span className="rounded-md bg-white/10 px-2 py-1 text-[10px] text-slate-300 sm:text-xs">
                Ctrl/Cmd + K
              </span>
            </div>

            <div className="space-y-1">
              {fetchingSuggestions ? (
                <div className="space-y-2 py-2">
                  {[1, 2, 3].map((item) => (
                    <div key={item} className="skeleton h-9 w-full" />
                  ))}
                </div>
              ) : (
                visibleSuggestions.map((suggestion, index) => (
                  <button
                    key={`${suggestion}-${index}`}
                    type="button"
                    onClick={() => {
                      setQuery(suggestion);
                      triggerSearch(suggestion);
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                    className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm text-slate-200 transition ${
                      activeIndex === index ? "bg-indigo-500/20 text-white" : "hover:bg-white/10"
                    }`}
                  >
                    <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
                    <span className="line-clamp-1">{suggestion}</span>
                  </button>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
