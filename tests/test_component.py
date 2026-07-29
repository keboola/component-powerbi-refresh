import json
import os
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

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


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
