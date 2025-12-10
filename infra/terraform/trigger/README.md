# Cloud Build Trigger for GitHub

This Terraform configuration sets up a Cloud Build trigger that automatically builds your application on every push to the `main` branch.

## Prerequisites

1. **Enable Required APIs**:
   ```bash
   gcloud services enable cloudbuild.googleapis.com
   ```

## Setup Instructions

1. **Install GitHub App**:
   - Go to [Google Cloud Console > Cloud Build > Connections](https://console.cloud.google.com/cloud-build/connections)
   - Click "Create Connection" and select "GitHub"
   - Follow the prompts to install the GitHub App
   - Note the **Installation ID** from the connection details (it will be a number like `12345678`)

2. **Configure Terraform**:
   Create a `terraform.tfvars` file:
   ```hcl
   github_app_installation_id = "YOUR_INSTALLATION_ID"
   ```
   Replace `YOUR_INSTALLATION_ID` with the installation ID from step 1.

3. **Apply Configuration**:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```

## What This Creates

1. **GitHub Connection** (`google_cloudbuildv2_connection`):
   - Connects your GCP project to GitHub
   - Uses either GitHub App or OAuth token for authentication

2. **Repository Connection** (`google_cloudbuildv2_repository`):
   - Links the specific GitHub repository (`k0s/k0sNgin`) to Cloud Build

3. **Build Trigger** (`google_cloudbuild_trigger`):
   - Automatically triggers builds on pushes to `main` branch
   - Uses `cloudbuild.yaml` from the repository root
   - Passes `SHORT_SHA` as `_SHORT_SHA` substitution variable

## Verification

After applying, verify the trigger was created:

```bash
gcloud builds triggers list --region=us-west1
```

You should see `main-branch-trigger` in the list.

## Testing

Push a change to the `main` branch and check the Cloud Build console to see the build trigger automatically.

## Troubleshooting

### Error: "Connection not found"
- Ensure the GitHub connection is created before the repository connection
- Check that the connection name matches

### Error: "Repository not found"
- Verify the repository URI is correct: `https://github.com/k0s/k0sNgin.git`
- Ensure the GitHub App has access to the repository

### Error: "Permission denied"
- Ensure the GitHub App is installed on the repository
- Check that the installation ID is correct
