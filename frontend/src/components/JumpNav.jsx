import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

const NAV_ITEMS = [
  { label: 'Top Picks', id: 'section-top-picks' },
  { label: 'Heatmap', id: 'section-heatmap' },
  { label: 'All Funds', id: 'section-all-funds' },
  { label: 'Backtest', id: 'section-backtest' },
];

export default function JumpNav() {
  const [visible, setVisible] = useState(false);
  const [active, setActive] = useState('');

  useEffect(() => {
    const onScroll = () => {
      setVisible(window.scrollY > 320);

      // Determine which section is in view
      for (const item of [...NAV_ITEMS].reverse()) {
        const el = document.getElementById(item.id);
        if (el) {
          const rect = el.getBoundingClientRect();
          if (rect.top <= 120) {
            setActive(item.id);
            return;
          }
        }
      }
      setActive('');
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const scrollTo = (id) => {
    const el = document.getElementById(id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <AnimatePresence>
      {visible && (
        <motion.nav
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 16 }}
          transition={{ duration: 0.25 }}
          className="fixed bottom-6 left-1/2 z-50"
          style={{ transform: 'translateX(-50%)' }}
        >
          <div
            className="flex items-center gap-1 px-2 py-1.5 rounded-full border border-gray-700/80 backdrop-blur-sm"
            style={{ backgroundColor: 'rgba(17,24,39,0.92)' }}
          >
            {NAV_ITEMS.map((item) => (
              <button
                key={item.id}
                onClick={() => scrollTo(item.id)}
                className={`px-3 py-1 rounded-full font-sans text-xs transition-all duration-200
                  ${active === item.id
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-700/50'
                    : 'text-gray-500 hover:text-gray-300'
                  }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </motion.nav>
      )}
    </AnimatePresence>
  );
}


