// Layout check: lists text or elements that spill out of their box on the current screen.
// Run it in the app's dev tools console (or a preview eval) at each window size worth checking
// (the window's minimum 768x560, its default 1100x760, and a large one), with the chat panel at
// its narrowest, and in every state a flow passes through (empty, thinking, questions, options,
// plan, building, failed), not only the empty screen. Empty array = clean. It cannot judge copy
// or density: take a screenshot and read it against docs/development/ui-bridge-baseline.md too.
// ponytail: a console script, not a CI test (jsdom has no layout); move it into a Playwright
// run if one is ever added.
(() => {
  const out = [];
  const fonts = new Set();
  const texts = [];
  const ctx = document.createElement("canvas").getContext("2d");
  const name = (e) =>
    e.tagName.toLowerCase() +
    (typeof e.className === "string" && e.className.trim() ? "." + e.className.trim().split(/\s+/).join(".") : "") +
    (e.getAttribute("aria-label") ? `[${e.getAttribute("aria-label")}]` : "");
  // Drawn past their box on purpose (the panda's ears) or screen-reader only.
  const skip = (e) => e.closest(".sr-only, .zazoo, [data-overflow-ok]");
  for (const e of document.querySelectorAll("body *")) {
    const cs = getComputedStyle(e);
    const r = e.getBoundingClientRect();
    if (cs.display === "none" || cs.visibility === "hidden" || !r.width || skip(e)) continue;
    const text = (e.textContent || "").trim().slice(0, 50);
    const scrolls = cs.overflowX === "auto" || cs.overflowX === "scroll";
    if (e.scrollWidth > e.clientWidth + 1 && e.clientWidth > 0 && !scrolls && !["INPUT", "TEXTAREA", "SELECT"].includes(e.tagName) && e.children.length === 0)
      out.push(`${cs.textOverflow === "ellipsis" ? "CUT" : "SPILL"} ${name(e)} "${text}"`);
    // Placeholders: an input's must fit on its line; a textarea's must fit without wrapping too
    // (a wrapped placeholder in a one-row composer is cut off at the bottom).
    if ((e.tagName === "INPUT" || e.tagName === "TEXTAREA") && e.placeholder && !e.value) {
      ctx.font = cs.font;
      const room = e.clientWidth - parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight);
      if (ctx.measureText(e.placeholder).width > room + 1) out.push(`PLACEHOLDER ${name(e)} "${e.placeholder}"`);
    }
    fonts.add(cs.fontSize);
    if (r.right > window.innerWidth + 1 && cs.position !== "fixed") out.push(`OFFSCREEN ${name(e)} "${text}"`);
    // Text drawn past whatever clips it (catches centred text that spills to the left too).
    if (e.children.length === 0 && text && e.tagName !== "TEXTAREA") {
      const range = document.createRange();
      range.selectNodeContents(e);
      const t = range.getBoundingClientRect();
      for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
        if (getComputedStyle(a).overflowX === "visible") continue;
        const ar = a.getBoundingClientRect();
        if (t.left < ar.left - 1 || t.right > ar.right + 1) out.push(`CLIPPED ${name(e)} "${text}" by ${name(a)}`);
        break;
      }
      // Cut top or bottom: a title that wrapped inside a fixed-height header, a line clamp that
      // ends mid-line. Scroll containers are fine.
      for (let a = e.parentElement; a && a !== document.body; a = a.parentElement) {
        const acs = getComputedStyle(a);
        if (acs.overflowY === "visible" || acs.overflowY === "auto" || acs.overflowY === "scroll") continue;
        const ar = a.getBoundingClientRect();
        if (t.top < ar.top - 1 || t.bottom > ar.bottom + 1) out.push(`CUT-V ${name(e)} "${text}" by ${name(a)}`);
        break;
      }
      texts.push([e, t]);
    }
    const p = e.parentElement;
    if (p && p !== document.body && cs.position !== "absolute" && cs.position !== "fixed") {
      const pr = p.getBoundingClientRect();
      if (getComputedStyle(p).overflow === "visible" && (r.right > pr.right + 2 || r.left < pr.left - 2)) out.push(`OUTSIDE ${name(e)} in ${name(p)}`);
    }
  }
  // Text covered by another element drawn on top of it (a see-through sticky header over
  // messages, an avatar over a subtitle, a tooltip over content).
  for (const [e, t] of texts) {
    if (t.width < 4 || t.height < 4 || t.bottom < 0 || t.top > window.innerHeight) continue;
    const x = Math.min(t.left + 4, window.innerWidth - 1), y = (t.top + t.bottom) / 2;
    const top = document.elementFromPoint(x, y);
    if (top && top !== e && !e.contains(top) && !top.contains(e) && !skip(top)) out.push(`COVERED ${name(e)} "${(e.textContent || "").trim().slice(0, 40)}" by ${name(top)}`);
  }
  // One type scale: more than five sizes on one screen is drift.
  if (fonts.size > 5) out.push(`FONTS ${fonts.size} sizes: ${[...fonts].sort((a, b) => parseFloat(a) - parseFloat(b)).join(" ")}`);
  return [...new Set(out)];
})();
