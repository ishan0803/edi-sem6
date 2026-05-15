"use client";
import { motion, useScroll, useTransform } from "framer-motion";
import Link from "next/link";
import { ArrowRight, MapPin, Activity, ShieldAlert, Cpu, Globe2, Network, Brain, Building2, Truck } from "lucide-react";
import { useRef } from "react";

export default function Home() {
  const containerRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end start"],
  });

  const headerY = useTransform(scrollYProgress, [0, 1], ["0%", "50%"]);
  const headerOpacity = useTransform(scrollYProgress, [0, 0.5], [1, 0]);

  return (
    <div ref={containerRef} className="relative min-h-screen bg-[#030305] text-white selection:bg-blue-500/30">

      {/* 1. Cinematic Background Elements — reduced blur for GPU perf */}
      <div className="fixed inset-0 cyber-grid pointer-events-none z-0" />
      <div className="fixed top-[-20%] left-[-10%] w-[50vw] h-[50vw] bg-blue-600/10 rounded-full blur-[100px] pointer-events-none mix-blend-screen z-0" style={{ contain: 'layout' }} />
      <div className="fixed bottom-[-20%] right-[-10%] w-[60vw] h-[60vw] bg-purple-600/10 rounded-full blur-[100px] pointer-events-none mix-blend-screen z-0" style={{ contain: 'layout' }} />

      {/* 2. Above-the-fold Hero Section */}
      <main className="relative z-10 flex flex-col items-center justify-center min-h-screen text-center px-6 overflow-hidden">

        {/* Floating Abstract Element */}
        <motion.div
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ duration: 1.5, ease: "easeOut" }}
          className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] border border-white/[0.02] rounded-full flex items-center justify-center"
        >
          <div className="w-[600px] h-[600px] border border-white/[0.04] rounded-full" />
          <div className="absolute w-[400px] h-[400px] border border-white/[0.08] rounded-full glow-primary" />
        </motion.div>

        <motion.div
          style={{ y: headerY, opacity: headerOpacity }}
          className="flex flex-col items-center relative z-20 max-w-5xl"
        >
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className="inline-flex items-center gap-3 px-4 py-2 rounded-full glass-panel text-xs font-mono tracking-widest text-blue-400 mb-8 uppercase"
          >
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
            </span>
            3D Friction-Aware Logistics Active
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 1, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
            className="text-6xl sm:text-7xl md:text-8xl lg:text-9xl font-extrabold tracking-tighter mb-6 leading-none"
          >
            Fulfillment <br className="hidden md:block" />
            <span className="text-gradient">Intelligence</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: "easeOut" }}
            className="text-lg md:text-xl text-gray-400 max-w-2xl mb-12 font-light tracking-wide leading-relaxed"
          >
            A 3D friction-aware quick commerce logistics engine meeting 10-minute SLAs.
            NLP address parsing, elevator delays, city-tier traffic, and GNN inventory rebalancing.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.3 }}
            className="flex flex-col sm:flex-row gap-6"
          >
            <Link
              href="/dashboard"
              className="group relative inline-flex items-center justify-center gap-3 px-8 py-5 bg-white text-black font-semibold rounded-xl overflow-hidden transition-all hover:scale-105 active:scale-95 glow-primary"
            >
              <span className="absolute inset-0 bg-gradient-to-r from-blue-100 to-white opacity-0 group-hover:opacity-100 transition-opacity" />
              <span className="relative z-10 flex items-center gap-2">
                Launch Engine <ArrowRight className="w-5 h-5 group-hover:translate-x-1 transition-transform" />
              </span>
            </Link>
          </motion.div>
        </motion.div>

        {/* Scroll Indicator */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1.5, duration: 1 }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2 text-gray-500"
        >
          <span className="text-xs uppercase tracking-widest font-mono">Discover Core</span>
          <div className="w-[1px] h-12 bg-gradient-to-b from-gray-500 to-transparent" />
        </motion.div>
      </main>

      {/* 3. Core Tech / Features Section */}
      <section className="relative z-10 py-32 px-6 max-w-7xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.8 }}
          className="text-center mb-24"
        >
          <h2 className="text-4xl md:text-5xl font-bold mb-4">Architected for <span className="text-blue-400">Scale</span></h2>
          <p className="text-gray-400 max-w-2xl mx-auto text-lg">Heavy-duty computational geometry combined with NLP, GNN, and VRP optimization.</p>
        </motion.div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          <FeatureCard icon={<MapPin className="text-blue-400 w-6 h-6" />} title="Spatial Routing"
            description="High-performance mapping using OpenStreetMap and NetworkX topologies. Calculate precise routes across millions of nodes." delay={0} />
          <FeatureCard icon={<Brain className="text-yellow-400 w-6 h-6" />} title="NLP Address Parsing (SAP)"
            description="spaCy-powered NLP extracts missing structural elements from messy Indian addresses. Calculates search-time penalties for riders." delay={0.05} />
          <FeatureCard icon={<Building2 className="text-pink-400 w-6 h-6" />} title="Z-Axis Friction (ZAFI)"
            description="Queries OSM building data to calculate elevator wait times and security gate delays. Redis-cached with geohash keys." delay={0.1} />
          <FeatureCard icon={<Activity className="text-purple-400 w-6 h-6" />} title="City-Tier Traffic"
            description="Dynamic scaling factors for Metro (1.0-1.2×) vs Tier-2/3 (0.5-0.7×) cities with automatic reverse geocoding." delay={0.15} />
          <FeatureCard icon={<Truck className="text-emerald-400 w-6 h-6" />} title="VRP Optimizer"
            description="OR-Tools Constraint Programming minimizes True Cost = Transit + SAP + ZAFI across configurable rider fleets with 10-min SLA." delay={0.2} />
          <FeatureCard icon={<Cpu className="text-cyan-400 w-6 h-6" />} title="GNN Inventory Engine"
            description="Graph Convolutional Network trained on synthetic demand data predicts stockouts and recommends inter-store inventory transfers." delay={0.25} />
          <FeatureCard icon={<ShieldAlert className="text-orange-400 w-6 h-6" />} title="Conflict Resolution"
            description="Automatic polygon differences calculation to yield unique coverage zones preventing overlapping fulfillment areas." delay={0.3} />
          <FeatureCard icon={<Globe2 className="text-emerald-400 w-6 h-6" />} title="Deck.gl Rendering"
            description="WebGL powered data visualization rendering coverage zones, VRP routes, and pin-to-ETA overlays at 60 FPS." delay={0.35} />
          <FeatureCard icon={<Network className="text-blue-400 w-6 h-6" />} title="FastAPI PostGIS"
            description="Asynchronous Python backend with ThreadPoolExecutor offloading for all heavy compute. Zero event-loop blocking." delay={0.4} />
        </div>
      </section>

      {/* 4. Footer */}
      <footer className="relative z-10 border-t border-white/5 py-12 px-6 mt-20">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center text-gray-500 text-sm">
          <div className="flex items-center gap-2 mb-4 md:mb-0">
            <div className="w-2 h-2 rounded-full bg-green-500" />
            Core Systems Operational
          </div>
          <p>© {new Date().getFullYear()} Quick Commerce Logistics Engine. EDI Sem 6.</p>
        </div>
      </footer>
    </div>
  );
}

function FeatureCard({ icon, title, description, delay }: { icon: React.ReactNode; title: string; description: string; delay: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-50px" }}
      transition={{ duration: 0.6, delay }}
      whileHover={{ y: -5 }}
      className="group p-8 rounded-3xl glass-panel relative overflow-hidden"
    >
      <div className="absolute inset-0 bg-gradient-to-br from-white/[0.05] to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
      <div className="relative z-10">
        <div className="w-14 h-14 rounded-2xl bg-white/5 flex items-center justify-center mb-6 border border-white/10 group-hover:scale-110 transition-transform duration-500 group-hover:border-white/20">
          {icon}
        </div>
        <h3 className="text-2xl font-bold mb-3 tracking-tight">{title}</h3>
        <p className="text-gray-400 leading-relaxed font-light">{description}</p>
      </div>
    </motion.div>
  );
}

