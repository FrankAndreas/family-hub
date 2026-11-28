// family-hub-theme: the remembered theme on <html> before the page renders (load it first, as a same-origin file:
// the apps' Content-Security-Policy allows no inline scripts). Kept in step with index.js.
(function () {
  var themes = ['aurora'];
  var theme = 'aurora';
  try {
    var saved = localStorage.getItem('family-theme');
    if (themes.indexOf(saved) >= 0) theme = saved;
  } catch (e) {
    // Private mode or blocked storage
  }
  document.documentElement.setAttribute('data-theme', theme);
})();
