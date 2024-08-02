"""
Template Component main class.

"""

import json
import logging
import time
from datetime import datetime  # noqa
from typing import Union
import requests
import backoff

from kbc.result import KBCTableDef  # noqa
from kbc.result import ResultWriter  # noqa
from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException
from requests import RequestException

# configuration variables
KEY_DATASET = 'dataset_list'
KEY_WORKSPACE = 'workspace'

STATE_AUTH_ID = "auth_id"
STATE_REFRESH_TOKEN = "#refresh_token"
REQUIRED_PARAMETERS = []


class Component(ComponentBase):
    def __init__(self):
        super().__init__()

        self.dataset_array = None
        self.authorization = None
        self.oauth_token = None
        self.refresh_token = None
        self.validate_configuration_parameters(REQUIRED_PARAMETERS)

        parameters = self.configuration.parameters

        self.workspace = parameters.get("workspace")
        self.wait = parameters.get("wait", "No") == "Yes"
        self.timeout = time.time() + parameters.get("timeout", 7200)
        self.interval = parameters.get("interval")
        self.alldatasets = parameters.get("alldatasets", "No") == "Yes"

        self.success_list = []
        self.failed_list = []
        self.requestid_array = []

    def _client_init(self):
        self.authorization = self.configuration.config_data["authorization"]
        access_token, self.refresh_token = self.get_oauth_token()
        self.write_state_file({
                    STATE_REFRESH_TOKEN: self.refresh_token,
                    STATE_AUTH_ID: self.authorization.get("oauth_api", {}).get("credentials", {}).get("id", "")
                    })

        self.header = access_token

    def run(self):
        self._client_init()
        self.load_datasets()
        self.check_dataset_inputs()

        group_url = f"groups/{self.workspace}" if self.workspace else ""

        logging.info(f"Processing datasets: {self.dataset_array}")
        for dataset in self.dataset_array:
            dataset_id = dataset["dataset_input"]
            logging.info(f"Refreshing dataset {dataset_id}")
            response = self.refresh_dataset(group_url, dataset_id)
            if response:
                self.success_list.append(dataset_id)
                self.requestid_array.append([dataset_id, response.headers["RequestId"]])
            else:
                self.failed_list.append(dataset_id)

        if self.wait:
            logging.debug(f"Waiting for dataset refreshes to finish. Timeout: {self.timeout}")
            self.check_status(group_url)
        else:
            logging.info(f"List refreshed: {self.success_list}")

        if self.failed_list:
            raise UserException(f"Any of dataset refreshes finished with error. {self.failed_list}")

        logging.info("PowerBI Refresh finished")

    @property
    def header(self):
        return self.header

    @header.setter
    def header(self, access_token):
        self.header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}"
        }

    def load_datasets(self):
        """
        This exists for compatibility with the old configuration scheme that was refactored in KCOFAC-2294-refactor-ux.
        Returns:
            None
        """
        dataset_list = self.configuration.parameters.get("dataset_list")
        datasets = self.configuration.parameters.get("datasets")  # old field

        if not dataset_list:
            if not datasets:
                raise UserException(
                    "To refresh Power BI datasets, you must specify datasets in Configuration Parameters.")
        else:
            datasets = dataset_list

        if isinstance(datasets[0], str):
            self.dataset_array = [{"dataset_input": item} for item in datasets]
        elif isinstance(datasets[0], dict):
            self.dataset_array = datasets

    def get_oauth_token(self):
        """Returns access token and refresh token."""
        config = self.authorization

        if not config.get("oauth_api"):
            raise UserException("In order for the component to process PowerBI refresh, please authenticate.")

        credentials = config["oauth_api"]["credentials"]
        client_id = credentials["appKey"]
        client_secret = credentials["#appSecret"]
        encrypted_data = json.loads(credentials["#data"])
        refresh_token = self.get_state_file().get(STATE_REFRESH_TOKEN, [])
        auth_id = self.get_state_file().get(STATE_AUTH_ID, [])

        if not auth_id and refresh_token:  # TODO: remove after few weeks
            # prevents discarding saved refresh tokens due to the missing conf id in the state file
            logging.info("Refresh token loaded from state file")

        elif refresh_token and auth_id == credentials.get("id", ""):
            logging.info("Refresh token loaded from state file")

        else:
            refresh_token = encrypted_data["refresh_token"]
            logging.info("Refresh token loaded from authorization")

        url = "https://login.microsoftonline.com/common/oauth2/token"
        header = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "resource": "https://analysis.windows.net/powerbi/api",
            "refresh_token": refresh_token
        }

        r = requests.post(url, headers=header, data=payload)
        if r.status_code != 200:
            raise UserException(f"Unable to refresh access token. Status code: {r.status_code} "
                                f"Reason: {r.reason}, message: {r.json()}")

        r_json = r.json()
        logging.info(f"Access token expires in {r_json.get('expires_in', '')} seconds."
                     f"Refresh token expires in {r_json.get('refresh_token_expires_in', '')} seconds.")

        return r_json["access_token"], r_json["refresh_token"]

    @backoff.on_exception(backoff.expo, Exception, max_tries=3)
    def refresh_dataset(self, group_url, dataset) -> Union[requests.models.Response, bool]:
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets/{dataset}/refreshes"
        # https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group#limitations
        payload = {"notifyOption": "MailOnFailure"}

        def _refresh_dataset():
            r = requests.post(refresh_url, headers=self.header, data=payload)
            if r.status_code == 202:
                logging.info(f"Dataset {dataset} refresh accepted by PowerBI API.")
                return r
            msg = json.loads(r.text)
            logging.error(
                f"Failed to refresh dataset: error code: {msg['error']['code']} "
                f"message: {msg['error']['message']}")
            return False

        try:
            response = _refresh_dataset()
            return response
        except Exception as e:
            logging.error(f"Dataset refresh failed. Exception: {e}")
            return False

    def refresh_status(self, dataset_id, group_url):
        """
        Uses https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/get-refresh-history
        to get refresh history. Not available for Onedrive and probably Sharepoint data sources (returns 404).
        Args:
            dataset_id: str, id of the dataset
            group_url: str, workspace id

        Returns:
            response
        """
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets/{dataset_id}/refreshes"

        response = self._get_request(refresh_url)

        return response

    @backoff.on_exception(backoff.expo, RequestException, max_tries=3)
    def _get_request(self, url):
        response = requests.get(url=url, headers=self.header)

        if response.status_code == 403:
            try:
                error_message = response.json()
                if error_message.get('error', {}).get('code') == 'TokenExpired':
                    access_token, _ = self.get_oauth_token()
                    self.header = access_token
                    response = requests.get(url=url, headers=self.header)
            except ValueError:
                raise UserException(f"Request for url {url} failed with status code: {response.status_code}"
                                    f" and message: {response.text}")

        return response

    def process_status(self, request, request_list, success_list, running_list):
        if request.status_code != 200:
            raise UserException(f"Failed to refresh dataset with ID: {request_list[0]} "
                                f"with status code: {request.status_code} and message: "
                                f"{request.text}")

        selected_status = [f['status'] for f in request.json()['value'] if request_list[1] in f['requestId']]

        if not selected_status:
            logging.error(f"Refresh request has been successful but the component cannot obtain refresh "
                          f"status for dataset refresh with id {request_list[1]}")
            self.requestid_array.remove([request_list[0], request_list[1]])
            return

        status = selected_status[0]

        if status == "Completed":
            success_list.append(request_list[0])
            self.requestid_array.remove([request_list[0], request_list[1]])
        elif status == "Failed":
            self.failed_list.append(request_list[0])
            self.requestid_array.remove([request_list[0], request_list[1]])
            if not self.alldatasets:
                content = json.loads(request.content)
                raise UserException(f"Dataset {self.failed_list} finished with error "
                                    f"{content['value'][1]['serviceExceptionJson']}")
        elif status == "Disabled":
            logging.info(f"Dataset {request_list[0]} is disabled")
            self.requestid_array.remove([request_list[0], request_list[1]])
        elif status == "Unknown":
            running_list.append(request_list[0])
        else:
            raise UserException(f"Unknown error in dataset {request_list[0]}")

    def check_status(self, group_url) -> None:
        while self.requestid_array != [] and time.time() < self.timeout:
            running_list = []
            success_list = []
            for requestid in self.requestid_array:

                try:
                    request = self.refresh_status(requestid[0], group_url)
                except RequestException as e:
                    raise UserException(f"Refresh status check failed with exception: {e}")

                self.process_status(request, requestid, success_list, running_list)
                logging.info(f"Running: {running_list}")
                logging.info(f"Refreshed: {success_list}")
                logging.info(f"Failed to refresh: {self.failed_list}")
            if self.requestid_array:
                time.sleep(self.interval)

    def check_dataset_inputs(self) -> None:
        """
        Validates the dataset inputs.

        Raises:
            UserException: If the dataset configuration is missing or if any of the dataset IDs are empty.
        """
        if not self.dataset_array:
            raise UserException("Dataset configuration is missing. Please specify datasets.")

        for dataset in self.dataset_array:
            if not dataset["dataset_input"]:
                raise UserException("Dataset IDs cannot be empty. Please enter Dataset ID.")

    @sync_action("selectWorkspace")
    def get_workspaces(self):
        self._client_init()
        refresh_url = "https://api.powerbi.com/v1.0/myorg/groups"
        response = self._get_request(refresh_url)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise UserException(f"Error while fetching workspaces: {e}")

        workspaces = [{"label": val["name"], "value": val["id"]} for val in response.json().get("value")]

        # Adding the Default Workspace element
        default_workspace = {"label": "Default Workspace", "value": ""}
        workspaces.insert(0, default_workspace)

        return workspaces

    @sync_action("selectDataset")
    def get_datasets(self):
        self._client_init()
        group_url = f"groups/{self.workspace}" if self.workspace else ""
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets"
        response = self._get_request(refresh_url)

        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise UserException(f"Error while fetching datasets: {e}")

        return [{"label": val["name"], "value": val["id"]} for val in response.json().get("value")]


"""
        Main entrypoint
"""
if __name__ == "__main__":
    try:
        comp = Component()
        # this triggers the run method by default and is controlled by the configuration.action parameter
        comp.execute_action()
    except UserException as exc:
        logging.exception(exc)
        exit(1)
    except Exception as exc:
        logging.exception(exc)
        exit(2)
