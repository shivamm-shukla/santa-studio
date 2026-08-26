import { useEffect, useRef, useState } from "react";
import Counter from "./Counter.jsx";
import Reveal from "./Reveal.jsx";
import useScrollScene from "./useScrollScene.js";
import useTheme from "./useTheme.js";
import { DELIVERABLES, PLACES, SECTIONS, STEPS, TICKER, TRUTHS } from "./content.js";

/* The front door.

   Deliberately not 3D. The studio is the 3D thing and it is one click away;
   a landing page that makes you fly through a tunnel to read a sentence is
   showing off, and it was also overlapping its own text. This is flat, fast
   and animated, and the one place it shows the studio it shows a photograph
   of the real one - taken through a real browser by shoot.mjs, in both
   lighting states, so the pictures are never lit the opposite way to the page
   they are sitting on. */

function Rail() {
  /* The pipeline as a rail that travels sideways while you scroll down.
     Driven by where the section sits in the viewport rather than by a
     scroll-jacking library, so the page never takes the wheel off you. */
  const section = useRef();
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    let frame = null;
    function onScroll() {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = null;
        const node = section.current;
        if (!node) return;
        const rect = node.getBoundingClientRect();
        const travel = rect.height - window.innerHeight;
        if (travel <= 0) return;
        setProgress(Math.min(1, Math.max(0, -rect.top / travel)));
      });
    }
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, []);

  /* Where the rail is, as a fractional card index. Everything below is
     positioned off this one number. */
  const at = progress * (STEPS.length - 1);

  return (
    <section className="rail-section" ref={section} style={{ height: `${STEPS.length * 82}vh` }}>
      <div className="rail-sticky">
        <div className="wrap">
          <div className="eyebrow">how it works</div>
          <h2>Six things happen, in order.</h2>
        </div>

        {/* A circle seen edge-on rather than a strip sliding past: cards swing
            round on an arc, turning to face you as they reach the middle and
            falling back and away as they leave. The first version slid them
            flat and dimmed them slightly, which reads as a filmstrip - there
            was nothing to arrive at. */}
        <div className="rail-stage">
          {STEPS.map((step, i) => {
            const offset = i - at;
            const away = Math.abs(offset);

            // Past two cards out there is nothing worth drawing.
            if (away > 2.6) return null;

            /* Positions come off an actual circle rather than a fudged
               slide: the angle is the offset, and x/z are its sine and
               cosine. That is what makes the far cards swing behind the near
               one instead of stacking beside it. The small lift and roll on
               the way past are what stop it reading as a machine. */
            const angle = offset * 0.62;              // radians around the arc
            const x = Math.sin(angle) * 62;           // % of the card's width
            const z = (Math.cos(angle) - 1) * 460;    // px, negative going back
            const lift = (1 - Math.cos(angle)) * 54;  // px, dropping away
            const roll = offset * -2.6;               // deg, a slight tilt

            const style = {
              transform: [
                `translateX(${x}%)`,
                `translateY(${lift}px)`,
                `translateZ(${z}px)`,
                `rotateY(${angle * -46}deg)`,
                `rotateZ(${roll}deg)`,
                `scale(${1 - Math.min(away, 2) * 0.05})`,
              ].join(" "),
              opacity: Math.max(0, 1 - away * 0.44),
              filter: `blur(${Math.min(away * 1.7, 5)}px) brightness(${1 - Math.min(away, 2) * 0.3}) saturate(${1 - Math.min(away, 2) * 0.35})`,
              zIndex: 100 - Math.round(away * 10),
            };

            return (
              <article className={"rail-card" + (away < 0.5 ? " here" : "")} key={step.n} style={style}>
                <span className="rail-n">{step.n}</span>
                <h3>{step.title}</h3>
                <p>{step.body}</p>
                <span className="rail-note">{step.note}</span>
              </article>
            );
          })}
        </div>

        <div className="rail-dots">
          {STEPS.map((step, i) => (
            <i key={step.n} className={Math.round(at) === i ? "on" : ""} />
          ))}
        </div>
      </div>
    </section>
  );
}

function Places({ theme }) {
  const [open, setOpen] = useState(PLACES[0].id);
  const [held, setHeld] = useState(false);
  const [tick, setTick] = useState(0);
  const [tilt, setTilt] = useState({ rx: 0, ry: 0 });
  const place = PLACES.find((p) => p.id === open) ?? PLACES[0];
  const index = PLACES.findIndex((p) => p.id === place.id);

  /* It walks itself round the studio. A row of tabs waiting to be clicked is
     a thing a visitor has to work out; a tour that is already running is one
     they can just watch. Touching it stops the clock, because taking control
     away from someone who has just taken it is rude. */
  const DWELL = 5200;
  useEffect(() => {
    if (held) return undefined;
    setTick(0);
    const started = Date.now();
    const timer = setInterval(() => {
      const done = (Date.now() - started) / DWELL;
      if (done >= 1) {
        setOpen(PLACES[(index + 1) % PLACES.length].id);
      } else {
        setTick(done);
      }
    }, 90);
    return () => clearInterval(timer);
  }, [index, held]);

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setTilt({
      rx: ((e.clientX - rect.left) / rect.width - 0.5) * 7,
      ry: ((e.clientY - rect.top) / rect.height - 0.5) * 7,
    });
  };

  return (
    <section className="places-section">
      <div className="wrap">
        <Reveal>
          <div className="eyebrow">the studio</div>
          <h2>It is a place, not a dashboard.</h2>
          <p className="lede">
            Work lands on desks. Decisions come up on the screen by the table.
            You record in a booth with a door.
          </p>
        </Reveal>

        <Reveal delay={80}>
          <div className="places-tabs">
            {PLACES.map((p) => (
              <button
                key={p.id}
                className={p.id === open ? "on" : ""}
                onClick={() => { setOpen(p.id); setHeld(true); }}
              >
                {p.title}
              </button>
            ))}
          </div>
        </Reveal>

        <Reveal delay={140} className="shot-stage">
          <div
            className="shot-frame"
            style={{ "--rx": tilt.rx, "--ry": tilt.ry }}
            onPointerMove={onMove}
            onPointerEnter={() => setHeld(true)}
            onPointerLeave={() => { setHeld(false); setTilt({ rx: 0, ry: 0 }); }}
          >
            <div className="shot-chrome">
              <i /><i /><i />
              <span>{`localhost:8000/room/${place.at}`}</span>
              <span className="shot-live"><b />the real thing</span>
            </div>

            <div className="shot-wrap">
              {/* Keyed on both, so switching either the place or the lights
                  re-runs the fade rather than swapping the picture underneath. */}
              <img
                key={`${place.id}-${theme}`}
                className="shot"
                src={`/room/shots/${place.id}-${theme}.png`}
                alt={place.title}
                loading="lazy"
              />
              <div className="shot-sheen" aria-hidden="true" />
            </div>

            <div className="shot-tick" aria-hidden="true">
              <i style={{ width: `${(held ? 0 : tick) * 100}%` }} />
            </div>

            <div className="shot-caption">
              <b>{place.title}</b>
              <span>{place.body}</span>
              <a className="btn ghost" href={`/room/${place.at}`}>Walk in →</a>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

function Ticker() {
  /* Two copies of the list, running end to end, so the loop has no seam. */
  const line = [...TICKER, ...TICKER];
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker-line">
        {line.map((word, i) => (
          <span key={i}>{word}<i>·</i></span>
        ))}
      </div>
    </div>
  );
}

function Deliverables() {
  return (
    <section className="out-section" id="sec-out">
      <div className="wrap">
        <Reveal>
          <div className="eyebrow">what you are left with</div>
          <h2>Every run leaves five things on disk.</h2>
        </Reveal>
        <div className="out-list">
          {DELIVERABLES.map(([title, body], i) => (
            <Reveal as="article" className="out-row" key={title} delay={i * 70}>
              <b>{title}</b>
              <span>{body}</span>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Landing() {
  const { theme, toggle } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const { progress, section } = useScrollScene(SECTIONS.map((s) => s.id));
  const [pointer, setPointer] = useState({ x: 0.5, y: 0.5 });

  const tint = SECTIONS[section]?.tint ?? SECTIONS[0].tint;

  const onHeroMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setPointer({
      x: (e.clientX - rect.left) / rect.width,
      y: (e.clientY - rect.top) / rect.height,
    });
  };

  const heroGlow = {
    transform: `translate3d(${(pointer.x - 0.5) * 34}px, ${(pointer.y - 0.5) * 24}px, 0)`,
  };

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
      {/* The page's colour travels with you. Each section owns a hue and the
          background eases between them, so scrolling feels like moving
          through somewhere rather than down a wall of one colour. */}
      <div
        className="tint"
        aria-hidden="true"
        style={{ "--tint": tint, "--depth": progress }}
      />

      <header className={"top" + (scrolled ? " stuck" : "")}>
        <a className="wordmark" href="/">
          <b>Santa Studio</b>
        </a>
        <nav>
          <a href="#how">How it works</a>
          <a href="#studio">The studio</a>
          <a href="/room/">Open the studio</a>
          <button className="lights" onClick={toggle}>
            <i className="bulb" />
            {theme === "light" ? "Lights off" : "Lights on"}
          </button>
        </nav>
      </header>

      <main>
        <section className="hero" id="sec-hero" onPointerMove={onHeroMove}>
          <div className="hero-glow" aria-hidden="true" style={heroGlow} />
          <div className="wrap">
            <Reveal as="div"><div className="eyebrow">Santa Studio</div></Reveal>
            <Reveal as="h1" delay={60}>
              <span>Give it a topic.</span>
              <span>Get back a video<br />with its sources attached.</span>
            </Reveal>
            <Reveal as="p" delay={140} className="lede">
              It researches the subject, checks the claims against the sources
              that made them, writes the script, reads it in your own voice,
              finds the footage, and cuts the whole thing. You sign off where
              it counts.
            </Reveal>
            <Reveal delay={220}>
              <div className="hero-actions">
                <a className="btn primary" href="/room/?at=board">Commission a video</a>
                <a className="btn ghost" href="/room/">Walk into the studio</a>
              </div>
            </Reveal>
            <Reveal delay={300}>
              <ul className="hero-facts">
                <li><Counter to={3} /><span>research indexes, no keys</span></li>
                <li><Counter to={8} suffix="s" /><span>of you is a cloned voice</span></li>
                <li><Counter to={11} /><span>stages, start to published</span></li>
                <li><Counter to={0} /><span>cards, anywhere</span></li>
              </ul>
            </Reveal>
          </div>
        </section>

        <Ticker />

        <div id="how" />
        <span id="sec-how" />
        <Rail />

        <div id="studio" />
        <span id="sec-studio" />
        <Places theme={theme} />

        <Deliverables />

        <section className="truths-section" id="sec-truths">
          <div className="wrap">
            <Reveal><h2>What it will not do to you.</h2></Reveal>
            <div className="truths">
              {TRUTHS.map(([title, body], i) => (
                <Reveal key={title} delay={i * 70}>
                  <article className="truth">
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </article>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="end-section" id="sec-end">
          <div className="wrap">
            <Reveal>
              <h2>The studio is through here.</h2>
              <div className="hero-actions">
                <a className="btn primary" href="/room/">Open the studio</a>
                <a className="btn ghost" href="/room/?at=booth">Record a voice first</a>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <footer>
        <div className="wrap">Santa Studio</div>
      </footer>
    </>
  );
}
