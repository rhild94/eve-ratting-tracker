// Attach CSRF tokens only to same-origin writes. Never persist private responses.
(() => {
  const account = window.__BOOTSTRAP__?.account;
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (input, options = {}) => {
    const url = new URL(input instanceof Request ? input.url : input, location.href);
    const method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
    if (account && url.origin === location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-CSRF-Token', account.csrf);
      options = {...options, headers};
    }
    const response = await nativeFetch(input, options);
    if (account && url.origin === location.origin && response.status === 401) location.replace('/');
    return response;
  };
  // Clear data rendered by a previously authenticated document on back navigation.
  addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
  // The old tracker stored wave state without an account boundary.
  for (const key of Object.keys(localStorage)) if (key.startsWith('wave_')) localStorage.removeItem(key);
})();
