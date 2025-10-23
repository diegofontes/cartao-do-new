// Dashboard UI helpers (agenda sizing & positioning)
(function(){
  function byId(id){ return document.getElementById(id); }

  function sizeAgendaMain(){
    try{
      var root = byId('agenda-root');
      if(!root) return;
      var vh = (window.visualViewport && window.visualViewport.height) || window.innerHeight;
      var rect = root.getBoundingClientRect();
      var bottomPad = 12; // breathing room
      var h = Math.max(240, vh - rect.top - bottomPad);
      root.style.height = h + 'px';
      root.style.maxHeight = h + 'px';
    }catch(_){/* noop */}
  }

  function scrollAgendaToNow(){
    try{
      var root = byId('agenda-root');
      var page = byId('agenda-page');
      if(!root || !page) return;
      var currentView = page.getAttribute('data-view') || (window.__agendaView__ || 'day');
      if(currentView === 'month') return; // not applicable
      var events = byId('events-layer');
      if(!events) return;
      var slotHStr = getComputedStyle(document.documentElement).getPropertyValue('--slot-h').trim();
      var slotH = parseFloat(slotHStr) || 56; // px per half-hour
      var now = new Date();
      var minutes = now.getHours()*60 + now.getMinutes();
      var halfSlots = minutes / 30;
      var y = halfSlots * slotH;
      var topGap = events.getBoundingClientRect().top - root.getBoundingClientRect().top;
      var target = topGap + y - (root.clientHeight * 0.4);
      root.scrollTo({ top: Math.max(0, target), behavior: 'smooth' });
    }catch(_){/* noop */}
  }

  function recalibrateAgenda(){ sizeAgendaMain(); scrollAgendaToNow(); }

  // Now line helpers
  function getCurrentView(){
    var page = byId('agenda-page');
    return page ? (page.getAttribute('data-view') || 'day') : 'day';
  }
  function getEventsLayer(){ return byId('events-layer'); }
  function ensureNowLine(){
    try{
      if(getCurrentView() === 'month') return; // not applicable
      var layer = getEventsLayer();
      if(!layer) return;
      var line = byId('now-line');
      if(!line){
        line = document.createElement('div');
        line.id = 'now-line';
        line.setAttribute('aria-hidden', 'true');
        layer.appendChild(line);
      }
      updateNowLinePosition();
    }catch(_){/* noop */}
  }
  function updateNowLinePosition(){
    try{
      if(getCurrentView() === 'month') return; // not applicable
      var layer = getEventsLayer();
      var root = byId('agenda-root');
      var line = byId('now-line');
      if(!(layer && root && line)) return;
      var slotHStr = getComputedStyle(document.documentElement).getPropertyValue('--slot-h').trim();
      var slotH = parseFloat(slotHStr) || 56;
      var now = new Date();
      var minutes = now.getHours()*60 + now.getMinutes();
      var halfSlots = minutes / 30;
      var y = halfSlots * slotH; // position inside events grid
      line.style.position = 'absolute';
      line.style.left = 0;
      line.style.right = 0;
      line.style.top = y + 'px';
      line.style.height = '2px';
      line.style.background = 'var(--accent)';
      line.style.opacity = '.75';
      line.style.pointerEvents = 'none';
    }catch(_){/* noop */}
  }
  function tickNowLine(){ updateNowLinePosition(); }

  // Expose for hx-on or manual calls if needed
  window.Agenda = {
    size: sizeAgendaMain,
    scrollToNow: scrollAgendaToNow,
    recalibrate: recalibrateAgenda,
    ensureNowLine: ensureNowLine,
    updateNowLine: updateNowLinePosition
  };

  // Initial load
  document.addEventListener('DOMContentLoaded', recalibrateAgenda);
  window.addEventListener('resize', sizeAgendaMain);

  // HTMX lifecycle hooks
  function onAfterSwap(e){
    try{
      if(!e || !e.target) return;
      if(e.target.id === 'agenda-page' || e.target.id === 'events-layer'){
        setTimeout(function(){
          recalibrateAgenda();
          ensureNowLine();
        }, 0);
      }
    }catch(_){/* noop */}
  }
  function onAfterOnLoad(e){
    try{
      if(!e || !e.target) return;
      if(e.target.id === 'events-layer'){
        setTimeout(function(){
          scrollAgendaToNow();
          ensureNowLine();
        }, 0);
      }
    }catch(_){/* noop */}
  }
  function onAfterSettle(e){
    try{
      if(!e || !e.target) return;
      if(e.target.id === 'agenda-page' || e.target.id === 'events-layer'){
        setTimeout(function(){
          recalibrateAgenda();
          ensureNowLine();
        }, 0);
      }
    }catch(_){/* noop */}
  }
  if (window.htmx && typeof window.htmx.on === 'function'){
    window.htmx.on('htmx:afterSwap', onAfterSwap);
    window.htmx.on('htmx:afterOnLoad', onAfterOnLoad);
    window.htmx.on('htmx:afterSettle', onAfterSettle);
  } else {
    // If HTMX loads later, attach once it is ready
    document.addEventListener('htmx:load', function(){
      try{
        window.htmx.on('htmx:afterSwap', onAfterSwap);
        window.htmx.on('htmx:afterOnLoad', onAfterOnLoad);
        window.htmx.on('htmx:afterSettle', onAfterSettle);
      }catch(_){/* noop */}
    });
  }

  // Keep the now line updated every minute
  setInterval(tickNowLine, 60000);
  // Ensure it exists on initial load
  document.addEventListener('DOMContentLoaded', ensureNowLine);
})();

// EasyMDE integration for Card "Sobre" editor
(function(){
  function initEditor(container){
    try{
      if (!container) return;
      var textarea = container.querySelector('textarea[name="about_markdown"]');
      if (!textarea) return;
      if (!window.EasyMDE) {
        // Retry once EasyMDE loads
        setTimeout(function(){ initEditor(container); }, 120);
        return;
      }
      if (textarea._easyMDEInstance) {
        return;
      }
      var readOnly = textarea.hasAttribute('disabled');
      var editor = new EasyMDE({
        element: textarea,
        autoDownloadFontAwesome: true,
        spellChecker: false,
        status: ["words", "lines"],
        toolbar: [
          "heading", "bold", "italic", "strikethrough",
          "|",
          "unordered-list", "ordered-list", "quote",
          "|",
          "link", "image", "code", "table", "horizontal-rule",
          "|",
          {
            name: "guide",
            action: function customGuide(){
              window.open("https://commonmark.org/help/", "_blank", "noopener,noreferrer");
            },
            className: "fa fa-question-circle",
            title: "Guia Markdown"
          }
        ],
        renderingConfig: {
          singleLineBreaks: false
        }
      });
      textarea._easyMDEInstance = editor;
      if (readOnly){
        editor.codemirror.setOption("readOnly", "nocursor");
        var toolbar = container.querySelector(".editor-toolbar");
        if (toolbar){
          toolbar.style.pointerEvents = "none";
          toolbar.style.opacity = "0.5";
        }
      }
      editor.codemirror.on("change", function(){
        try{
          textarea.value = editor.value();
          textarea.dispatchEvent(new Event("input", { bubbles: true }));
          textarea.dispatchEvent(new Event("change", { bubbles: true }));
        }catch(_){/* noop */}
      });
    }catch(_){/* noop */}
  }

  function destroyEditor(container){
    try{
      if (!container) return;
      var textarea = container.querySelector('textarea[name="about_markdown"]');
      if (!textarea) return;
      var inst = textarea._easyMDEInstance;
      if (inst && typeof inst.toTextArea === "function"){
        inst.toTextArea();
      }
      delete textarea._easyMDEInstance;
    }catch(_){/* noop */}
  }

  function handleInitial(){
    var block = document.getElementById("card-about");
    if (block){
      initEditor(block);
    }
  }

  document.addEventListener("DOMContentLoaded", handleInitial);

  if (window.htmx && typeof window.htmx.on === "function"){
    window.htmx.on("htmx:beforeSwap", function(evt){
      if (evt && evt.target && evt.target.id === "card-about"){
        destroyEditor(evt.target);
      }
    });
    window.htmx.on("htmx:afterSwap", function(evt){
      if (evt && evt.target && evt.target.id === "card-about"){
        initEditor(evt.target);
      }
    });
  } else {
    document.addEventListener("htmx:load", function(){
      try{
        window.htmx.on("htmx:beforeSwap", function(evt){
          if (evt && evt.target && evt.target.id === "card-about"){
            destroyEditor(evt.target);
          }
        });
        window.htmx.on("htmx:afterSwap", function(evt){
          if (evt && evt.target && evt.target.id === "card-about"){
            initEditor(evt.target);
          }
        });
      }catch(_){/* noop */}
    });
  }
})();
