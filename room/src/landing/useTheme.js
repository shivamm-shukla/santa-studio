import { useCallback, useEffect, useState } from "react";

/* The light switch, shared with the room and with the rest of the app.

   It reads the same localStorage key everything else does, so turning the
   lights on here and walking into the studio does not put you back in the
   dark. The landing did not have one at all, which made it the one page in
   the product where the switch was missing. */

const KEY = "santa-studio-theme";

function stored() {
  try {
    const saved = localStorage.getItem(KEY);
    return saved === "light" || saved === "dark" ? saved : "dark";
  } catch (e) {
    return "dark";
  }
}

export default function useTheme() {
  const [theme, setTheme] = useState(stored);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) { /* private window - it still switches, it just forgets */ }
  }, [theme]);

  const toggle = useCallback(
    () => setTheme((t) => (t === "light" ? "dark" : "light")),
    []
  );

  return { theme, toggle };
}
