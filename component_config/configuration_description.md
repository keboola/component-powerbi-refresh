The primary purpose of the Power BI Refresh application is to refresh the configured datasets within a Power BI workspace.

**Important:** Each Power BI Refresh configuration can only work with a single Power BI workspace. If you need to refresh datasets in multiple Power BI workspaces, you must create a separate configuration for each workspace.

## Parameters

1. **PowerBI workspace**
    - The PowerBI workspace where the user wants to refresh their dataset.
    - Leave this blank if exporting the dataset to the signed-in account's **"My Workspace"**.

2. **PowerBI datasets**
    - The IDs of the PowerBI datasets within the configured workspace that the user wants to refresh.
	
3. **Wait for end**
	- Check the dataset refresh status after sending the refresh request.
	
4. **Wait for all datasets**
	- End the job with an error if any dataset finishes with a failed status (only works when "Wait for end" is set to `Yes`).
	
5. **Interval**
	- The interval (in seconds) for checking refresh statuses (only works when "Wait for end" is set to `Yes`).
	
6. **Timeout**
	- The timeout duration (in seconds) for checking refresh statuses. Maximum allowed timeout: 2 hours.
