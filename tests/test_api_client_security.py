import logging
from unittest.mock import Mock

import requests

from web.api_client import NanorvsAPIClient


def test_woocommerce_credentials_use_basic_auth_not_query_params():
    client = NanorvsAPIClient(
        base_url="https://woocommerce.example/wp-json/wc/v3",
        consumer_key="test-consumer-key",
        consumer_secret="test-consumer-secret",
    )
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"id": 1}'

    client.session.get = Mock(return_value=response)

    assert client.get_order(1) == {"id": 1}
    assert client.session.get.call_args.kwargs["params"] == {}
    assert client.session.auth == (
        "test-consumer-key",
        "test-consumer-secret",
    )


def test_woocommerce_request_errors_do_not_log_credentials(caplog):
    secret = "test-consumer-secret"
    client = NanorvsAPIClient(
        base_url="https://woocommerce.example/wp-json/wc/v3",
        consumer_key="test-consumer-key",
        consumer_secret=secret,
    )
    response = requests.Response()
    response.status_code = 401
    response.url = f"https://example.invalid/?consumer_secret={secret}"
    response._content = secret.encode()
    error = requests.HTTPError(
        f"request failed: {response.url}",
        response=response,
    )
    client.session.get = Mock(side_effect=error)

    with caplog.at_level(logging.ERROR):
        assert client.get_order(1) is None

    assert secret not in caplog.text
    assert "consumer-key" not in caplog.text
