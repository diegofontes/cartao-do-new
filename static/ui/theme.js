(function(){
  const root = document.documentElement;
  const stored = localStorage.getItem('theme');
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  if(!stored){ root.setAttribute('data-theme', prefersDark ? 'dark' : 'light'); }
  else { root.setAttribute('data-theme', stored); }
  window.toggleTheme = () => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    applyLogo();
  };

  // Global HTMX CSRF header if csrftoken cookie is present (Django-friendly)
  document.addEventListener('htmx:configRequest', function(e){
    const m = document.cookie.match('(^|;)\\s*csrftoken\\s*=\\s*([^;]+)');
    const token = m ? m.pop() : '';
    if (token) { e.detail.headers['X-CSRFToken'] = token; }
  });

  // Sidebar collapse state (persisted)
  function applySidebar(collapsed){
    const layout = document.querySelector('.layout');
    const sidebar = document.querySelector('.sidebar');
    if (!layout || !sidebar) return;
    if (collapsed){
      layout.setAttribute('data-collapsed','true');
      sidebar.setAttribute('data-collapsed','true');
    } else {
      layout.removeAttribute('data-collapsed');
      sidebar.removeAttribute('data-collapsed');
    }
  }
  const sbStored = localStorage.getItem('sidebarCollapsed') === '1';
  applySidebar(sbStored);
  function toggleSidebar(){
    const next = !(localStorage.getItem('sidebarCollapsed') === '1');
    localStorage.setItem('sidebarCollapsed', next ? '1' : '0');
    applySidebar(next);
  }
  window.toggleSidebar = toggleSidebar;
  // Drawer controls (mobile sidebar)
  function openDrawer(){
    document.body.setAttribute('data-drawer','open');
    const sb = document.querySelector('.sidebar');
    if (sb){ sb.setAttribute('aria-hidden','false'); const first = sb.querySelector('nav a'); if(first) first.focus(); }
  
    document.querySelector('.layout').removeAttribute('data-collapsed');
    document.querySelector('.sidebar').removeAttribute('data-collapsed');
      
  }
  function closeDrawer(){
    document.body.removeAttribute('data-drawer');
    const sb = document.querySelector('.sidebar');
    if (sb){ sb.setAttribute('aria-hidden','true'); }
  }
  function toggleDrawer(){
    if (document.body.getAttribute('data-drawer') === 'open') closeDrawer(); else openDrawer();
  }
  window.toggleDrawer = toggleDrawer;

  document.addEventListener('click', function(e){
    const btn = e.target.closest('[data-toggle-sidebar]');
    if (btn){ e.preventDefault(); toggleSidebar(); }

    const themeBtn = e.target.closest('[data-toggle-theme], [aria-label="Alternar tema"]');
    if (themeBtn){ e.preventDefault(); try{ window.toggleTheme(); } catch(_){} }

    const openBtn = e.target.closest('[data-open-drawer]');
    if (openBtn){ e.preventDefault(); toggleDrawer(); }

    const closeBtn = e.target.closest('[data-close-drawer]');
    if (closeBtn){ e.preventDefault(); closeDrawer(); }

    if (e.target.classList.contains('drawer-backdrop')){ e.preventDefault(); closeDrawer(); }

    // Close drawer when a sidebar link is chosen (common mobile UX)
    const sideLink = e.target.closest('.sidebar nav a');
    if (sideLink && document.body.getAttribute('data-drawer') === 'open'){ closeDrawer(); }

    // Trigger hidden file input via data-open-file selector
    const openFileBtn = e.target.closest('[data-open-file]');
    if (openFileBtn){
      e.preventDefault();
      try{
        // Allow optional selector via data-open-file; if empty, find nearest input[type=file]
        let sel = openFileBtn.getAttribute('data-open-file');
        let inp = null;
        if (sel){
          inp = document.querySelector(sel);
        } else {
          const scope = openFileBtn.closest('#dropzone') || openFileBtn.closest('form') || document;
          inp = scope.querySelector('input[type="file"]');
        }
        if (inp){ inp.click(); }
      }catch(_){/* noop */}
    }
  });

  // Allow closing the drawer with Escape
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape' && document.body.getAttribute('data-drawer') === 'open'){ closeDrawer(); }
  });

  // Swap logo image based on current theme
  function applyLogo(){
    const isDark = root.getAttribute('data-theme') === 'dark';
    const els = document.querySelectorAll('[data-logo-light], [data-logo-dark], #logo');
    els.forEach(function(el){
      const light = el.getAttribute('data-logo-light') || el.getAttribute('data-logo-dark');
      const dark = el.getAttribute('data-logo-dark') || el.getAttribute('data-logo-light');
      const next = isDark ? (dark || el.getAttribute('src')) : (light || el.getAttribute('src'));
      if (next && el.getAttribute('src') !== next) {
        el.classList.add('logo-swap');
        el.setAttribute('src', next);
        window.setTimeout(function(){ el.classList.remove('logo-swap'); }, 180);
      }
    });
  }
  document.addEventListener('DOMContentLoaded', applyLogo);
  // Observe data-theme attribute changes to keep logo in sync
  try{
    const mo = new MutationObserver(function(m){
      for (const rec of m){
        if (rec.attributeName === 'data-theme') { applyLogo(); }
      }
    });
    mo.observe(document.documentElement, { attributes: true });
  }catch(_){/* noop */}
  // Also update if system theme changes and user hasn't set an explicit preference
  try{
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', function(){
      const storedTheme = localStorage.getItem('theme');
      if(!storedTheme){
        root.setAttribute('data-theme', mq.matches ? 'dark' : 'light');
        applyLogo();
      }
    });
  }catch(_){/* noop */}
})();
