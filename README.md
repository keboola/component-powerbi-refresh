Refreshing PowerBI's datasets
=============

The primary purpose of the 'PowerBI Refresh' application is to refresh the configured datasets within a PowerBI workspace. 

**Important:** Each **PowerBI Refresh** configuration can only work with a single PowerBI workspace. If you need to refresh datasets in multiple PowerBI workspaces, you must create a separate configuration for each workspace.

**Table of contents:**

[TOC]

Functionality Notes
===================
- Detailed information about the refresh status can be found in the **Datasource/Semantic Model** under **Refresh > Refresh History > Show**.

- The credentials used for the datasource connection in Power BI Desktop are not transferred to Power BI Online when publishing the report. You must set them again in the **Data Source/Semantic Model** under **File > Settings > Data source credentials**.

Prerequisites
=============

- OAuth2 authorization
- Dataset ID

Supported Endpoints
===================

If you need additional endpoints, please submit your request at [ideas.keboola.com](https://ideas.keboola.com/).

PowerBI Refresh Configuration
=============

 - **PowerBI workspace** (`workspace`) - [REQ] Leave this blank if exporting to the signed-in account's workspace.
 - **PowerBI datasets** (`datasets`) - [REQ] Enter the **ID** of the dataset (not the dataset name).
 - **Wait for end** (`wait`) - [OPT] Check the dataset's refresh status after sending the refresh request.
 - **Wait for all datasets** (`alldatasets`) - [OPT] End the job with an error if any dataset fails to refresh (only works when "Wait for end" is set to `Yes`).
 - **Interval** (`interval`) - [OPT] Status check interval (only works when "Wait for end" is set to `Yes`).
 - **Timeout** (`timeout`) - [OPT] Status check timeout (only works when "Wait for end" is `Yes`).

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

The application generates **log output** for monitoring refresh activities.

Development
-----------

If needed, modify the local data folder path (the `CUSTOM_FOLDER` placeholder) in
the `docker-compose.yml` file:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    volumes:
      - ./:/code
      - ./CUSTOM_FOLDER:/data
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Clone this repository, initialize the workspace, and run the component using the following commands:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose build
docker-compose run --rm dev
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To run the test suite and perform a lint check, use:

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
docker-compose run --rm test
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integration
===========

For information about deployment and integration with KBC, please refer to the
[deployment section of developers documentation](https://developers.keboola.com/extend/component/deployment/)
