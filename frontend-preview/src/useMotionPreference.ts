import { useEffect, useLayoutEffect, useState } from 'react';

type Connection = EventTarget & { saveData?: boolean };
const connection = (navigator as Navigator & { connection?: Connection }).connection;

// Kept in App memory so navigating never silently restarts motion.
export default function useMotionPreference() {
  const [paused, setPaused] = useState(false);
  const [reduced, setReduced] = useState(() => matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [saveData, setSaveData] = useState(() => Boolean(connection?.saveData));
  const enabled = !paused && !reduced && !saveData;

  useEffect(() => {
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(query.matches);
    const updateData = () => setSaveData(Boolean(connection?.saveData));
    query.addEventListener('change', update);
    connection?.addEventListener('change', updateData);
    return () => {
      query.removeEventListener('change', update);
      connection?.removeEventListener('change', updateData);
    };
  }, []);

  useLayoutEffect(() => {
    document.documentElement.dataset.welcomeMotion = enabled ? 'on' : 'off';
  }, [enabled]);

  return { enabled, paused, reduced, saveData, toggle: () => setPaused(value => !value) };
}

export type MotionPreference = ReturnType<typeof useMotionPreference>;
