'''
Template Component main class.

'''

import logging
import logging_gelf.handlers
import logging_gelf.formatters
import os
import sys
import json
from datetime import datetime  # noqa
import requests

from kbc.env_handler import KBCEnvHandler
from kbc.result import KBCTableDef  # noqa
from kbc.result import ResultWriter  # noqa


# configuration variables
KEY_DATASET = 'datasets'
KEY_WORKSPACE = 'workspace'

MANDATORY_PARS = [
    KEY_DATASET,
    KEY_WORKSPACE
]
MANDATORY_IMAGE_PARS = []

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


APP_VERSION = '0.0.2'


class Component(KBCEnvHandler):

    def __init__(self, debug=False):
        KBCEnvHandler.__init__(self, MANDATORY_PARS)
        logging.info('Running version %s', APP_VERSION)
        logging.info('Loading configuration...')

        try:
            self.validate_config()
            self.validate_image_parameters(MANDATORY_IMAGE_PARS)
        except ValueError as e:
            logging.error(e)
            exit(1)

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

        response = requests.post(
            url=url, headers=header, data=payload)

        if response.status_code != 200:
            logging.error(
                "Unable to refresh access token. Please reset the account authorization.")
            sys.exit(1)

        data_r = response.json()
        token = data_r["access_token"]

        return token

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

        try:
            response = requests.post(
                url=refresh_url, headers=header, data=payload)

            if response.status_code != 202:
                # logging.error("{0} : {1} refresh failed".format(
                #   response.status_code, dataset))
                # return False
                logging.error("Failed to refresh dataset: {}".format(dataset))
                logging.error("Please validate your dataset inputs.")
                sys.exit(1)
        except Exception:
            # logging.error("{0} refresh failed: {1}".format(dataset, e))
            logging.error("Failed to refresh dataset: {}".format(dataset))
            logging.error("Please validate your dataset inputs.")
            # return False
            sys.exit(1)

        return True

    def run(self):
        '''
        Main execution code
        '''

        # Activate when oauth in KBC is ready
        # Get Authorization Token
        authorization = self.configuration.get_authorization()
        self.oauth_token = self.get_oauth_token(authorization)

        # Configuration parameters
        params = self.cfg_params  # noqa
        # Error handler, if there is nothing in the configuration
        if params == {}:
            logging.error(
                "There are no inputs in the configurations. Please configure.")
            sys.exit(1)
        workspace = params["workspace"]
        dataset_array = params["datasets"]
        # Handling input error
        if len(dataset_array) == 0:
            logging.error(
                "Dataset configuration is missing. Please specify datasets.")
            sys.exit(1)

        # handling empty dataset inputs
        invalid_dataset = False
        for dataset in dataset_array:
            if dataset["dataset_input"] == '':
                invalid_dataset = True
        if invalid_dataset:
            logging.error(
                "Dataset IDs cannot be empty. Please enter Dataset ID.")
            sys.exit(1)

        if workspace == "":
            group_url = ""
        else:
            group_url = "groups/{}/".format(workspace)

        success_list = []
        failed_list = []
        for dataset in dataset_array:
            dataset_name = dataset["dataset_input"]
            does_it_work = self.refresh_dataset(group_url, dataset_name)
            if does_it_work:
                success_list.append(dataset_name)
            else:
                failed_list.append(dataset_name)

        logging.info("List refreshed: {}".format(success_list))
        # logging.info("List failed to refresh: {}".format(failed_list))

        logging.info("PowerBI Refresh finished")


"""
        Main entrypoint
"""
if __name__ == "__main__":
    if len(sys.argv) > 1:
        debug = sys.argv[1]
    else:
        debug = True
    comp = Component(debug)
    comp.run()
