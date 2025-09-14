(function(){
  function activateTab(btn){
    const list = btn.closest('.tablist');
    if(!list) return;
    list.querySelectorAll('.tab').forEach(b=>b.classList.remove('is-active'));
    btn.classList.add('is-active');
    const id = btn.getAttribute('aria-controls');
    const panels = list.parentElement.querySelectorAll('[role="tabpanel"]');
    panels.forEach(p=>p.hidden = (p.id !== id));
  }
  document.addEventListener('click', function(e){
    const b = e.target.closest('.tab');
    if(b){ activateTab(b); }
    const close = e.target.closest('[data-close-slideover]');
    if(close){ const s = document.getElementById('slideover'); if(s) s.innerHTML=''; }
  });
  document.addEventListener('keydown', function(e){
    if(e.key === 'Escape'){ const s = document.getElementById('slideover'); if(s) s.innerHTML=''; }
  });
})();

