(function(){
  const form = document.getElementById('search-form');
  if (!form) return;

  const radiusField = document.getElementById('radius-input');
  const addressInput = document.getElementById('search-address');
  const geoBtn = document.getElementById('btn-geoloc');
  const geoFeedback = document.getElementById('geo-feedback');
  const resultsUrl = form.dataset.resultsUrl || '/search/results';
  const clearButton = form.querySelector('[data-action="clear-address"]');
  const latHidden = document.getElementById('search-lat');
  const lngHidden = document.getElementById('search-lng');
  const limitField = form.querySelector('input[name="limit"]');
  const offsetField = form.querySelector('input[name="offset"]');
  const pageSize = Math.max(1, parseInt(form.dataset.pageSize || '15', 10) || 15);
  const defaultGeoMessage = 'Informe um endereço ou capture sua localização para buscar cards próximos.';
  let geoCoords = null;

  function ensureLimitField(){
    if (limitField) {
      limitField.value = String(pageSize);
    }
  }

  function resetOffsetField(){
    if (offsetField) {
      offsetField.value = '0';
    }
  }

  ensureLimitField();
  if (offsetField && !offsetField.value) {
    resetOffsetField();
  }

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
    if (addressInput) {
      addressInput.value = '';
      addressInput.focus();
    }
    resetOffsetField();
    geoCoords = null;
    if (latHidden) latHidden.value = '';
    if (lngHidden) lngHidden.value = '';
    setGeoFeedback(defaultGeoMessage);
  });

  addressInput?.addEventListener('input', function(){
    geoCoords = null;
    resetOffsetField();
    if (latHidden) latHidden.value = '';
    if (lngHidden) lngHidden.value = '';
    if (this.value.trim()) {
      setGeoFeedback('Endereço informado. Clique em "Procurar" para buscar.');
    } else {
      setGeoFeedback(defaultGeoMessage);
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
      geoFeedback.textContent = message || defaultGeoMessage;
    }
  }

  function assembleResultsUrl(lat, lng){
    const params = new URLSearchParams();
    params.set('lat', lat.toFixed(6));
    params.set('lng', lng.toFixed(6));
    params.set('limit', String(pageSize));
    params.set('offset', '0');
    ensureLimitField();
    resetOffsetField();
    const categoryInput = form.querySelector('input[name="category"]:checked');
    const category = categoryInput && categoryInput.value;
    if (category) params.set('category', category);
    const radius = currentRadius();
    if (isFinite(radius)) params.set('radius_km', radius);
    return `${resultsUrl}?${params.toString()}`;
  }

  function loadResults(lat, lng){
    window.location.href = assembleResultsUrl(lat, lng);
  }

  geoBtn?.addEventListener('click', function(){
    if (!navigator.geolocation) {
      toast('error', 'Geolocalização não suportada neste navegador.');
      return;
    }
    resetOffsetField();
    setGeoFeedback('Obtendo localização…');
    navigator.geolocation.getCurrentPosition(
      function(position){
        const { latitude, longitude } = position.coords;
        geoCoords = { lat: latitude, lng: longitude };
        if (latHidden) latHidden.value = latitude.toFixed(6);
        if (lngHidden) lngHidden.value = longitude.toFixed(6);
        const pretty = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 3 });
        setGeoFeedback(`Localização capturada (${pretty.format(latitude)}, ${pretty.format(longitude)}). Clique em "Procurar" para buscar.`);
      },
      function(){
        geoCoords = null;
        if (latHidden) latHidden.value = '';
        if (lngHidden) lngHidden.value = '';
        setGeoFeedback('Não foi possível obter sua localização.');
        toast('error', 'Não foi possível obter sua localização.');
      }
    );
  });

  form.addEventListener('submit', function(event){
    resetOffsetField();
    const address = addressInput && addressInput.value.trim();
    if (!address && geoCoords) {
      setGeoFeedback('Buscando cards próximos com sua localização…');
      if (!window.htmx) {
        event.preventDefault();
        loadResults(geoCoords.lat, geoCoords.lng);
      }
    }
  });

  form.addEventListener('htmx:configRequest', function(event){
    if (event.target !== form) return;
    const detail = event.detail;
    if (!detail) return;
    const address = addressInput && addressInput.value.trim();
    if (address || !geoCoords) return;
    const url = assembleResultsUrl(geoCoords.lat, geoCoords.lng);
    detail.path = url;
    detail.verb = 'GET';
    if (detail.parameters) detail.parameters = {};
    if (detail.unfilteredParameters) detail.unfilteredParameters = {};
    if (detail.headers) {
      delete detail.headers['Content-Type'];
    }
  });
})();
