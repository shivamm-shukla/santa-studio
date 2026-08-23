/* Placeholder content for the simulation. Every line here is a stand-in for
   something the real agents already produce — research source URLs, the
   script agent's in-progress scenes, the assembler's timeline — and gets
   replaced wholesale when the room is wired to the backend. */

export const TASK_EMAILS = {
  topic: {
    from: "Manager",
    subject: "New task — pick this week's topic",
    preview:
      "Niche is Indian history. Check what the channel has already covered and come back with one topic, not five.",
  },
  reference: {
    from: "Manager",
    subject: "New task — reference analysis",
    preview:
      "Pull the three best-performing videos on this topic and tell me what their first 30 seconds do.",
  },
  research: {
    from: "Manager",
    subject: "New task — research brief",
    preview:
      "Chronology, numbers, and a source for every claim. Flag anything you can't stand behind.",
  },
  factcheck: {
    from: "Manager",
    subject: "New task — verify the brief",
    preview:
      "Second pass on Research's claims. Anything you can't confirm from two independent sources, mark disputed.",
  },
  script: {
    from: "Manager",
    subject: "New task — write the narration",
    preview:
      "Brief is verified and attached. Nine minutes, cold open on the strongest fact, no throat-clearing.",
  },
  voice: {
    from: "Manager",
    subject: "New task — record the narration",
    preview:
      "Script is locked. Use the saved voice profile, not a fresh clone, and normalise before you hand it over.",
  },
  visual: {
    from: "Manager",
    subject: "New task — shot list and footage",
    preview:
      "One shot per beat, commercially licensed only. If you can't license it, don't use it.",
  },
  assembler: {
    from: "Manager",
    subject: "New task — assemble the cut",
    preview:
      "Timeline first, render second. Captions burned in, music under the narration, not over it.",
  },
  shorts: {
    from: "Manager",
    subject: "New task — pull the shorts",
    preview: "Three vertical cuts from the master. Hook in the first two seconds or it isn't a short.",
  },
  thumbnail: {
    from: "Manager",
    subject: "New task — thumbnails",
    preview: "Four options, readable at 120px wide. Face or object, never both.",
  },
  publish: {
    from: "Manager",
    subject: "New task — publish",
    preview: "Metadata is approved. Upload as unlisted first, then flip it public once it processes.",
  },
};

export const WORK_LINES = {
  topic: [
    "loading channel history — 47 published videos",
    "filtering topics covered in the last 90 days",
    "scoring 12 candidates on search demand vs. saturation",
    "shortlist: Mysorean rockets, Chola navy, Kohinoor",
    "picked: the rockets that beat the East India Company",
  ],
  reference: [
    "fetching top 3 videos for this topic",
    "transcribing first 30s of each",
    "measuring cut rate: 4.2s / 2.8s / 3.9s average shot",
    "all three cold-open on a number, none on a greeting",
    "style profile updated: faster open, no intro card",
  ],
  research: [
    "en.wikipedia.org/wiki/Mysorean_rockets",
    "britannica.com/topic/Anglo-Mysore-Wars",
    "noting: iron-cased rockets, ~2 km range",
    "asi.gov.in — Srirangapatna excavation report",
    "conflict: two sources disagree on range",
    "royalarmouries.org — Congreve's own account",
    "18 claims, 14 with two independent sources",
  ],
  factcheck: [
    "re-checking 18 claims against source list",
    "confirmed: iron casing predates Congreve",
    "confirmed: deployed at Pollilur, 1780",
    "cannot confirm: the 2 km range figure",
    "disputed claim flagged for a human call",
  ],
  script: [
    "In 1780, a British column marched into a field",
    "and the sky above them caught fire.",
    "These were not fireworks. They were iron.",
    "— scene 2 —",
    "The East India Company had never seen a rocket",
    "that could stay together long enough to aim.",
    "Mysore had been building them for twenty years.",
  ],
  voice: [
    "loading voice profile — suraj_v2 (cached)",
    "synthesising chunk 1 of 6",
    "synthesising chunk 4 of 6",
    "loudness normalise → -16 LUFS",
    "forced-aligning captions to waveform",
  ],
  visual: [
    "shot list: 34 beats",
    "pexels — 'fortress ramparts', CC0, 4K",
    "rejected: watermark on candidate 7",
    "archive.org — 1793 engraving, public domain",
    "26 of 34 beats matched",
    "generating Ken Burns paths for stills",
  ],
  assembler: [
    "building timeline from 34 beats",
    "V1: 34 clips placed",
    "A1: narration, A2: bed at -22 dB",
    "captions burned in at 62px",
    "rendering 1080p — 9m 12s",
  ],
  shorts: [
    "scanning master for hook density",
    "candidate 1 — 0:14 'the sky caught fire' (0.94)",
    "candidate 2 — 4:31 'twenty years earlier' (0.83)",
    "reframing to 9:16, tracking the subject",
    "3 shorts cut and captioned",
  ],
  thumbnail: [
    "composing 4 variants",
    "variant A — rocket silhouette, 3 words",
    "variant C — rejected, unreadable at 120px",
    "contrast check passed on A, B, D",
  ],
  publish: [
    "$ santa publish --run 7f3a --unlisted",
    "uploading master.mp4 — 412 MB",
    "upload complete, processing",
    "attaching thumbnail variant A",
    "scheduling public flip in 15 min",
  ],
};

/* The two gates the real state machine already has, plus the disputed-claim
   call that fact-check raises mid-run. */
export const GATES = {
  factcheck: {
    from: "Fact-check",
    stage: "FACT_CHECKING",
    title: "One claim can't be verified",
    body:
      "Research says the Mysorean rockets had a range of about 2 km. Two sources disagree and neither is primary. Cut the number, keep it with a hedge, or hold the run while someone digs?",
    options: [
      { id: "hedge", label: "Keep it, hedged", tone: "primary" },
      { id: "cut", label: "Cut the claim", tone: "ghost" },
    ],
  },
  video: {
    from: "Manager",
    stage: "AWAITING_APPROVAL",
    title: "Is this cut good to go?",
    body:
      "9m 12s, 34 shots, captions burned in, music bed at -22 dB. Approving sends it to thumbnails; sending it back re-runs assembly with your note.",
    options: [
      { id: "approve", label: "Approve the cut", tone: "primary" },
      { id: "regenerate", label: "Re-run assembly", tone: "ghost" },
    ],
  },
  publish: {
    from: "Manager",
    stage: "AWAITING_PUBLISH",
    title: "Ready to publish?",
    body:
      "Thumbnail A, title 'The Rockets That Beat the Empire', 12 tags. Publishing uploads unlisted first and flips it public once YouTube finishes processing.",
    options: [
      { id: "approve", label: "Publish it", tone: "primary" },
      { id: "hold", label: "Hold for now", tone: "ghost" },
    ],
  },
};
