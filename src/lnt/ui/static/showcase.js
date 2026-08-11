(function () {
  'use strict';

  // Theme Toggle
  const toggleThemeBtn = document.getElementById('toggle-theme');
  if (toggleThemeBtn) {
    toggleThemeBtn.addEventListener('click', function () {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
      const newTheme = currentTheme === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('lnt-theme', newTheme);
    });
  }

  // Motion Toggle
  const toggleMotionBtn = document.getElementById('toggle-motion');
  if (toggleMotionBtn) {
    toggleMotionBtn.addEventListener('click', function () {
      const isReduced = document.body.classList.toggle('reduced-motion');
      toggleMotionBtn.textContent = 'Режим уменьшения движения (' + (isReduced ? 'Вкл' : 'Выкл') + ')';
    });
  }

  // Forced Colors Detection
  const forcedColorsIndicator = document.getElementById('forced-colors-indicator');
  if (forcedColorsIndicator) {
    const mediaQuery = window.matchMedia('(forced-colors: active)');
    if (mediaQuery.matches) {
      forcedColorsIndicator.style.display = 'inline-flex';
    }
    mediaQuery.addEventListener('change', function (e) {
      forcedColorsIndicator.style.display = e.matches ? 'inline-flex' : 'none';
    });
  }

  // Initialize Theme from LocalStorage
  const savedTheme = localStorage.getItem('lnt-theme');
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
  }
})();
