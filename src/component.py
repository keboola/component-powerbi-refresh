"""
Template Component main class.

"""

import json
import logging
import time
from datetime import datetime  # noqa
from typing import Union

import requests
from kbc.result import KBCTableDef  # noqa
from kbc.result import ResultWriter  # noqa
from keboola.component.base import ComponentBase, sync_action
from keboola.component.exceptions import UserException

# configuration variables
KEY_DATASET = 'datasets'
KEY_WORKSPACE = 'workspace'
KEY_ASYNC_DATASET = 'selected_datasets'

REQUIRED_PARAMETERS = [
    KEY_WORKSPACE
]

# Default Table Output Destination
DEFAULT_TABLE_SOURCE = "/data/in/tables/"


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

    def run(self):
        self.oauth_token = self.get_oauth_token()

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
    def select_dataset(self):
        self.oauth_token = self.get_oauth_token()
        return self.get_datasets()

    def get_datasets(self):
        group_url = f"groups/{self.workspace}" if self.workspace else ""
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets"
        header = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.oauth_token}"
        }
        response = requests.get(refresh_url, headers=header)
        return [{"label": val["name"], "value": val["id"]} for val in response.json().get("value")]

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

        for attempts in range(3):
            try:
                response = requests.post(url, headers=header, data=payload)
                if response.status_code == 200:
                    break
                elif attempts < 2:
                    time.sleep(2 ** (attempts + 4))
                else:
                    raise UserException(
                        "Unable to refresh access token. {} {}".format(response.status_code, response.reason))
            except Exception:
                raise UserException("Try later or reset the account authorization.")

        return response.json()["access_token"]

    def refresh_dataset(self, group_url, dataset) -> Union[requests.models.Response, bool]:
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}/datasets/{dataset}/refreshes"
        header = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.oauth_token)
        }
        payload = {
            "retryCount": 0
        }
        response = False

        for attempts in range(3):
            try:
                response = requests.post(refresh_url, headers=header, data=payload)
                if response.status_code == 202:
                    return response
                if attempts < 2:
                    time.sleep(2 ** (attempts + 4))
                    continue
                else:
                    msg = json.loads(response.text)
                    logging.error(
                        f"Failed to refresh dataset: error code: {msg['error']['code']} "
                        f"message: {msg['error']['message']}")
                    return False
            except Exception as e:
                logging.error(f"Dataset refresh failed. Exception: {e}")
                return False
        return response

    def refresh_status(self, request_id, group_url):
        refresh_url = f"https://api.powerbi.com/v1.0/myorg/{group_url}datasets/{request_id[0]}/refreshes" \
                      f"/{request_id[1]}"
        header = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.oauth_token)
        }
        response = requests.get(
            url=refresh_url, headers=header)
        return response

    def check_status(self, group_url) -> None:
        while self.requestid_array != [] and time.time() < self.timeout:
            running_list = []
            success_list = []
            for requestid in self.requestid_array:
                request = self.refresh_status(requestid, group_url)
                if request.status_code == 200:

                    selected_status = [f['status'] for f in request.json()['value']
                                       if requestid[1] in f['requestId']]

                    if selected_status[0] == "Completed":
                        success_list.append(requestid[0])
                        self.requestid_array.remove([requestid[0], requestid[1]])
                    elif selected_status[0] == "Failed":
                        self.failed_list.append(requestid[0])
                        self.requestid_array.remove([requestid[0], requestid[1]])
                        if not self.alldatasets:
                            content = json.loads(request.content)
                            raise UserException(f"Dataset {self.failed_list} finished"
                                                f" with error {content['value'][1]['serviceExceptionJson']}")

                    elif selected_status[0] == "Disabled":
                        logging.info(f"Dataset {requestid[0]} is disabled")
                        self.requestid_array.remove([requestid[0], requestid[1]])
                    elif selected_status[0] == "Unknown":
                        running_list.append(requestid[0])
                    else:
                        raise UserException(f"Unknown error in dataset {requestid[0]}")
                elif request.status_code == 403:
                    self.oauth_token = self.get_oauth_token()
                else:
                    raise UserException(f"Error Message: {request.text}")
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
        parameters = self.configuration.parameters
        if len(parameters.get("datasets")[0].get("dataset_input")) == 0:
            self.dataset_array = [{"dataset_input": item} for item in parameters.get(KEY_ASYNC_DATASET)]
        else:
            self.dataset_array = parameters.get("datasets")

        if not self.dataset_array:
            raise UserException("Dataset configuration is missing. Please specify datasets.")


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
