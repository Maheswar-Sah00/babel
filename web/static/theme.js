// Light or dark theme. A classic script in <head>, so it runs before the page paints (no flash of the wrong theme).
// It always sets <html data-theme="light|dark">: the saved choice, else the system setting (followed live). Every
// stylesheet keys its dark colours on :root[data-theme="dark"] inside @media screen, so printing stays light.
// window.babelTheme: get(), set("light" | "dark"), toggle(x, y); each change fires "babel:theme" on document.
(function () {
  var KEY = "babel-theme";
  var REVEAL_MS = 460;
  var media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;

  function saved() {
    try {
      var value = localStorage.getItem(KEY);
      return value === "light" || value === "dark" ? value : null;
    } catch (e) {
      return null;
    }
  }

  function system() {
    return media && media.matches ? "dark" : "light";
  }

  function apply(theme) {
    if (document.documentElement.dataset.theme === theme) return;
    document.documentElement.dataset.theme = theme;
    document.dispatchEvent(new CustomEvent("babel:theme", { detail: { theme: theme } }));
  }

  function set(theme) {
    try {
      localStorage.setItem(KEY, theme);
    } catch (e) { /* private window: the choice lasts until the page closes */ }
    apply(theme);
  }

  // The new theme grows over the old one in a circle from (x, y) until it covers the window (a view transition;
  // app.css turns off the default cross-fade). Without view transitions, without a point, or when the reader asks
  // for reduced motion, it switches at once.
  function reveal(theme, x, y) {
    var still = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!document.startViewTransition || still || typeof x !== "number" || typeof y !== "number") return set(theme);
    var radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    var at = " at " + Math.round(x) + "px " + Math.round(y) + "px)";
    var transition = document.startViewTransition(function () { set(theme); });
    transition.ready.then(function () {
      document.documentElement.animate(
        { clipPath: ["circle(0px" + at, "circle(" + Math.ceil(radius) + "px" + at] },
        { duration: REVEAL_MS, easing: "cubic-bezier(.4, 0, .2, 1)", pseudoElement: "::view-transition-new(root)" });
    }).catch(function () { /* skipped (e.g. the page was hidden): the theme is already set */ });
  }

  window.babelTheme = {
    get: function () { return document.documentElement.dataset.theme === "dark" ? "dark" : "light"; },
    set: set,
    toggle: function (x, y) { reveal(window.babelTheme.get() === "dark" ? "light" : "dark", x, y); },
  };
  apply(saved() || system());
  if (media && media.addEventListener) {
    media.addEventListener("change", function () { if (!saved()) apply(system()); });
  }
})();
