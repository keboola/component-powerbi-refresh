The main purpose of 'PowerBI Refresh' application is to refresh the configured datasets within a PowerBI Workspace.
Be aware! Each 'PowerBI Refresh' application's configuration can only work with one PowerBI Workspace, meaning that if you want to refresh PowerBI datasets from another PowerBI Workspaces, you will have to create a new 'PowerBI Refresh' configuration to send "refresh" requests to the PowerBI Workspace.

## Parameters

1. PowerBI Workspace
    - The PowerBI Workspace where the user wants to refresh their dataset
    - Please leave this blank if the user is exporting the dataset into the signed in account's "My Workspace"

2. PowerBI Datasets
    - IDs of the PowerBI Datasets within the configured workspace the user wish to refresh