import { useEffect, useRef, useState } from "react";
import Reveal from "./Reveal.jsx";
import useTheme from "./useTheme.js";
import { NOT_YET, PLACES, STEPS, TRUTHS } from "./content.js";

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

            const style = {
              transform: [
                `translateX(${offset * 46}%)`,
                `translateZ(${-away * 260}px)`,
                `rotateY(${offset * -34}deg)`,
                `scale(${1 - Math.min(away, 2) * 0.06})`,
              ].join(" "),
              opacity: Math.max(0, 1 - away * 0.5),
              filter: `blur(${Math.min(away * 1.6, 4)}px) brightness(${1 - Math.min(away, 2) * 0.28})`,
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
  const place = PLACES.find((p) => p.id === open) ?? PLACES[0];

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
                onClick={() => setOpen(p.id)}
              >
                {p.title}
              </button>
            ))}
          </div>
        </Reveal>

        <Reveal delay={140} className="shot-frame">
          {/* Keyed on both, so switching either the place or the lights
              re-runs the fade rather than swapping the picture underneath. */}
          <img
            key={`${place.id}-${theme}`}
            className="shot"
            src={`/room/shots/${place.id}-${theme}.png`}
            alt={place.title}
            loading="lazy"
          />
          <div className="shot-caption">
            <b>{place.title}</b>
            <span>{place.body}</span>
            <a className="btn ghost" href={`/room/${place.at}`}>Walk in →</a>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

export default function Landing() {
  const { theme, toggle } = useTheme();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <>
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
        <section className="hero">
          <div className="hero-glow" aria-hidden="true" />
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
                <li><b>3</b><span>research indexes, no keys</span></li>
                <li><b>8s</b><span>of you is a cloned voice</span></li>
                <li><b>0</b><span>cards, anywhere</span></li>
              </ul>
            </Reveal>
          </div>
        </section>

        <div id="how" />
        <Rail />

        <div id="studio" />
        <Places theme={theme} />

        <section className="truths-section">
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

        <section className="honest-section">
          <div className="wrap">
            <Reveal>
              <div className="eyebrow">and the honest part</div>
              <h2>What does not work yet.</h2>
            </Reveal>
            <ul className="honest">
              {NOT_YET.map((line, i) => (
                <Reveal as="li" key={line} delay={i * 70}>{line}</Reveal>
              ))}
            </ul>
          </div>
        </section>

        <section className="end-section">
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
