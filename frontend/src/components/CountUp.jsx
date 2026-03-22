import { useEffect, useRef, useState } from 'react';
import PropTypes from 'prop-types';

export function useCountUp(target, duration = 1200, delay = 150) {
  const [value, setValue] = useState(0);
  const rafRef = useRef(null);

  useEffect(() => {
    let startTime = null;

    const step = (timestamp) => {
      if (!startTime) startTime = timestamp + delay;
      if (timestamp < startTime) {
        rafRef.current = requestAnimationFrame(step);
        return;
      }
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // easeOutCubic
      setValue(target * eased);
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(step);
      }
    };

    rafRef.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(rafRef.current);
  }, [target, duration, delay]);

  return value;
}

export default function CountUp({ value, duration = 1200, delay = 150, decimals = 0 }) {
  const animated = useCountUp(value, duration, delay);
  return <>{decimals > 0 ? animated.toFixed(decimals) : Math.round(animated)}</>;
}

CountUp.propTypes = {
  value: PropTypes.number.isRequired,
  duration: PropTypes.number,
  delay: PropTypes.number,
  decimals: PropTypes.number,
};
