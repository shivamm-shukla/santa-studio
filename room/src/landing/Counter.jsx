import { useEffect, useRef, useState } from "react";

/* A number that counts up when it arrives.

   The same reasoning as the counters the pipeline draws over its own videos:
   a figure that is simply there is a caption, and a figure that arrives is
   something you read. Once only - a number that re-counts every time it
   scrolls past is a fidget. */

export default function Counter({ to, suffix = "", duration = 1100 }) {
  const ref = useRef();
  const [value, setValue] = useState(0);
  const done = useRef(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setValue(to);
      return;
    }

    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting || done.current) return;
      done.current = true;

      const started = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - started) / duration);
        // Eased out, so it decelerates onto the figure rather than stopping.
        setValue(Math.round(to * (1 - Math.pow(1 - t, 3))));
        if (t < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });

    observer.observe(node);
    return () => observer.disconnect();
  }, [to, duration]);

  return <b ref={ref}>{value}{suffix}</b>;
}
