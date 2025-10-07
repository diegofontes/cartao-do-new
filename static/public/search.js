(function(){
  function qs(sel){ return document.querySelector(sel); }
  const form = qs('#search-form');
  const geoBtn = qs('#geo-btn');
  const loading = qs('#search-loading');
  const cepForm = qs('#cep-form');
  const cepFeedback = qs('#cep-public-feedback');
  const latInput = form?.querySelector('input[name="lat"]');
  const lngInput = form?.querySelector('input[name="lng"]');

  function setLoading(state){
    if(!loading) return;
    loading.classList.toggle('is-visible', !!state);
  }

  function setFeedback(msg){
    if(!cepFeedback) return;
    cepFeedback.textContent = msg || '';
  }

  function submitForm(){
    if(!form) return;
    if(typeof form.requestSubmit === 'function') form.requestSubmit();
    else form.submit();
  }

  function setCoords(lat, lng){
    if(latInput) latInput.value = lat.toFixed(6);
    if(lngInput) lngInput.value = lng.toFixed(6);
    submitForm();
  }

  if(geoBtn && navigator.geolocation){
    geoBtn.addEventListener('click', function(){
      setFeedback('Obtendo localização...');
      navigator.geolocation.getCurrentPosition(function(pos){
        const { latitude, longitude } = pos.coords;
        setFeedback('Localização encontrada!');
        setCoords(latitude, longitude);
      }, function(err){
        setFeedback('Não foi possível obter a localização (' + (err.message || 'erro') + ').');
      });
    });
  }

  if(form){
    form.addEventListener('htmx:beforeRequest', () => setLoading(true));
    form.addEventListener('htmx:afterSwap', () => setLoading(false));
    form.addEventListener('htmx:responseError', () => setLoading(false));
  }

  function getCsrf(){
    const meta = document.querySelector('meta[name="csrf-token"]');
    if(meta) return meta.getAttribute('content');
    const match = document.cookie.match('(^|;)\\s*(viewer_csrftoken|csrftoken)\\s*=\\s*([^;]+)');
    return match ? match.pop() : '';
  }

  if(cepForm){
    cepForm.addEventListener('submit', function(evt){
      evt.preventDefault();
      const cepInput = qs('#cep-public');
      const cep = (cepInput && cepInput.value || '').trim();
      if(!cep){
        setFeedback('Informe um CEP para buscar.');
        return;
      }
      const endpoint = window.SEARCH_ENDPOINTS && window.SEARCH_ENDPOINTS.geocode;
      if(!endpoint){
        setFeedback('Endpoint de geocodificação não disponível.');
        return;
      }
      setFeedback('Consultando CEP...');
      fetch(endpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'X-CSRFToken': getCsrf()
        },
        body: new URLSearchParams({cep})
      }).then(function(resp){
        return resp.json().then(function(data){ return {ok: resp.ok, data: data}; });
      }).then(function(payload){
        if(!payload.ok){
          setFeedback(payload.data.error || 'CEP não encontrado.');
          return;
        }
        setFeedback('Coordenadas preenchidas a partir do CEP.');
        setCoords(payload.data.lat, payload.data.lng);
      }).catch(function(){
        setFeedback('Não foi possível consultar o CEP agora.');
      });
    });
  }
})();
