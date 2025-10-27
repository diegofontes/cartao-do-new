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

  const phoneMasked = new WeakSet();

  function digitsOnly(val){
    return (val || '').replace(/\D+/g, '');
  }

  function normalizeLocalDigits(raw){
    const txt = String(raw || '');
    let digits = digitsOnly(txt);
    if(!digits){ return ''; }
    if(txt.trim().startsWith('+55')){
      digits = digits.replace(/^55/, '');
    }else if(digits.startsWith('55') && digits.length > 11){
      digits = digits.slice(2);
    }
    if(digits.length > 11){
      digits = digits.slice(-11);
    }
    while(digits.length && digits[0] === '0'){
      digits = digits.slice(1);
    }
    return digits.slice(0, 11);
  }

  function formatBrazilPhone(raw){
    const local = normalizeLocalDigits(raw);
    if(!local){ return ''; }
    if(local.length <= 2){
      return '+55 (' + local;
    }
    const ddd = local.slice(0, 2);
    const subscriber = local.slice(2);
    if(!subscriber){
      return '+55 (' + ddd + ') ';
    }
    if(subscriber.length <= 5){
      return '+55 (' + ddd + ') ' + subscriber;
    }
    return '+55 (' + ddd + ') ' + subscriber.slice(0, 5) + '-' + subscriber.slice(5);
  }

  function applyPhoneMask(input){
    if(!input || phoneMasked.has(input)){ return; }
    phoneMasked.add(input);
    const handler = function(){
      const formatted = formatBrazilPhone(input.value);
      input.value = formatted;
      if(document.activeElement === input && typeof input.setSelectionRange === 'function'){
        const pos = formatted.length;
        input.setSelectionRange(pos, pos);
      }
    };
    input.addEventListener('input', handler);
    input.addEventListener('blur', handler);
    handler();
  }

  function initPhoneMask(root){
    const scope = root instanceof Element ? root : document;
    scope.querySelectorAll('[data-phone-mask]').forEach(applyPhoneMask);
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', function(){ initPhoneMask(document); });
  }else{
    initPhoneMask(document);
  }

  document.addEventListener('htmx:afterSwap', function(evt){
    if(evt && evt.detail && evt.detail.target){
      initPhoneMask(evt.detail.target);
    }
  });
})();
