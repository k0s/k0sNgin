// Audio player for k0sNgin audio directories (templates/_player.html).
// Progressive enhancement: without this script the page is a list of links.
// An external file because the site CSP (script-src 'self') blocks inline
// scripts.
(() => {
  const root = document.querySelector(".player");
  if (!root) return;
  const audio = root.querySelector(".player-audio");
  const controls = root.querySelector(".player-controls");
  const items = [...root.querySelectorAll("ol.playlist li[data-src]")];
  const gapMs = Math.max(0, parseFloat(root.dataset.gap) || 0) * 1000;
  let i = -1, timer = null;

  function clear() {
    items.forEach(li => li.classList.remove("now"));
  }

  function play(k) {
    clearTimeout(timer);
    clear();
    if (k < 0 || k >= items.length) { i = -1; return; }
    i = k;
    items[i].classList.add("now");
    items[i].scrollIntoView({ block: "nearest", behavior: "smooth" });
    audio.src = items[i].dataset.src;
    audio.play();
  }

  audio.addEventListener("ended", () => {
    if (i >= 0) timer = setTimeout(() => play(i + 1), gapMs);
  });
  items.forEach((li, k) => li.addEventListener("click", event => {
    event.preventDefault();  // play here rather than following the link
    play(k);
  }));
  const on = (action, handler) =>
    controls.querySelector(`[data-action=${action}]`).addEventListener("click", handler);
  on("play", () => play(0));
  on("next", () => play(i < 0 ? 0 : i + 1));
  on("prev", () => play(Math.max(0, i - 1)));
  on("stop", () => { clearTimeout(timer); audio.pause(); i = -1; clear(); });

  controls.hidden = false;
  audio.hidden = false;
})();
