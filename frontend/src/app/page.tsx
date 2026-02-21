"use client";
import { motion } from "framer-motion";
import Link from "next/link";
import { ArrowRight, MapPin, Activity, ShieldAlert } from "lucide-react";

export default function Home() {
  return (
    <div className="relative min-h-screen overflow-hidden flex flex-col items-center justify-center">
      {/* Background glow effects */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-600/20 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-purple-600/20 rounded-full blur-[120px] pointer-events-none" />

      {/* Grid pattern */}
      <div className="absolute inset-0 bg-[url('/grid.svg')] bg-center [mask-image:linear-gradient(180deg,white,rgba(255,255,255,0))] opacity-10" />

      <main className="z-10 flex flex-col items-center text-center px-6 max-w-5xl">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
          className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-sm text-blue-400 mb-8"
        >
          <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
          System Active
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-6xl md:text-8xl font-bold tracking-tight mb-6"
        >
          Fulfillment <span className="text-gradient">Intelligence</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="text-lg md:text-xl text-gray-400 max-w-2xl mb-12"
        >
          A production-grade geospatial engine for analyzing multi-location service areas.
          Track, optimize, and compute real-time distance and time-based isochrones.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3 }}
          className="flex flex-col sm:flex-row gap-4"
        >
          <Link
            href="/dashboard"
            className="group relative inline-flex items-center justify-center gap-2 px-8 py-4 bg-white text-black font-medium rounded-lg overflow-hidden transition-all hover:scale-105 active:scale-95"
          >
            <span className="relative z-10 flex items-center gap-2">
              Launch Dashboard <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </span>
          </Link>
          <button className="px-8 py-4 bg-white/5 border border-white/10 text-white font-medium rounded-lg hover:bg-white/10 transition-colors">
            View Documentation
          </button>
        </motion.div>

        {/* Feature Highlights */}
        <motion.div
          initial={{ opacity: 0, y: 40 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.5 }}
          className="mt-32 grid grid-cols-1 md:grid-cols-3 gap-8 w-full text-left"
        >
          <FeatureCard
            icon={<MapPin className="text-blue-400" />}
            title="Spatial Routing"
            description="High-performance mapping using OpenStreetMap and NetworkX topologies."
          />
          <FeatureCard
            icon={<Activity className="text-purple-400" />}
            title="Live Traffic Multipliers"
            description="Dynamic time-bands adjusted by localized traffic congestion metrics."
          />
          <FeatureCard
            icon={<ShieldAlert className="text-pink-400" />}
            title="Conflict Resolution"
            description="Automatic polygon differences calculation to yield unique coverage zones."
          />
        </motion.div>
      </main>
    </div>
  );
}

function FeatureCard({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <div className="p-6 rounded-2xl bg-white/5 border border-white/10 backdrop-blur-sm hover:bg-white/10 transition-colors">
      <div className="w-12 h-12 rounded-lg bg-white/5 flex items-center justify-center mb-4 border border-white/5">
        {icon}
      </div>
      <h3 className="text-xl font-semibold mb-2">{title}</h3>
      <p className="text-gray-400 leading-relaxed">{description}</p>
    </div>
  );
}
