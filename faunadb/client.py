from time import time
# pylint: disable=redefined-builtin
from builtins import object

from requests import Request, Session

from faunadb.errors import get_or_invalid, FaunaError
from faunadb.objects import Ref
from faunadb.query import to_query
from faunadb.request_result import RequestResult
from faunadb._json import parse_json, to_json


class Client(object):
  """
  Directly communicates with FaunaDB via JSON.

  For data sent to the server, the ``to_fauna_json`` method will be called on any values.
  It is encouraged to pass e.g. :any:`Ref` objects instead of raw JSON data.

  All methods return a converted JSON response.
  This is a dict containing lists, ints, floats, strings, and other dicts.
  Any :any:`Ref`, :any:`Set`, :any:`FaunaTime`, or :class:`datetime.date`
  values in it will also be parsed.
  (So instead of ``{ "@ref": "classes/frogs/123" }``, you will get ``Ref("classes/frogs", "123")``.)
  """

  # pylint: disable=too-many-arguments, too-many-instance-attributes
  def __init__(
      self,
      domain="rest.faunadb.com",
      scheme="https",
      port=None,
      timeout=60,
      secret=None,
      observer=None):
    """
    :param domain:
      Base URL for the FaunaDB server.
    :param scheme:
      ``"http"`` or ``"https"``.
    :param port:
      Port of the FaunaDB server.
    :param timeout:
      Read timeout in seconds.
    :param secret:
      Auth token for the FaunaDB server.
      Should resemble "username", "username:password", or ("username", "password").
    :param observer:
      Callback that will be passed a :any:`RequestResult` after every completed request.
    """

    self.domain = domain
    self.scheme = scheme
    self.port = (443 if scheme == "https" else 80) if port is None else port

    self.session = Session()
    if secret is not None:
      self.session.auth = Client._parse_secret(secret)

    self.session.headers.update({
      "Accept-Encoding": "gzip",
      "Content-Type": "application/json;charset=utf-8"
    })
    self.session.timeout = timeout

    self.base_url = "%s://%s:%s" % (self.scheme, self.domain, self.port)

    self.observer = observer

  def __del__(self):
    # pylint: disable=bare-except
    try:
      self.session.close()
    except:
      pass

  def get(self, path, query=None):
    """
    HTTP ``GET``.
    See the `docs <https://faunadb.com/documentation/rest>`__.

    :param path: Path relative to ``self.domain``. May be a Ref.
    :param query: Dict to be converted to URL parameters.
    :return: Converted JSON response.
    """
    return self._execute("GET", path, query=query)

  def post(self, path, data=None):
    """
    HTTP ``POST``.
    See the `docs <https://faunadb.com/documentation/rest>`__.

    :param path: Path relative to ``self.domain``. May be a Ref.
    :param data:
      Dict to be converted to request JSON.
      Values in this will have ``to_fauna_json`` called, recursively.
    :return: Converted JSON response.
    """
    return self._execute("POST", path, data)

  def put(self, path, data=None):
    """
    Like :any:`post`, but a ``PUT`` request.
    See the `docs <https://faunadb.com/documentation/rest>`__.
    """
    return self._execute("PUT", path, data)

  def patch(self, path, data=None):
    """
    Like :any:`post`, but a ``PATCH`` request.
    See the `docs <https://faunadb.com/documentation/rest>`__.
    """
    return self._execute("PATCH", path, data)

  def delete(self, path):
    """
    Like :any:`post`, but a ``DELETE`` request.
    See the `docs <https://faunadb.com/documentation/rest>`__.
    """
    return self._execute("DELETE", path)

  def query(self, expression):
    """
    Use the FaunaDB query API.
    See :doc:query.

    :param expression: Argument to :any:`to_query`.
    :return: Converted JSON response.
    """
    return self._execute("POST", "", to_query(expression))

  def ping(self, scope=None, timeout=None):
    """
    Ping FaunaDB.
    See the `docs <https://faunadb.com/documentation/rest#other>`__.
    """
    return self.get("ping", {"scope": scope, "timeout": timeout})

  def _execute(self, action, path, data=None, query=None):
    """Performs an HTTP action, logs it, and looks for errors."""
    # pylint: disable=raising-bad-type
    if isinstance(path, Ref):
      path = path.value
    if query is not None:
      query = {k: v for k, v in query.items() if v is not None}

    start_time = time()
    response = self._perform_request(action, path, data, query)
    end_time = time()
    response_dict = parse_json(response.text)

    request_result = RequestResult(
      self,
      action, path, query, data,
      response_dict, response.status_code, response.headers,
      start_time, end_time)

    if self.observer is not None:
      self.observer(request_result)

    FaunaError.raise_for_status_code(request_result)
    return get_or_invalid(response_dict, "resource")

  def _perform_request(self, action, path, data, query):
    """Performs an HTTP action."""
    url = self.base_url + "/" + path
    req = Request(action, url, params=query, data=to_json(data))
    return self.session.send(self.session.prepare_request(req))

  @staticmethod
  def _parse_secret(secret):
    if isinstance(secret, tuple):
      if len(secret) != 2:
        raise ValueError("Secret tuple must have exactly two entries")
      return secret
    else:
      pair = secret.split(":", 1)
      if len(pair) == 1:
        pair.append("")
      return tuple(pair)
