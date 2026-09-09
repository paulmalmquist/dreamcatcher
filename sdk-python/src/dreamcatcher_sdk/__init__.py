"""Dependency-free backend SDK. Never put warehouse credentials in an app."""
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class DreamcatcherError(RuntimeError):
    def __init__(self, status, detail):
        self.status, self.detail = status, detail
        super().__init__(str(detail))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Dreamcatcher:
    """Create one client per authenticated user request; token is app-scoped."""
    def __init__(self, *, base_url, app_id, token, timeout=35):
        url = urlsplit(base_url)
        if url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
            raise ValueError('Use a clean gateway origin')
        if url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError('HTTPS required outside local development')
        if not re.fullmatch(r'[A-Za-z0-9-]{2,80}', app_id) or not token:
            raise ValueError('App identity and scoped token are required')
        self.base, self.app_id, self.token, self.timeout = base_url.rstrip('/'), app_id, token, timeout
        self.opener = build_opener(NoRedirect())

    def _request(self, path, body=None, method=None):
        request = Request(self.base + '/api' + path, data=json.dumps(body, allow_nan=False).encode() if body is not None else None,
                          method=method or ('POST' if body is not None else 'GET'),
                          headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                return json.load(response)
        except HTTPError as error:
            try: detail = json.loads(error.read()).get('detail', 'Gateway request failed')
            except (ValueError, AttributeError): detail = 'Gateway request failed'
            raise DreamcatcherError(error.code, detail) from None

    def context(self):
        return self._request('/v2/runtime/' + self.app_id + '/context')

    def query(self, reference, parameters):
        return self._request('/execute/query', {'app_id': self.app_id, 'reference': reference, 'parameters': parameters})

    def skill(self, reference, inputs):
        return self._request('/execute/skill', {'app_id': self.app_id, 'reference': reference, 'parameters': inputs})

    def _state_path(self, collection, key):
        if not all(re.fullmatch(r'[A-Za-z0-9_-]{1,120}', v) for v in (collection, key)):
            raise ValueError('Invalid state key or collection')
        return '/v2/runtime/' + self.app_id + '/state/' + collection + '/' + key

    def state_get(self, collection, key):
        return self._request(self._state_path(collection, key))

    def state_put(self, collection, key, value, *, expected_version, idempotency_key):
        return self._request(self._state_path(collection, key), {'value': value, 'expected_version': expected_version, 'idempotency_key': idempotency_key}, 'PUT')
