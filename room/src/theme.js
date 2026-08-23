/* Shared palette. The 3D room's own materials are physical (wood, fabric,
   painted concrete) and live with the meshes; these are the accent colours
   used by anything that reads as a *screen* or as UI chrome. */

export const ACCENT = "#FF6B35";   // active / needs-attention
export const DATA = "#00E5FF";     // informational / streaming data
export const WARN = "#FFD23F";

export const CHROME = {
  dark: {
    bg: "#0A0A0F",
    panel: "rgba(14,14,20,0.92)",
    text: "#F5F3EF",
    dim: "rgba(245,243,239,0.6)",
    border: "rgba(255,255,255,0.12)",
  },
  light: {
    bg: "#F7F5F0",
    panel: "rgba(255,255,255,0.94)",
    text: "#15151C",
    dim: "rgba(21,21,28,0.6)",
    border: "rgba(0,0,0,0.12)",
  },
};
