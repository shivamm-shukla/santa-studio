import { useEffect, useRef, useState } from "react";

/* How far down the page you are, and which section owns that position.

   One listener for the whole page rather than one per effect: a landing with
   a dozen scroll-driven things on it is a dozen handlers fighting for the
   main thread otherwise, and the first thing to go is the smoothness that is
   the entire point. Everything reads off this. */

export default function useScrollScene(sections) {
  const [progress, setProgress] = useState(0);
  const [section, setSection] = useState(0);
  const frame = useRef(null);

  useEffect(() => {
    function measure() {
      frame.current = null;
      const scrollable = document.body.scrollHeight - window.innerHeight;
      const p = scrollable > 0 ? window.scrollY / scrollable : 0;
      setProgress(p);

      // Whichever marker is closest to a third of the way down the viewport -
      // roughly where the eye sits when reading.
      const line = window.innerHeight * 0.34;
      let best = 0;
      let bestDistance = Infinity;
      sections.forEach((id, i) => {
        const node = document.getElementById(id);
        if (!node) return;
        const distance = Math.abs(node.getBoundingClientRect().top - line);
        if (distance < bestDistance) {
          bestDistance = distance;
          best = i;
        }
      });
      setSection(best);
    }

    function onScroll() {
      if (!frame.current) frame.current = requestAnimationFrame(measure);
    }

    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame.current) cancelAnimationFrame(frame.current);
    };
  }, [sections]);

  return { progress, section };
}
