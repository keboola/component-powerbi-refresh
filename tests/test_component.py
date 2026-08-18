import json
import os
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

import requests
from freezegun import freeze_time
from keboola.component.exceptions import UserException

from component import NO_FAILURE_DETAIL, RATE_LIMIT_DEFAULT_WAIT, Component, TooManyRequestsError


class TestComponent(unittest.TestCase):
    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {"KBC_DATADIR": "./non-existing-dir"})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()


class TestTooManyRequestsError(unittest.TestCase):
    def test_message_includes_retry_after(self):
        err = TooManyRequestsError(retry_after=23)
        self.assertEqual(err.retry_after, 23)
        self.assertIn("429", str(err))
        self.assertIn("23", str(err))

    def test_none_retry_after(self):
        err = TooManyRequestsError()
        self.assertIsNone(err.retry_after)


class TestGetRetryAfter(unittest.TestCase):
    def test_parses_header(self):
        response = MagicMock()
        response.headers = {"Retry-After": "23"}
        self.assertEqual(Component._get_retry_after(response), 23)

    def test_falls_back_to_default_when_missing(self):
        response = MagicMock()
        response.headers = {}
        self.assertEqual(Component._get_retry_after(response), RATE_LIMIT_DEFAULT_WAIT)

    def test_falls_back_to_default_when_invalid(self):
        response = MagicMock()
        response.headers = {"Retry-After": "soon"}
        self.assertEqual(Component._get_retry_after(response), RATE_LIMIT_DEFAULT_WAIT)

    def test_custom_default(self):
        response = MagicMock()
        response.headers = {}
        self.assertEqual(Component._get_retry_after(response, default=120), 120)


class TestCheckRateLimit(unittest.TestCase):
    def test_raises_on_429(self):
        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "23"}
        comp = Component.__new__(Component)
        with self.assertRaises(TooManyRequestsError) as ctx:
            comp._check_rate_limit(response)
        self.assertEqual(ctx.exception.retry_after, 23)

    def test_noop_on_200(self):
        response = MagicMock()
        response.status_code = 200
        comp = Component.__new__(Component)
        comp._check_rate_limit(response)  # should not raise

    def test_noop_on_202(self):
        response = MagicMock()
        response.status_code = 202
        comp = Component.__new__(Component)
        comp._check_rate_limit(response)  # should not raise


class TestRefreshDataset429(unittest.TestCase):
    @patch("time.sleep")
    @patch("component.requests.post")
    def test_retries_on_429_then_succeeds(self, mock_post, mock_sleep):
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "23"}

        response_202 = MagicMock()
        response_202.status_code = 202
        response_202.headers = {"RequestId": "test-id"}

        mock_post.side_effect = [response_429, response_202]

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test", "Content-Type": "application/json"}

        result = comp.refresh_dataset("groups/workspace-id", "dataset-id")

        self.assertEqual(result, response_202)
        self.assertEqual(mock_post.call_count, 2)
        mock_sleep.assert_called_once_with(23)

    @patch("time.sleep")
    @patch("component.requests.post")
    def test_returns_false_on_non_429_error(self, mock_post, mock_sleep):
        response_400 = MagicMock()
        response_400.status_code = 400
        response_400.headers = {}
        response_400.text = '{"error": {"code": "BadRequest", "message": "Invalid"}}'

        mock_post.return_value = response_400

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test", "Content-Type": "application/json"}

        result = comp.refresh_dataset("groups/workspace-id", "dataset-id")

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()


class TestGetRequest429(unittest.TestCase):
    @patch("time.sleep")
    @patch("component.requests.get")
    def test_retries_on_429_then_succeeds(self, mock_get, mock_sleep):
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "23"}

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.headers = {}

        mock_get.side_effect = [response_429, response_200]

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test", "Content-Type": "application/json"}

        result = comp._get_request("https://api.powerbi.com/v1.0/myorg/test")

        self.assertEqual(result, response_200)
        self.assertEqual(mock_get.call_count, 2)
        mock_sleep.assert_called_once_with(23)


class TestRequestNewTokenRetry(unittest.TestCase):
    """
    A transient connection reset on the OAuth token endpoint must be retried.

    Regression: the token POST was the only un-retried HTTP call in the component, so
    `('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))` propagated
    out of `run()` and ended the job as an opaque internal error (exit 2).
    """

    @staticmethod
    def _token_response() -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"access_token": "new-access-token", "refresh_token": "new-refresh-token"}
        return response

    @patch("time.sleep")
    @patch("component.requests.post")
    def test_retries_on_connection_reset_then_succeeds(self, mock_post, mock_sleep):
        mock_post.side_effect = [
            requests.exceptions.ConnectionError(
                "('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))"
            ),
            self._token_response(),
        ]

        result = Component._request_new_token("client-id", "client-secret", "refresh-token")

        self.assertEqual(result, {"access_token": "new-access-token", "refresh_token": "new-refresh-token"})
        self.assertEqual(mock_post.call_count, 2)

    @patch("time.sleep")
    @patch("component.requests.post")
    def test_reraises_after_last_attempt(self, mock_post, mock_sleep):
        """A persistent outage must still fail the job - the retry smooths blips, it never swallows."""
        mock_post.side_effect = requests.exceptions.ConnectionError("('Connection aborted.', ConnectionResetError())")

        with self.assertRaises(requests.exceptions.ConnectionError):
            Component._request_new_token("client-id", "client-secret", "refresh-token")

        self.assertEqual(mock_post.call_count, 3)

    @patch("time.sleep")
    @patch("component.requests.post")
    def test_succeeds_first_try_without_sleeping(self, mock_post, mock_sleep):
        """Happy path is untouched: one call, no backoff sleep."""
        mock_post.return_value = self._token_response()

        result = Component._request_new_token("client-id", "client-secret", "refresh-token")

        self.assertEqual(result, {"access_token": "new-access-token", "refresh_token": "new-refresh-token"})
        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("component.requests.post")
    def test_non_200_still_raises_user_exception_without_retry(self, mock_post, mock_sleep):
        """A rejected token is not transient - it must stay an immediate, un-retried user error."""
        response_401 = MagicMock()
        response_401.status_code = 401
        response_401.reason = "Unauthorized"
        response_401.json.return_value = {"error": "invalid_grant"}
        mock_post.return_value = response_401

        with self.assertRaises(UserException):
            Component._request_new_token("client-id", "client-secret", "refresh-token")

        self.assertEqual(mock_post.call_count, 1)
        mock_sleep.assert_not_called()


def _history_response(entries) -> MagicMock:
    """Builds a mock PowerBI refresh-history response with the given `value` entries."""
    response = MagicMock()
    response.status_code = 200
    response.content = json.dumps({"value": entries}).encode()
    response.json.return_value = {"value": entries}
    return response


class TestGetFailureDetail(unittest.TestCase):
    """`serviceExceptionJson` is optional in the PowerBI refresh-history payload."""

    def test_returns_detail_from_original_lookup(self):
        response = _history_response(
            [
                {"requestId": "req-0", "status": "Completed"},
                {"requestId": "req-1", "status": "Failed", "serviceExceptionJson": "boom-at-index-1"},
            ]
        )
        self.assertEqual(Component._get_failure_detail(response, "req-1"), "boom-at-index-1")

    def test_falls_back_to_polled_request_when_detail_missing(self):
        response = _history_response(
            [
                {"requestId": "req-0", "status": "Completed"},
                {"requestId": "req-1", "status": "Failed"},  # no serviceExceptionJson
                {"requestId": "req-2", "status": "Failed", "serviceExceptionJson": "boom-for-req-2"},
            ]
        )
        self.assertEqual(Component._get_failure_detail(response, "req-2"), "boom-for-req-2")

    def test_placeholder_when_history_has_single_entry(self):
        response = _history_response([{"requestId": "req-0", "status": "Failed"}])
        self.assertEqual(Component._get_failure_detail(response, "req-0"), NO_FAILURE_DETAIL)

    def test_placeholder_when_no_entry_carries_a_detail(self):
        response = _history_response(
            [
                {"requestId": "req-0", "status": "Failed"},
                {"requestId": "req-1", "status": "Failed"},
            ]
        )
        self.assertEqual(Component._get_failure_detail(response, "req-0"), NO_FAILURE_DETAIL)

    def test_placeholder_when_request_id_is_not_a_string(self):
        """The helper must never raise, even on a null/non-string requestId."""
        response = _history_response(
            [
                {"requestId": None, "status": "Failed"},
                {"requestId": 42, "status": "Failed"},
                "not-a-dict",
            ]
        )
        self.assertEqual(Component._get_failure_detail(response, "req-0"), NO_FAILURE_DETAIL)

    def test_placeholder_on_malformed_payload(self):
        response = MagicMock()
        response.content = b"not json at all"
        self.assertEqual(Component._get_failure_detail(response, "req-0"), NO_FAILURE_DETAIL)


class TestProcessStatusFailedRaisesUserException(unittest.TestCase):
    """A failed PowerBI refresh must exit 1 with a readable message, never a bare KeyError (exit 2)."""

    @staticmethod
    def _component() -> Component:
        comp = Component.__new__(Component)
        comp.failed_list = []
        comp.alldatasets = False
        comp.dataset_names = {}
        comp.requestid_array = [["dataset-id", "req-1"]]
        return comp

    def test_raises_user_exception_with_detail(self):
        comp = self._component()
        response = _history_response(
            [
                {"requestId": "req-0", "status": "Completed"},
                {"requestId": "req-1", "status": "Failed", "serviceExceptionJson": "boom-at-index-1"},
            ]
        )
        with self.assertRaises(UserException) as ctx:
            comp.process_status(response, ["dataset-id", "req-1"], [], [])
        self.assertIn("boom-at-index-1", str(ctx.exception))

    def test_raises_user_exception_when_detail_is_absent(self):
        """Regression: this payload used to raise KeyError('serviceExceptionJson') and exit 2."""
        comp = self._component()
        response = _history_response([{"requestId": "req-1", "status": "Failed"}])
        with self.assertRaises(UserException) as ctx:
            comp.process_status(response, ["dataset-id", "req-1"], [], [])
        self.assertIn(NO_FAILURE_DETAIL, str(ctx.exception))
        self.assertIn("dataset-id", str(ctx.exception))


class TestTokenAuthority(unittest.TestCase):
    """The token authority must be configurable to support B2B guest accounts."""

    @staticmethod
    def _post_url(tenant_id=None) -> str:
        kwargs = {} if tenant_id is None else {"tenant_id": tenant_id}
        with patch("component.requests.post") as post:
            post.return_value = MagicMock(status_code=200, json=lambda: {"access_token": "a", "refresh_token": "r"})
            Component._request_new_token("client", "secret", "refresh", **kwargs)
        return post.call_args[0][0]

    def test_defaults_to_common_authority(self):
        self.assertEqual(self._post_url(), "https://login.microsoftonline.com/common/oauth2/token")

    def test_blank_tenant_falls_back_to_common(self):
        self.assertEqual(self._post_url(""), "https://login.microsoftonline.com/common/oauth2/token")

    def test_uses_tenant_specific_authority(self):
        self.assertEqual(self._post_url("tenant-guid"), "https://login.microsoftonline.com/tenant-guid/oauth2/token")

    def test_error_response_with_empty_body_raises_user_exception(self):
        """Regression: an empty/non-JSON error body used to raise JSONDecodeError and exit 2."""
        response = MagicMock(status_code=404, reason="Not Found", text="")
        response.json.side_effect = ValueError("no json")
        with patch("component.requests.post", return_value=response):
            with self.assertRaises(UserException) as ctx:
                Component._request_new_token("client", "secret", "refresh", tenant_id="contoso.onmicrosoft.com")
        self.assertIn("404", str(ctx.exception))
        self.assertIn(NO_FAILURE_DETAIL, str(ctx.exception))

    def test_error_response_with_text_body_surfaces_text(self):
        response = MagicMock(status_code=500, reason="Server Error", text="  upstream exploded  ")
        response.json.side_effect = ValueError("no json")
        with patch("component.requests.post", return_value=response):
            with self.assertRaises(UserException) as ctx:
                Component._request_new_token("client", "secret", "refresh")
        self.assertIn("upstream exploded", str(ctx.exception))


class TestResolveTenantId(unittest.TestCase):
    """Blank keeps the historical `common` authority; malformed input fails cleanly, not with a traceback."""

    def test_missing_and_blank_values_default_to_common(self):
        for raw in (None, "", "   ", False, 0):
            with self.subTest(raw=raw):
                self.assertEqual(Component._resolve_tenant_id(raw), "common")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(Component._resolve_tenant_id("  contoso.onmicrosoft.com  "), "contoso.onmicrosoft.com")

    def test_accepts_guid_and_domain(self):
        for raw in ("11111111-2222-3333-4444-555555555555", "contoso.onmicrosoft.com", "common"):
            with self.subTest(raw=raw):
                self.assertEqual(Component._resolve_tenant_id(raw), raw)

    def test_non_string_truthy_value_does_not_crash(self):
        """A config written via the API could supply a number; it must not raise AttributeError."""
        self.assertEqual(Component._resolve_tenant_id(12345), "12345")

    def test_rejects_url_structured_values(self):
        malformed = [
            "https://login.microsoftonline.com/11111111-2222-3333-4444-555555555555/",
            "common/oauth2/token",
            "common?x=",
            "common#frag",
            "../../foo",
            "two words",
            "tenant\nid",
            "-leading-dash-is-not-a-tenant-",
        ]
        for raw in malformed:
            with self.subTest(raw=raw):
                with self.assertRaises(UserException) as ctx:
                    Component._resolve_tenant_id(raw)
                self.assertIn("not a valid Microsoft Entra tenant identifier", str(ctx.exception))


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
