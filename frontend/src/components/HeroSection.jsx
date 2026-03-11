import { useEffect, useMemo, useRef, useState } from "react";
import { gsap } from "gsap";
import { Sparkles, Wand2 } from "lucide-react";

const STATIC_TITLE = "AI Price Intelligence Platform";
const ROTATING_PHRASES = [
  "Find the Best Deals",
  "Compare Products Instantly",
  "Shop Smarter with AI",
];

export default function HeroSection({ onSearchClick }) {
  const sectionRef = useRef(null);
  const titleRef = useRef(null);
  const subtitleRef = useRef(null);
  const ctaRef = useRef(null);
  const [phraseIndex, setPhraseIndex] = useState(0);
  const [typedText, setTypedText] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);

  const activePhrase = useMemo(() => ROTATING_PHRASES[phraseIndex], [phraseIndex]);

  useEffect(() => {
    const ctx = gsap.context(() => {
      const timeline = gsap.timeline({ defaults: { ease: "power4.out" } });
      timeline
        .fromTo(
          titleRef.current,
          { opacity: 0, y: 26, filter: "blur(8px)" },
          { opacity: 1, y: 0, filter: "blur(0px)", duration: 1.1 },
        )
        .fromTo(
          subtitleRef.current,
          { opacity: 0, y: 24 },
          { opacity: 1, y: 0, duration: 0.8 },
          "-=0.65",
        )
        .fromTo(
          ctaRef.current,
          { opacity: 0, y: 20, scale: 0.98 },
          { opacity: 1, y: 0, scale: 1, duration: 0.75 },
          "-=0.45",
        );
    }, sectionRef);

    return () => ctx.revert();
  }, []);

  useEffect(() => {
    const pauseAfterType = 1200;
    const pauseAfterDelete = 350;
    const typeSpeed = isDeleting ? 40 : 75;
    let timeoutId;

    if (!isDeleting && typedText === activePhrase) {
      timeoutId = setTimeout(() => setIsDeleting(true), pauseAfterType);
      return () => clearTimeout(timeoutId);
    }
    if (isDeleting && typedText.length === 0) {
      timeoutId = setTimeout(() => {
        setIsDeleting(false);
        setPhraseIndex((prev) => (prev + 1) % ROTATING_PHRASES.length);
      }, pauseAfterDelete);
      return () => clearTimeout(timeoutId);
    }

    timeoutId = setTimeout(() => {
      const nextLength = typedText.length + (isDeleting ? -1 : 1);
      setTypedText(activePhrase.slice(0, Math.max(0, nextLength)));
    }, typeSpeed);

    return () => clearTimeout(timeoutId);
  }, [activePhrase, isDeleting, typedText]);

  return (
    <section
      ref={sectionRef}
      className="relative z-10 mx-auto flex w-full max-w-6xl flex-col items-center px-4 pb-8 pt-10 text-center sm:pb-12 sm:pt-16"
    >
      <div className="pointer-events-none absolute -top-16 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-cyan-400/15 blur-[90px]" />
      <div className="pointer-events-none absolute bottom-0 right-[8%] h-52 w-52 rounded-full bg-indigo-500/20 blur-[110px]" />

      <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100">
        <Sparkles className="h-3.5 w-3.5 text-cyan-300" />
        AI Shopping Cockpit
      </div>

      <h1
        ref={titleRef}
        className="max-w-5xl text-4xl font-extrabold leading-tight sm:text-5xl md:text-6xl lg:text-7xl"
      >
        {STATIC_TITLE.split(" ").slice(0, 2).join(" ")}{" "}
        <span className="text-gradient">{STATIC_TITLE.split(" ").slice(2).join(" ")}</span>
      </h1>

      <p
        ref={subtitleRef}
        className="typing-cursor mt-5 min-h-[34px] text-lg font-medium text-slate-300 sm:min-h-[40px] sm:text-2xl"
      >
        {typedText}
      </p>

      <button
        ref={ctaRef}
        type="button"
        onClick={onSearchClick}
        className="ripple-btn neon-border glass-card neo-glow mt-9 inline-flex items-center gap-2 rounded-full px-7 py-3.5 text-sm font-semibold text-white transition-all duration-300 hover:-translate-y-0.5 hover:scale-[1.02] sm:text-base"
      >
        <Wand2 className="h-[18px] w-[18px] text-cyan-300" />
        Launch AI Search
      </button>

      <div className="mt-11 grid w-full max-w-3xl grid-cols-2 gap-3 text-left text-xs text-slate-300 sm:grid-cols-4 sm:text-sm">
        {[
          "30+ Stores Synced",
          "Real-Time Insights",
          "Semantic AI Search",
          "Smart Deal Detection",
        ].map((item) => (
          <div key={item} className="glass-card rounded-xl border border-white/10 px-3 py-2.5 text-center">
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}
