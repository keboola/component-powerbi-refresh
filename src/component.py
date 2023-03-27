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

# configuration variables
KEY_DATASET = 'datasets'
KEY_WORKSPACE = 'workspace'

REQUIRED_PARAMETERS = [
    KEY_DATASET,
    KEY_WORKSPACE
]


class Component(ComponentBase):
    def __init__(self):
        super().__init__()
        self.dataset_array = None
        self.authorization = None
        self.oauth_token = None
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

        self.authorization = self.configuration.config_data["authorization"]
        self.oauth_token = self.get_oauth_token()

        self.header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.oauth_token}"
        }

    def run(self):
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
            self.check_status(group_url)
        else:
            logging.info(f"List refreshed: {self.success_list}")

        if self.failed_list:
            raise UserException(f"Any of dataset refreshes finished with error. {self.failed_list}")

        logging.info("PowerBI Refresh finished")

    @sync_action("selectDataset")
    def get_datasets(self):
        group_url = f"groups/{self.workspace}" if self.workspace else ""
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets"
        response = requests.get(refresh_url, headers=self.header)
        return [{"label": val["name"], "value": val["id"]} for val in response.json().get("value")]

    def load_datasets(self):
        """
        This exists for compatibility with the old configuration scheme.
        Returns:
            None
        """
        datasets = self.configuration.parameters.get("datasets")
        if isinstance(datasets[0], str):
            self.dataset_array = [{"dataset_input": item} for item in datasets]
        elif isinstance(datasets[0], dict):
            self.dataset_array = datasets

    def get_oauth_token(self):
        """
        Extracting OAuth Token from Authorization
        """
        config = self.authorization
        credentials = config["oauth_api"]["credentials"]
        client_id = credentials["appKey"]
        client_secret = credentials["#appSecret"]
        encrypted_data = json.loads(credentials["#data"])
        refresh_token = encrypted_data["refresh_token"]

        url = "https://login.microsoftonline.com/common/oauth2/token"
        header = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "resource": "https://analysis.windows.net/powerbi/api",
            "refresh_token": refresh_token
        }

        @backoff.on_exception(backoff.expo, Exception, max_tries=3)
        def send_request():
            r = requests.post(url, headers=header, data=payload)
            if r.status_code != 200:
                raise UserException(f"Unable to refresh access token. Status code: {r.status_code}"
                                    f"Reason: {r.reason}, message: {r.json()}")
            return r.json()["access_token"]

        return send_request()

    def refresh_dataset(self, group_url, dataset) -> Union[requests.models.Response, bool]:
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets/{dataset}/refreshes"
        # https://learn.microsoft.com/en-us/rest/api/power-bi/datasets/refresh-dataset-in-group#limitations
        payload = {"notifyOption": "MailOnFailure"}

        @backoff.on_exception(backoff.expo, Exception, max_tries=3)
        def refresh_dataset_backoff():
            r = requests.post(refresh_url, headers=self.header, data=payload)
            if r.status_code == 202:
                logging.info(f"Dataset {dataset} refresh accepted by PowerBI API.")
                return r
            logging.info(r.text)
            try:
                msg = json.loads(r.text)
                logging.error(
                    f"Failed to refresh dataset: error code: {msg['error']['code']} "
                    f"message: {msg['error']['message']}")
            except json.JSONDecodeError:
                logging.error(f"Error : {r} Error txt : {r.text}")
            return False

        try:
            response = refresh_dataset_backoff()
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
        response = requests.get(
            url=refresh_url, headers=self.header)
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
                request = self.refresh_status(requestid[0], group_url)
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
