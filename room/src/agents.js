/* The roster. One character per pipeline stage, in pipeline order, so the
   room is literally a picture of manager.py's STATE_SEQUENCE.

   `state` is the backend state name this desk represents; the Manager has no
   state of its own because it *is* the state machine. `screen` picks which
   in-laptop UI gets drawn for this role (see studio/screenDraw.js). */

export const AGENTS = [
  { id: "manager",    name: "Manager",     state: null,                screen: "board",    color: "#FF6B35" },
  { id: "topic",      name: "Topic",       state: "TOPIC_SELECTION",   screen: "notes",    color: "#FFD23F" },
  { id: "reference",  name: "Reference",   state: "REFERENCE_ANALYSIS",screen: "browser",  color: "#7CE38B" },
  { id: "research",   name: "Research",    state: "RESEARCHING",       screen: "browser",  color: "#00E5FF" },
  { id: "factcheck",  name: "Fact-check",  state: "FACT_CHECKING",     screen: "notes",    color: "#FF5C7A" },
  { id: "script",     name: "Scriptwriter",state: "SCRIPTING",         screen: "doc",      color: "#FFB86B" },
  { id: "voice",      name: "Voice",       state: "VOICE_GENERATION",  screen: "waveform", color: "#9D6BFF" },
  { id: "visual",     name: "Visual",      state: "VISUAL_SELECTION",  screen: "gallery",  color: "#4DD0E1" },
  { id: "assembler",  name: "Assembler",   state: "VIDEO_ASSEMBLY",    screen: "timeline", color: "#F06292" },
  { id: "shorts",     name: "Shorts",      state: "SHORTS_EXTRACTION", screen: "shorts",   color: "#B8FF6B" },
  { id: "thumbnail",  name: "Thumbnail",   state: "THUMBNAIL",         screen: "gallery",  color: "#FFA0D2" },
  { id: "publish",    name: "Publish",     state: "YOUTUBE_PUBLISH",   screen: "terminal", color: "#FF6B35" },
];

export const AGENT_BY_STATE = Object.fromEntries(
  AGENTS.filter((a) => a.state).map((a) => [a.state, a])
);
