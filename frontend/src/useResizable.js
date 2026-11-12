import { useCallback, useState } from "react";

// A panel width the user drags (or nudges with the arrow keys), remembered per browser.
// `sign` is +1 when dragging right grows the panel (a left panel), -1 for a right panel.
export function useResizable(storageKey, { initial, min, max, sign = 1 }) {
  const [width, setWidth] = useState(() => {
    try {
      const v = Number(localStorage.getItem(storageKey));
      return v ? v : null;
    } catch {
      return null;
    }
  });

  const clamp = useCallback((w) => Math.round(Math.min(Math.max(w, min), max())), [min, max]);

  const save = useCallback(
    (w) => {
      setWidth(w);
      try {
        if (w == null) localStorage.removeItem(storageKey);
        else localStorage.setItem(storageKey, String(w));
      } catch {
        /* private window: not remembered */
      }
    },
    [storageKey]
  );

  const handleProps = {
    role: "separator",
    "aria-orientation": "vertical",
    tabIndex: 0,
    title: "Drag to resize · double-click to reset",
    onPointerDown: (e) => {
      const panel = sign > 0 ? e.currentTarget.previousElementSibling : e.currentTarget.nextElementSibling;
      const startX = e.clientX;
      const startW = panel.getBoundingClientRect().width;
      e.currentTarget.setPointerCapture(e.pointerId);
      document.body.classList.add("resizing");
      const move = (ev) => save(clamp(startW + sign * (ev.clientX - startX)));
      const up = () => {
        document.body.classList.remove("resizing");
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    },
    onDoubleClick: () => save(null),
    onKeyDown: (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      const panel = sign > 0 ? e.currentTarget.previousElementSibling : e.currentTarget.nextElementSibling;
      const step = (e.key === "ArrowRight" ? 24 : -24) * sign;
      save(clamp(panel.getBoundingClientRect().width + step));
    },
  };

  return { width: width ?? initial, handleProps };
}
