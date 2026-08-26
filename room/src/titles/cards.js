/* Every word in the demo film.

   There is no narration, so this is the script. That changes what the type is
   for: it is not decoration over a shot, it is the only thing explaining what
   the shot is of. So most of these are lower thirds rather than full cards -
   they sit under the picture instead of covering it, because the picture is
   the product working and hiding it to describe it would be perverse.

   Kinds:
     wordmark   the opening and the end - full frame, centred
     chapter    a numbered step. Big number, short label, one line under it
     lower      a lower third: a heading and a line, out of the way
     credit     small print, bottom, for attribution

   The `seconds` on each is how long it is on screen, and the same number
   appears in reel/demo_edit.py. If one moves, both move. */

export const CARDS = [
  // --- act 1: cold open -------------------------------------------------
  { id: "open", kind: "wordmark", top: "santa", big: "STUDIO", rule: true, seconds: 3.6 },
  {
    id: "promise",
    kind: "lower",
    head: "One topic in. One finished video out.",
    line: "Researched, fact-checked, narrated in your voice, cut and captioned.",
    seconds: 3.4,
  },

  // --- act 2: the site --------------------------------------------------
  { id: "site", kind: "lower", head: "It starts at a web page.", line: "Nothing to install.", seconds: 2.8 },

  // --- act 3: the studio ------------------------------------------------
  {
    id: "place",
    kind: "lower",
    head: "It is a place, not a dashboard.",
    line: "Every stage of the pipeline has a desk, and you can watch it work.",
    seconds: 3.8,
  },

  // --- act 4: commission ------------------------------------------------
  { id: "c1", kind: "chapter", n: "01", label: "Commission", line: "A niche, a topic, and any videos to learn pacing from.", seconds: 3.4 },
  { id: "c1b", kind: "lower", head: "Reference videos are read, not copied.", line: "Structure and pacing only.", seconds: 2.8 },

  // --- act 5: the work --------------------------------------------------
  { id: "c2", kind: "chapter", n: "02", label: "It researches", line: "Wikipedia, OpenAlex and GDELT. No API keys.", seconds: 3.4 },
  {
    id: "c3",
    kind: "chapter",
    n: "03",
    label: "It checks itself",
    line: "Every claim carries the source that made it. Where two sources disagree, the video says so.",
    seconds: 4.0,
  },
  { id: "c3b", kind: "lower", head: "Charts are built from the figures it found.", line: "Not generated — generating one invents numbers.", seconds: 3.0 },

  // --- act 6: the voice -------------------------------------------------
  { id: "c4", kind: "chapter", n: "04", label: "Your voice", line: "About eight seconds of ordinary speech is enough.", seconds: 3.4 },
  { id: "sample", kind: "lower", head: "This is the sample.", line: "A Hindi recording, eighty seconds of it.", seconds: 3.0 },
  { id: "clone", kind: "lower", head: "This is the script, read in that voice.", line: "Same speaker. Words it has never said.", seconds: 3.4 },
  {
    id: "credit",
    kind: "credit",
    line: "Voice sample: “Hindi Dengue Details”, Wikimedia Commons, CC BY-SA 3.0",
    seconds: 3.0,
  },

  // --- act 7: the film --------------------------------------------------
  { id: "c5", kind: "chapter", n: "05", label: "The film", line: "Narrated, captioned, graded, and sourced.", seconds: 3.4 },
  { id: "deliver", kind: "lower", head: "Five things land on disk.", line: "The master, the captions, the thumbnail, the sources, and the timeline it was cut from.", seconds: 3.8 },

  // --- act 8: clips -----------------------------------------------------
  { id: "c6", kind: "chapter", n: "06", label: "Shorts", line: "It watches the finished video and keeps the moments that hold on their own.", seconds: 4.0 },
  { id: "clips2", kind: "lower", head: "Ranked, with reasons.", line: "Then cut to the size each platform wants.", seconds: 3.0 },
  { id: "clips3", kind: "lower", head: "Publish now, or schedule it.", line: "Straight to YouTube from the same screen.", seconds: 3.2 },

  // --- act 9: close -----------------------------------------------------
  { id: "end", kind: "wordmark", top: "santa", big: "STUDIO", note: "give it a topic", seconds: 4.2 },
];

export const CARD_INDEX = Object.fromEntries(CARDS.map((c, i) => [c.id, i]));
