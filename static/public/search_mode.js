(function(){
  const form = document.getElementById('search-form');
  if (!form) return;

  const radiusField = document.getElementById('radius-input');
  const geoBtn = document.getElementById('btn-geoloc');
  const geoFeedback = document.getElementById('geo-feedback');
  const resultsUrl = form.dataset.resultsUrl || '/search/results';
  const clearButton = form.querySelector('[data-action="clear-address"]');

  function currentRadius(){
    if (!radiusField) {
      return parseFloat(form.dataset.defaultRadius || '10');
    }
    const min = parseFloat(radiusField.getAttribute('min') || '1');
    const max = parseFloat(radiusField.getAttribute('max') || '50');
    let value = parseFloat(radiusField.value);
    if (!isFinite(value)) value = parseFloat(form.dataset.defaultRadius || '10');
    if (value < min) value = min;
    if (value > max) value = max;
    // keep select/number in sync if clamped
    if (String(value) !== radiusField.value) {
      radiusField.value = String(value);
    }
    return value;
  }

  radiusField?.addEventListener('change', function(){
    currentRadius();
  });

  clearButton?.addEventListener('click', function(){
    const address = document.getElementById('search-address');
    if (address) {
      address.value = '';
      address.focus();
    }
  });

  function toast(kind, message){
    const host = document.getElementById('toasts');
    if (!host) {
      window.alert(message);
      return;
    }
    const el = document.createElement('div');
    el.className = `toast ${kind === 'error' ? 'err' : 'ok'}`;
    el.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    el.innerHTML = `
      <div class="toast-copy">
        <div class="title">${kind === 'error' ? 'Aviso' : 'Tudo certo'}</div>
        <div class="msg">${message}</div>
      </div>
      <button type="button" class="toast-close" aria-label="Fechar aviso">&times;</button>
    `;
    el.querySelector('.toast-close')?.addEventListener('click', function(){ el.remove(); });
    host.appendChild(el);
    window.setTimeout(function(){ el.remove(); }, kind === 'error' ? 6000 : 4000);
  }

  function setGeoFeedback(message){
    if (geoFeedback) {
      geoFeedback.textContent = message || '';
    }
  }

  function assembleResultsUrl(lat, lng){
    const params = new URLSearchParams();
    params.set('lat', lat.toFixed(6));
    params.set('lng', lng.toFixed(6));
    const categoryInput = form.querySelector('[name="category"]');
    const category = categoryInput && categoryInput.value;
    if (category) params.set('category', category);
    const radius = currentRadius();
    if (isFinite(radius)) params.set('radius_km', radius);
    return `${resultsUrl}?${params.toString()}`;
  }

  function loadResults(lat, lng){
    if (!window.htmx) {
      window.location.href = assembleResultsUrl(lat, lng);
      return;
    }
    const url = assembleResultsUrl(lat, lng);
    window.htmx.ajax('GET', url, {
      target: '#results',
      swap: 'outerHTML',
      indicator: '#results-loading'
    });
  }

  geoBtn?.addEventListener('click', function(){
    if (!navigator.geolocation) {
      toast('error', 'Geolocalização não suportada neste navegador.');
      return;
    }
    setGeoFeedback('Obtendo localização…');
    navigator.geolocation.getCurrentPosition(
      function(position){
        const { latitude, longitude } = position.coords;
        setGeoFeedback('Localização encontrada.');
        loadResults(latitude, longitude);
      },
      function(){
        setGeoFeedback('');
        toast('error', 'Não foi possível obter sua localização.');
      }
    );
  });
})();
