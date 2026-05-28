(function () {
  const STORAGE_KEY = 'rpgSurveyAccessibility';

  const defaultSettings = {
    fontSize: 'normal',
    theme: 'default',
    underlineLinks: false,
    reduceMotion: false
  };

  function readSettings() {
    try {
      return { ...defaultSettings, ...JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') };
    } catch (_) {
      return { ...defaultSettings };
    }
  }

  function saveSettings(settings) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }

  function applySettings(settings) {
    const root = document.documentElement;

    root.setAttribute('data-font-size', settings.fontSize);
    root.setAttribute('data-theme', settings.theme);
    root.toggleAttribute('data-underline-links', Boolean(settings.underlineLinks));
    root.toggleAttribute('data-reduce-motion', Boolean(settings.reduceMotion));

    document.querySelectorAll('[data-font-size]').forEach(btn => {
      btn.setAttribute('aria-pressed', String(btn.dataset.fontSize === settings.fontSize));
    });

    document.querySelectorAll('[data-theme-choice]').forEach(btn => {
      btn.setAttribute('aria-pressed', String(btn.dataset.themeChoice === settings.theme));
    });

    const linkToggle = document.querySelector('[data-toggle-links]');
    if (linkToggle) linkToggle.checked = Boolean(settings.underlineLinks);

    const motionToggle = document.querySelector('[data-toggle-motion]');
    if (motionToggle) motionToggle.checked = Boolean(settings.reduceMotion);
  }

  function openPanel() {
    const toggle = document.getElementById('accessibilityToggle');
    const panel = document.getElementById('accessibilityPanel');

    if (!toggle || !panel) return;

    panel.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');

    const firstButton = panel.querySelector('button, input, select, textarea, a[href]');
    if (firstButton) firstButton.focus();
  }

  function closePanel() {
    const toggle = document.getElementById('accessibilityToggle');
    const panel = document.getElementById('accessibilityPanel');

    if (!toggle || !panel) return;

    panel.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.focus();
  }

  document.addEventListener('DOMContentLoaded', function () {
    let settings = readSettings();
    applySettings(settings);

    const toggle = document.getElementById('accessibilityToggle');
    const panel = document.getElementById('accessibilityPanel');

    if (toggle && panel) {
      toggle.addEventListener('click', function () {
        if (panel.hidden) openPanel();
        else closePanel();
      });
    }

    document.querySelectorAll('[data-accessibility-close]').forEach(btn => {
      btn.addEventListener('click', closePanel);
    });

    document.querySelectorAll('[data-font-size]').forEach(btn => {
      btn.addEventListener('click', function () {
        settings.fontSize = btn.dataset.fontSize || 'normal';
        saveSettings(settings);
        applySettings(settings);
      });
    });

    document.querySelectorAll('[data-theme-choice]').forEach(btn => {
      btn.addEventListener('click', function () {
        settings.theme = btn.dataset.themeChoice || 'default';
        saveSettings(settings);
        applySettings(settings);
      });
    });

    const linkToggle = document.querySelector('[data-toggle-links]');
    if (linkToggle) {
      linkToggle.addEventListener('change', function () {
        settings.underlineLinks = linkToggle.checked;
        saveSettings(settings);
        applySettings(settings);
      });
    }

    const motionToggle = document.querySelector('[data-toggle-motion]');
    if (motionToggle) {
      motionToggle.addEventListener('change', function () {
        settings.reduceMotion = motionToggle.checked;
        saveSettings(settings);
        applySettings(settings);
      });
    }

    document.querySelectorAll('[data-accessibility-reset]').forEach(btn => {
      btn.addEventListener('click', function () {
        settings = { ...defaultSettings };
        saveSettings(settings);
        applySettings(settings);
      });
    });

    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && panel && !panel.hidden) {
        closePanel();
      }
    });

    document.addEventListener('click', function (event) {
      const widget = document.querySelector('.accessibility-widget');
      if (!widget || !panel || panel.hidden) return;

      if (!widget.contains(event.target)) {
        panel.hidden = true;
        toggle?.setAttribute('aria-expanded', 'false');
      }
    });
  });
})();
