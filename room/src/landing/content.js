/* What the front door says.

   Kept as data rather than as markup so the page can lay the same facts out
   three different ways - a card, a rail, a list - without any of them going
   out of step with the others. Every number here is one the system actually
   produces; nothing is aspirational. */

export const STEPS = [
  {
    n: "01",
    title: "It finds out",
    body: "Three indexes, none of which needs an account: Wikipedia for the shape of a subject, OpenAlex for the academic record with DOIs, GDELT for what was written at the time.",
    note: "The sources in the description are the ones it read. Not ones a model wrote.",
  },
  {
    n: "02",
    title: "It checks itself",
    body: "Every claim carries the source that made it. Where two sources give different figures for the same thing, the video says they disagree.",
    note: "Rounding is not a dispute. Neither is the same number in another unit.",
  },
  {
    n: "03",
    title: "It writes",
    body: "Structure learned from channels you point it at — hook shape, section order, how long a point is held. Substance from the research.",
    note: "Their craft. Never their content.",
  },
  {
    n: "04",
    title: "It speaks",
    body: "Cloned from about eight seconds of you, recorded at the microphone in the booth. Captions are timed against the audio that ships.",
    note: "Which is what Hinglish needed.",
  },
  {
    n: "05",
    title: "It looks",
    body: "Stock that is actually of the subject — checked, because libraries answer every query with something. Where none exists, stills made to look photographed.",
    note: "Documents and charts are refused, not invented.",
  },
  {
    n: "06",
    title: "It cuts",
    body: "Shots that move like a camera, charts built from the real figures, one grade over every source so the edit reads as filmed rather than assembled.",
    note: "Then captions, then the shorts, then the thumbnails.",
  },
];

export const PLACES = [
  {
    id: "floor",
    at: "",
    title: "The studio floor",
    body: "Twelve desks, one per stage. Work lands on them in order and you can read over anyone's shoulder while they do it.",
  },
  {
    id: "board",
    at: "?at=board",
    title: "The board",
    body: "Where a video is commissioned. Niche, topic, the channels to learn from, whose voice reads it. Hand it over and the studio starts.",
  },
  {
    id: "booth",
    at: "?at=booth",
    title: "The booth",
    body: "A room off the floor with foam on the walls and a microphone in it. Press record and talk — the mic answers your voice while you do.",
  },
  {
    id: "rack",
    at: "?at=rack",
    title: "The rack",
    body: "Every voice you have recorded, and the moods you can give one. Both takes play side by side, because that is the only way to judge a filter.",
  },
];

export const TRUTHS = [
  ["Free tiers, on purpose", "Four LLM providers behind one router, images on Cloudflare's free allowance, footage from Pexels, Pixabay and Commons. No card, anywhere."],
  ["It survives being interrupted", "State is written after every stage. A killed run resumes where it stopped. A run that hits a daily limit parks and says when to come back."],
  ["Licensed or generated", "Every frame is commercially usable, and the default voice model is MIT — so a monetised channel is not a licensing problem."],
  ["Sources as a deliverable", "A sources document beside the master, and clickable links in the description. Claims that failed the check are listed too, separately."],
];

/* Each section owns a hue. The page background travels between them as you
   scroll, so moving down it feels like moving through somewhere rather than
   past a wall of the same colour. */
export const SECTIONS = [
  { id: "sec-hero", tint: "255, 107, 53" },
  { id: "sec-how", tint: "0, 229, 255" },
  { id: "sec-studio", tint: "255, 107, 53" },
  { id: "sec-out", tint: "120, 220, 160" },
  { id: "sec-truths", tint: "160, 140, 255" },
  { id: "sec-end", tint: "255, 107, 53" },
];

/* What a finished run leaves on disk. Concrete, because "a video" is what
   every tool on earth claims to produce. */
export const DELIVERABLES = [
  ["The video", "1080p, narrated, captioned, mixed to −14 LUFS."],
  ["The shorts", "Vertical cuts sized for Shorts, Reels and Twitter."],
  ["The thumbnails", "Several variants with hook text, to choose from."],
  ["sources.md", "Every source, the claims drawn from it, and separately the claims that were flagged and kept out."],
  ["The timeline", "The whole edit as a file you can adjust and re-render without spending an API call."],
];

/* Runs along the page like a ticker. Short, concrete, slightly odd - the
   things that are true of this and of almost nothing else. */
export const TICKER = [
  "sources you can click",
  "your own voice",
  "no card, anywhere",
  "refuses to invent a document",
  "parks when the quota runs out",
  "one grade over every source",
  "depth-driven motion on stills",
  "charts from the real figures",
];
