/* The film's typography, rendered in the browser and filmed like everything
   else.

   Not drawn in ffmpeg. drawtext can put words on a picture, but the only fonts
   on this machine are DejaVu, and a film whose titles are set in the wrong
   typeface looks like it was made by someone else. These are set in the
   product's own faces, animated the way the product animates, and captured
   with a transparent background so the edit can lay them over the shot they
   belong to.

   ?i=<n> picks a card, ?set=demo picks the long film's script rather than the
   short reel's. window.__titleSeek(k), k from 0 to 1, is the card's whole
   life: in, hold, out. */

import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import { CARDS as DEMO_CARDS } from "./cards.js";
import "./titles.css";

const REEL_CARDS = [
  { kind: "wordmark", top: "santa", big: "STUDIO", rule: true },
  { kind: "line", big: "Give it a topic." },
  { kind: "line", big: "Get the video back.", note: "with its sources attached" },
  { kind: "line", big: "It researches. It checks itself.", note: "three indexes · every claim sourced" },
  { kind: "line", big: "A studio you can walk into." },
  { kind: "line", big: "Commission it at the board." },
  { kind: "line", big: "Read it in your own voice.", note: "eight seconds is a voice" },
  { kind: "line", big: "Cut shorts on the wall." },
  { kind: "end", top: "santa", big: "STUDIO", note: "open the studio" },
];

/* Cards arrive on a beat and leave on one, so the hold is whatever is left
   between. A lower third earns a longer hold because it is being read while
   something else is happening. */
const SHAPE = {
  wordmark: [0.26, 0.84],
  end: [0.26, 0.84],
  line: [0.28, 0.82],
  chapter: [0.22, 0.86],
  lower: [0.18, 0.88],
  credit: [0.20, 0.86],
};

const easeOut = (x) => 1 - Math.pow(1 - x, 3.2);
const easeIn = (x) => x * x * x;

function Card({ card, k }) {
  const [IN, OUT] = SHAPE[card.kind] ?? SHAPE.line;
  const enter = k < IN ? easeOut(k / IN) : 1;
  const leave = k > OUT ? 1 - easeIn((k - OUT) / (1 - OUT)) : 1;
  const on = enter * leave;

  /* Full cards travel further than lower thirds. A lower third that leaps
     around pulls the eye off the thing it is describing, which is the one job
     it has. */
  const travel = card.kind === "lower" || card.kind === "credit" ? 16 : 34;
  const rise = (1 - enter) * travel - (1 - leave) * (travel * 0.6);
  const blur = (1 - on) * (card.kind === "lower" ? 5 : 9);
  const spread = (1 - enter) * 0.16;

  const style = {
    opacity: on,
    transform: `translate3d(0, ${rise}px, 0)`,
    filter: `blur(${blur}px)`,
  };
  if (card.kind === "wordmark" || card.kind === "end") {
    style.letterSpacing = `${0.24 + spread}em`;
  }

  const ruleStyle = { transform: `scaleX(${enter * leave})` };

  if (card.kind === "chapter") {
    return (
      <div className="card chapter" style={style}>
        <div className="n">{card.n}</div>
        <div className="label">{card.label}</div>
        <i className="rule" style={ruleStyle} />
        <div className="note">{card.line}</div>
      </div>
    );
  }

  if (card.kind === "lower") {
    return (
      <div className="card lower" style={style}>
        <i className="tick" style={ruleStyle} />
        <div className="head">{card.head}</div>
        <div className="line">{card.line}</div>
      </div>
    );
  }

  if (card.kind === "credit") {
    return (
      <div className="card credit" style={style}>
        {card.line}
      </div>
    );
  }

  return (
    <div className={`card ${card.kind}`} style={style}>
      {card.top && <div className="top">{card.top}</div>}
      <div className="big">{card.big}</div>
      {card.rule && <i className="rule" style={ruleStyle} />}
      {card.note && <div className="note">{card.note}</div>}
    </div>
  );
}

function Titles() {
  const params = new URLSearchParams(location.search);
  const cards = params.get("set") === "demo" ? DEMO_CARDS : REEL_CARDS;
  const which = Number(params.get("i") || 0);
  const [k, setK] = useState(0);
  const card = cards[Math.max(0, Math.min(cards.length - 1, which))];

  useEffect(() => {
    window.__titleCount = cards.length;
    window.__titleSeek = (value) => setK(value);
    return () => {
      delete window.__titleSeek;
      delete window.__titleCount;
    };
  }, [cards.length]);

  return <Card card={card} k={k} />;
}

createRoot(document.getElementById("root")).render(<Titles />);
