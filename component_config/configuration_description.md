The main purpose of 'PowerBI Refresh' application is to refresh the configured datasets within a PowerBI Workspace.
Be aware! Each 'PowerBI Refresh' application's configuration can only work with one PowerBI Workspace, meaning that if you want to refresh PowerBI datasets from another PowerBI Workspaces, you will have to create a new 'PowerBI Refresh' configuration to send "refresh" requests to the PowerBI Workspace.

## Parameters

1. PowerBI Workspace
    - The PowerBI Workspace where the user wants to refresh their dataset
    - Please leave this blank if the user is exporting the dataset into the signed in account's "My Workspace"

2. PowerBI Datasets
    - IDs of the PowerBI Datasets within the configured workspace the user wish to refresh
	
3. Wait for end
	- Check dataset refresh status after refresh request
	
4. Wait for all datasets
	- End job with error if any of datasets finish with failed status (Works only when "Wait for end" is Yes)
	
5. Interval
	- Status check interval (Works only when "Wait for end" is Yes)
	
6. Timeout
	- Status check timeout (Works only when "Wait for end" is Yes) - maximum is 2 hours!