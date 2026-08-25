import { useEffect, useRef, useState } from "react";
import { Canvas } from "@react-three/fiber";

import Scene, { STATIONS } from "./scene.jsx";

/* The page is a tall empty scroller with a fixed canvas behind it. Scrolling
   does not move any HTML - it moves the camera, and the canvas is what you are
   actually looking at. The only flat things on top are the two you need hands
   for: the way in, and the way to the room. */

const SECTIONS = STATIONS.length + 2; // the title, each station, the publish end

export default function Landing() {
  const progress = useRef(0);
  const [entered, setEntered] = useState(false);
  const [atEnd, setAtEnd] = useState(false);

  useEffect(() => {
    function onScroll() {
      const scrollable = document.body.scrollHeight - window.innerHeight;
      const value = scrollable > 0 ? window.scrollY / scrollable : 0;
      progress.current = value;
      setAtEnd(value > 0.82);
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // The first paint is the title sitting still; the hint only earns its place
  // once someone has had a moment to look at it.
  useEffect(() => {
    const timer = setTimeout(() => setEntered(true), 900);
    return () => clearTimeout(timer);
  }, []);

  return (
    <>
      <div className="stage">
        <Canvas
          camera={{ fov: 62, near: 0.1, far: 220, position: [0, 0.6, 6] }}
          gl={{ antialias: true }}
          dpr={[1, 2]}
        >
          <color attach="background" args={["#06060a"]} />
          <fog attach="fog" args={["#06060a", 18, 96]} />
          <Scene progress={progress} />
        </Canvas>
      </div>

      <header className="top">
        <span className="wordmark">Santa Studio</span>
        <nav>
          <a href="/dashboard">Dashboard</a>
          <a href="/voice-studio">Voice</a>
          <a href="/room/">The Room</a>
        </nav>
      </header>

      <div className={"scroll-hint" + (entered && progress.current < 0.05 ? " show" : "")}>
        <span>scroll to walk through it</span>
        <i />
      </div>

      <div className={"cta" + (atEnd ? " show" : "")}>
        <a className="cta-primary" href="/dashboard">Start a run</a>
        <a className="cta-secondary" href="/room/">Walk into the room</a>
      </div>

      {/* What actually gives the page its scroll length. Nothing is drawn
          here - the canvas is - so it is deliberately empty. */}
      <div className="scroller" style={{ height: `${SECTIONS * 100}vh` }} aria-hidden="true" />

      {/* The same words as the scene, for anything that cannot see a canvas. */}
      <div className="sr-only">
        <h1>Santa Studio — a topic in, a finished sourced video out.</h1>
        {STATIONS.map((s) => (
          <section key={s.title}>
            <h2>{s.title}</h2>
            <p>{s.body}</p>
          </section>
        ))}
      </div>
    </>
  );
}
