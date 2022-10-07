"""
Template Component main class.

"""

import logging
import logging_gelf.handlers
import logging_gelf.formatters
import os
import sys
import json
from datetime import datetime  # noqa
import requests
import time

from kbc.result import KBCTableDef  # noqa
from kbc.result import ResultWriter  # noqa
from keboola.component.exceptions import UserException
from keboola.component.base import ComponentBase

# configuration variables
KEY_DATASET = 'datasets'
KEY_WORKSPACE = 'workspace'

REQUIRED_PARAMETERS = [
    KEY_DATASET,
    KEY_WORKSPACE
]

# Default Table Output Destination
DEFAULT_TABLE_SOURCE = "/data/in/tables/"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)-8s : [line:%(lineno)3s] %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S")

if 'KBC_LOGGER_ADDR' in os.environ and 'KBC_LOGGER_PORT' in os.environ:
    logger = logging.getLogger()
    logging_gelf_handler = logging_gelf.handlers.GELFTCPSocketHandler(
        host=os.getenv('KBC_LOGGER_ADDR'), port=int(os.getenv('KBC_LOGGER_PORT')))
    logging_gelf_handler.setFormatter(
        logging_gelf.formatters.GELFFormatter(null_character=True))
    logger.addHandler(logging_gelf_handler)

    # remove default logging to stdout
    logger.removeHandler(logger.handlers[0])


class Component(ComponentBase):

    def __init__(self):
        super().__init__()
        self.oauth_token = None
        self.validate_configuration_parameters(REQUIRED_PARAMETERS)

        self.workspace = self.configuration.parameters.get("workspace")
        self.dataset_array = self.configuration.parameters.get("datasets")
        self.wait = self.configuration.parameters.get("wait")
        self.timeout = time.time() + self.configuration.parameters.get("timeout")
        self.interval = self.configuration.parameters.get("interval")
        self.alldatasets = self.configuration.parameters.get("alldatasets")

    def get_oauth_token(self, config):
        """
        Extracting OAuth Token out of Authorization
        """

        data = config["oauth_api"]["credentials"]
        data_encrypted = json.loads(
            config["oauth_api"]["credentials"]["#data"])
        client_id = data["appKey"]
        client_secret = data["#appSecret"]
        refresh_token = data_encrypted["refresh_token"]

        url = "https://login.microsoftonline.com/common/oauth2/token"
        header = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "resource": "https://analysis.windows.net/powerbi/api",
            "refresh_token": refresh_token
        }

        attempts = 0
        while attempts < 3:
            try:
                response = requests.post(
                    url=url, headers=header, data=payload)
                if response.status_code == 200:
                    break
                elif attempts < 2:
                    wait_time = 2 ** (attempts + 4)
                    time.sleep(wait_time)
                    attempts += 1
                    continue
                else:
                    raise UserException(
                        "Unable to refresh access token. {} {}".format(
                            response.status_code, response.reason))
            except Exception:
                raise UserException(
                    "Try later or reset the account authorization.")

        data_r = response.json()
        return data_r["access_token"]

    def refresh_dataset(self, group_url, dataset):
        """
        Refreshing the entered dataset
        """

        refresh_url = "https://api.powerbi.com/v1.0/myorg/{0}datasets/{1}/refreshes".format(
            group_url, dataset)

        header = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.oauth_token)
        }
        payload = {
            "notifyOption": "MailOnFailure"
        }

        attempts = 0
        while attempts < 3:
            try:
                response = requests.post(
                    url=refresh_url, headers=header, data=payload)
                if response.status_code == 202:
                    break
                elif attempts < 2:
                    wait_time = 2 ** (attempts + 4)
                    time.sleep(wait_time)
                    attempts += 1
                    continue
                else:
                    raise UserException(f"Reached maximum attempts when refreshing dataset: {response.text}")
            except Exception as e:
                raise UserException(f"Dataset refresh execution failed.")
        logging.info(f"Response we got when trying to refresh dataset: {response.text}")
        return response

    def refresh_status(self, group_url, dataset):

        refresh_url = "https://api.powerbi.com/v1.0/myorg/{0}datasets/{1}/refreshes".format(
            group_url, dataset)

        header = {
            "Content-Type": "application/json",
            "Authorization": "Bearer {}".format(self.oauth_token)
        }

        response = requests.get(
            url=refresh_url, headers=header)

        return response

    def run(self):
        """
        Main execution code
        """

        # Activate when oauth in KBC is ready
        # Get Authorization Token
        authorization = self.configuration.config_data["authorization"]
        self.oauth_token = self.get_oauth_token(authorization)

        # Handling input error
        if len(self.dataset_array) == 0:
            raise UserException("Dataset configuration is missing. Please specify datasets.")

        # handling empty dataset inputs
        invalid_dataset = False
        for dataset in self.dataset_array:
            if dataset["dataset_input"] == '':
                invalid_dataset = True
        if invalid_dataset:
            raise UserException("Dataset IDs cannot be empty. Please enter Dataset ID.")

        if self.workspace == "":
            group_url = ""
        else:
            group_url = "groups/{}/".format(self.workspace)

        success_list = []
        failed_list = []
        requestid_array = []
        for dataset in self.dataset_array:
            dataset_name = dataset["dataset_input"]
            does_it_work = False
            does_it_work = self.refresh_dataset(group_url, dataset_name)
            if does_it_work:
                success_list.append(dataset_name)
                requestid_array.append([dataset_name, does_it_work.headers["RequestId"]])
            else:
                failed_list.append(dataset_name)

        if self.wait:
            while requestid_array != [] and time.time() < self.timeout:
                running_list = []
                success_list = []
                for requestid in requestid_array:
                    status = self.refresh_status(group_url, requestid[0])
                    if status.status_code == 200:

                        selected_status = [f['status'] for f in status.json()['value']
                                           if requestid[1] in f['requestId']]

                        if selected_status[0] == "Completed":
                            success_list.append(requestid[0])
                            requestid_array.remove([requestid[0], requestid[1]])
                        elif selected_status[0] == "Failed":
                            failed_list.append(requestid[0])
                            requestid_array.remove([requestid[0], requestid[1]])
                            if self.alldatasets == "No":
                                logging.error(f"Dataset {failed_list} finished with error")
                                sys.exit(1)
                        elif selected_status[0] == "Disabled":
                            logging.info(f"Dataset {requestid[0]} is disabled")
                            requestid_array.remove([requestid[0], requestid[1]])
                        elif selected_status[0] == "Unknown":
                            running_list.append(requestid[0])
                        else:
                            logging.error(f"Unknown error in dataset {requestid[0]}")
                            sys.exit(1)
                    elif status.status_code == 403:
                        self.oauth_token = self.get_oauth_token(authorization)
                    else:
                        raise UserException("Error Message: {status.text}")
                    logging.info(f"List running: {running_list}")
                    logging.info(f"List refreshed: {success_list}")
                    logging.info(f"List failed to refresh: {failed_list}")
                if requestid_array:
                    time.sleep(self.interval)
        else:
            logging.info(f"List refreshed: {success_list}")
        if failed_list:
            raise UserException("Any of dataset refreshes finished with error.")

        logging.info("PowerBI Refresh finished")


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
