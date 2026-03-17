'''
Created on 12. 11. 2018

@author: esner
'''
import unittest
import mock
import os
from unittest.mock import patch, MagicMock
from freezegun import freeze_time

from component import Component, TooManyRequestsError, RATE_LIMIT_DEFAULT_WAIT


class TestComponent(unittest.TestCase):

    # set global time to 2010-10-10 - affects functions like datetime.now()
    @freeze_time("2010-10-10")
    # set KBC_DATADIR env to non-existing dir
    @mock.patch.dict(os.environ, {'KBC_DATADIR': './non-existing-dir'})
    def test_run_no_cfg_fails(self):
        with self.assertRaises(ValueError):
            comp = Component()
            comp.run()


class TestTooManyRequestsError(unittest.TestCase):

    def test_exception_message(self):
        err = TooManyRequestsError(retry_after=30)
        self.assertEqual(err.retry_after, 30)
        self.assertIn("429", str(err))
        self.assertIn("30", str(err))

    def test_exception_default(self):
        err = TooManyRequestsError()
        self.assertIsNone(err.retry_after)


class TestGetRetryAfter(unittest.TestCase):

    def test_retry_after_header_present(self):
        response = MagicMock()
        response.headers = {"Retry-After": "45"}
        result = Component._get_retry_after(response)
        self.assertEqual(result, 45)

    def test_retry_after_header_missing(self):
        response = MagicMock()
        response.headers = {}
        result = Component._get_retry_after(response)
        self.assertEqual(result, RATE_LIMIT_DEFAULT_WAIT)

    def test_retry_after_header_invalid(self):
        response = MagicMock()
        response.headers = {"Retry-After": "not-a-number"}
        result = Component._get_retry_after(response)
        self.assertEqual(result, RATE_LIMIT_DEFAULT_WAIT)

    def test_retry_after_custom_default(self):
        response = MagicMock()
        response.headers = {}
        result = Component._get_retry_after(response, default=120)
        self.assertEqual(result, 120)


class TestCheckRateLimit(unittest.TestCase):

    @patch('component.time.sleep')
    def test_raises_on_429(self, mock_sleep):
        """Test that _check_rate_limit raises TooManyRequestsError on 429 response."""
        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "30"}

        comp = Component.__new__(Component)

        with self.assertRaises(TooManyRequestsError) as ctx:
            comp._check_rate_limit(response)

        self.assertEqual(ctx.exception.retry_after, 30)
        mock_sleep.assert_called_once_with(30)

    @patch('component.time.sleep')
    def test_uses_default_wait(self, mock_sleep):
        """Test that _check_rate_limit uses default wait when Retry-After is missing."""
        response = MagicMock()
        response.status_code = 429
        response.headers = {}

        comp = Component.__new__(Component)

        with self.assertRaises(TooManyRequestsError):
            comp._check_rate_limit(response)

        mock_sleep.assert_called_once_with(RATE_LIMIT_DEFAULT_WAIT)

    @patch('component.time.sleep')
    def test_noop_on_200(self, mock_sleep):
        """Test that _check_rate_limit does nothing for non-429 responses."""
        response = MagicMock()
        response.status_code = 200
        response.headers = {}

        comp = Component.__new__(Component)
        comp._check_rate_limit(response)

        mock_sleep.assert_not_called()

    @patch('component.time.sleep')
    def test_noop_on_500(self, mock_sleep):
        """Test that _check_rate_limit does nothing for 500 responses."""
        response = MagicMock()
        response.status_code = 500
        response.headers = {}

        comp = Component.__new__(Component)
        comp._check_rate_limit(response)

        mock_sleep.assert_not_called()


class TestRefreshDatasetRateLimit(unittest.TestCase):

    @patch('component.time.sleep')
    @patch('component.requests.post')
    def test_retries_on_429(self, mock_post, mock_sleep):
        """Test that refresh_dataset retries when it receives a 429 response."""
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "5"}

        response_202 = MagicMock()
        response_202.status_code = 202
        response_202.headers = {"RequestId": "test-request-id"}

        mock_post.side_effect = [response_429, response_202]

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

        result = comp.refresh_dataset("groups/test-workspace", "test-dataset")

        self.assertEqual(result, response_202)
        self.assertEqual(mock_post.call_count, 2)

    @patch('component.time.sleep')
    @patch('component.requests.post')
    def test_returns_false_on_other_errors(self, mock_post, mock_sleep):
        """Test that refresh_dataset returns False for non-429 error responses."""
        response_400 = MagicMock()
        response_400.status_code = 400
        response_400.headers = {}
        response_400.text = '{"error": {"code": "BadRequest", "message": "Invalid request"}}'

        mock_post.return_value = response_400

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

        result = comp.refresh_dataset("groups/test-workspace", "test-dataset")

        self.assertFalse(result)
        self.assertEqual(mock_post.call_count, 1)

    @patch('component.time.sleep')
    @patch('component.requests.post')
    def test_success_on_202(self, mock_post, mock_sleep):
        """Test that refresh_dataset returns the response on 202."""
        response_202 = MagicMock()
        response_202.status_code = 202
        response_202.headers = {"RequestId": "test-request-id"}

        mock_post.return_value = response_202

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

        result = comp.refresh_dataset("groups/test-workspace", "test-dataset")

        self.assertEqual(result, response_202)
        mock_sleep.assert_not_called()


class TestGetRequestRateLimit(unittest.TestCase):

    @patch('component.time.sleep')
    @patch('component.requests.get')
    def test_retries_on_429(self, mock_get, mock_sleep):
        """Test that _get_request retries when it receives a 429 response."""
        response_429 = MagicMock()
        response_429.status_code = 429
        response_429.headers = {"Retry-After": "10"}

        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.headers = {}

        mock_get.side_effect = [response_429, response_200]

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

        result = comp._get_request("https://api.powerbi.com/v1.0/myorg/test")

        self.assertEqual(result, response_200)
        self.assertEqual(mock_get.call_count, 2)

    @patch('component.time.sleep')
    @patch('component.requests.get')
    def test_success_on_200(self, mock_get, mock_sleep):
        """Test that _get_request returns response directly on 200."""
        response_200 = MagicMock()
        response_200.status_code = 200
        response_200.headers = {}

        mock_get.return_value = response_200

        comp = Component.__new__(Component)
        comp._header = {"Authorization": "Bearer test-token", "Content-Type": "application/json"}

        result = comp._get_request("https://api.powerbi.com/v1.0/myorg/test")

        self.assertEqual(result, response_200)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
