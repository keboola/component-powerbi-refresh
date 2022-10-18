
=============

Refreshing PowerBI's datasets

The main purpose of 'PowerBI Refresh' application is to refresh the configured datasets within a PowerBI Workspace. Be aware! Each 'PowerBI Refresh' application's configuration can only work with one PowerBI Workspace, meaning that if you want to refresh PowerBI datasets from another PowerBI Workspaces, you will have to create a new 'PowerBI Refresh' configuration to send "refresh" requests to the PowerBI Workspace.

**Table of contents:**

[TOC]

Functionality notes
===================

Prerequisites
=============

- oauth2 Authorization
- ID of the Dataset

Supported endpoints
===================

If you need more endpoints, please submit your request to
[ideas.keboola.com](https://ideas.keboola.com/)

Configuration
=============

##PowerBI Refresh Configuration
 - PowerBI Workspace (workspace) - [REQ] Please leave this blank if user is trying to export into the signed-in account's workspace
 - PowerBI Datasets (datasets) - [REQ] Please enter the 'ID' of the dataset. Note: Not the 'Name' of the dataset
 - Wait for end (wait) - [OPT] Check dataset refresh status after refresh request
 - Wait for all datasets (alldatasets) - [OPT] End job with error if any of datasets finish with failed status (Works only when "Wait for end" is Yes)
 - Interval (interval) - [OPT] Status check interval (Works only when "Wait for end" is Yes)
 - Timeout (timeout) - [OPT] Status check timeout (Works only when "Wait for end" is Yes)




Sample Configuration
=============
```json
{
   "parameters": {
      "datasets": [
         {
            "dataset_input": "xxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxx"
         }
      ],
      "workspace": "",
      "wait": true,
      "timeout": 3600,
      "interval": 30,
      "alldatasets": false
   }
}
```

Output
======

Log output

Development
-----------

If required, change local data folder (the `CUSTOM_FOLDER` placeholder) path to your custom path in
the `docker-compose.yml` file:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clone this repository, init the workspace and run the component with following command:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose build
docker-compose run --rm dev
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Run the test suite and lint check using this command:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose run --rm test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration
===========

For information about deployment and integration with KBC, please refer to the
[deployment section of developers documentation](https://developers.keboola.com/extend/component/deployment/)