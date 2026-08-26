import { useEffect, useRef, useState } from "react";

/* Arrive when scrolled to, once.

   An IntersectionObserver rather than a scroll listener: the browser does the
   work off the main thread, and a page with thirty of these still scrolls at
   sixty. Respects a reduced-motion preference by simply being visible. */

export default function Reveal({ children, delay = 0, as: Tag = "div", className = "" }) {
  const ref = useRef();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setShown(true);
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setShown(true);
          observer.disconnect();
        }
      },
      { rootMargin: "-12% 0px -8% 0px" }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`reveal${shown ? " in" : ""} ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </Tag>
  );
}
