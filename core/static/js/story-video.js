/* "See story": plays the ReadyWise promo video full-screen in a dialog. Works on every screen size; Esc, the close button or a click outside ends it. */
(() => {
  let root, vid, opener;
  function build(src, poster) {
    root = document.createElement("div"); root.className = "sv"; root.setAttribute("role", "dialog"); root.setAttribute("aria-modal", "true"); root.setAttribute("aria-label", "ReadyWise story"); root.hidden = true;
    root.innerHTML = '<button type="button" class="sv-x" aria-label="Close video">&times;</button><div class="sv-box"><video controls playsinline preload="none" poster="' + poster + '"><source src="' + src + '" type="video/mp4"></video></div>';
    document.body.appendChild(root); vid = root.querySelector("video");
    root.querySelector(".sv-x").onclick = close;
    root.addEventListener("click", e => { if (e.target === root) close(); });
  }
  function open(btn) {
    opener = btn; if (!root) build(btn.dataset.src, btn.dataset.poster);
    root.hidden = false; document.body.style.overflow = "hidden"; requestAnimationFrame(() => root.classList.add("open"));
    vid.currentTime = 0; const p = vid.play(); if (p && p.catch) p.catch(() => {}); root.querySelector(".sv-x").focus();
  }
  function close() {
    if (!root || root.hidden) return; vid.pause(); root.classList.remove("open"); document.body.style.overflow = "";
    setTimeout(() => { root.hidden = true; }, 200); if (opener) opener.focus();
  }
  document.addEventListener("click", e => { const b = e.target.closest("[data-story-open]"); if (b) { e.preventDefault(); open(b); } });
  document.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
})();
