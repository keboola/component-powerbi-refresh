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
 - **Tenant ID** (`tenant_id`) - [OPT] Leave blank unless you authorized with an external (B2B guest) account. By default the token is requested from the `common` authority, which resolves to the signed-in user's *home* tenant; for a guest account that is not the tenant hosting the workspace, so its workspaces and datasets are not visible and refreshes fail. Set this to the Microsoft Entra tenant ID (GUID) or domain name of the tenant hosting the workspace. Enter the bare identifier, not a full URL.

### Using a B2B guest account

If the workspace lives in a tenant you are only a guest in, set **Tenant ID** to that tenant's identifier.

Set it **before** using *Load workspaces* and *Reload dataset names*. Those pickers enumerate whichever tenant the token points at, so with the field still blank they list your own home tenant's workspaces — and they do so without any error, which is what makes this failure mode hard to spot. If you already picked a workspace or dataset before setting **Tenant ID**, reload both lists and select again.

If refreshes still fail with a token error immediately after setting it, re-run the OAuth authorization for the configuration so a fresh token is issued for that tenant.

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
