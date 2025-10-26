# Deploying with Terraform

This directory contains Terraform configuration to deploy k0sNgin to Google Cloud Platform (GCP) using Cloud Run.

## Prerequisites

1. **GCP Account**: You need a GCP project (in this case, `k0sngin`)
2. **gcloud CLI**: Install the Google Cloud SDK
3. **Terraform**: Install Terraform
4. **Docker**: Install Docker for building and pushing images

## Deployment Options

This project supports two deployment approaches:

### Option 1: Manual Deployment (Development)

Manually build and push the Docker image, then deploy via Terraform. See [Manual Deployment](#manual-deployment) below.

### Option 2: Automated CI/CD (Recommended for Production)

Automate the entire process using GitHub Actions. See [CI/CD Deployment](#cicd-deployment) below.

## Manual Deployment {#manual-deployment}

This approach is useful for learning, testing changes, or manual deployments.

### Initial Setup

#### 1. Authenticate with Google Cloud

```bash
# Login to GCP with your credentials
gcloud auth application-default login
```

#### 2. Enable Required APIs

The following APIs need to be enabled in your GCP project:

```bash
# Enable Cloud Run API
gcloud services enable run.googleapis.com

# Enable Cloud Build API
gcloud services enable cloudbuild.googleapis.com

# Configure Docker to authenticate with GCR
gcloud auth configure-docker
```

Alternatively, you can enable all APIs through the Google Cloud Console:
- [Cloud Run API](https://console.developers.google.com/apis/api/run.googleapis.com/overview?project=k0sngin)
- [Cloud Build API](https://console.developers.google.com/apis/api/cloudbuild.googleapis.com/overview?project=k0sngin)

#### 3. Build and Push Docker Image

From the project root directory:

```bash
# In a subshell...
(

# Change directory to the repository root
cd "$( git rev-parse --show-toplevel )"

# Build the Docker image
docker build -t gcr.io/k0sngin/k0sninja .

# Push the image to Google Container Registry
docker push gcr.io/k0sngin/k0sninja:latest

)
```

## Deployment

### 1. Initialize Terraform

Navigate to the terraform directory and initialize:

```bash
cd "$( git rev-parse --show-toplevel)"/infra/terraform
terraform init
```

### 2. Plan and Apply

Review the changes:

```bash
terraform plan
```

Deploy the infrastructure:

```bash
terraform apply -auto-approve
```


### 3. Get Service URL

After deployment, retrieve the service URL:

```bash
terraform output service_url
```

## Outputs

The Terraform configuration provides the following outputs:

- `service_url`: The public URL of your Cloud Run service
- `service_name`: The name of the Cloud Run service
- `service_location`: The region where the service is deployed

View all outputs:

```bash
terraform output
```

_Example: `curl`ing the website:_

```bash
curl "$( terraform output -raw service_url )"
```

## Updating the Service

### Rebuilding the Docker Image

After making changes to the application:

```bash
# From the project root directory

# Rebuild the image
docker build -t gcr.io/k0sngin/k0sninja .

# Push the updated image
docker push gcr.io/k0sngin/k0sninja:latest

# Update the Cloud Run service
cd infra/terraform
terraform apply -auto-approve
```

Note: If you're using a different image tag (not `latest`), you'll need to update the image reference in `main.tf` before applying.

## CI/CD Deployment {#cicd-deployment}

For automated deployments, use GitHub Actions. This eliminates the need for manual Docker builds and pushes.

### GitHub Actions Setup

1. **Create a GCP Service Account**:

```bash
# Create service account
gcloud iam service-accounts create github-actions \
    --display-name="GitHub Actions Deployment"

# Grant necessary permissions
gcloud projects add-iam-policy-binding k0sngin \
    --member="serviceAccount:github-actions@k0sngin.iam.gserviceaccount.com" \
    --role="roles/storage.admin"
gcloud projects add-iam-policy-binding k0sngin \
    --member="serviceAccount:github-actions@k0sngin.iam.gserviceaccount.com" \
    --role="roles/run.admin"
gcloud projects add-iam-policy-binding k0sngin \
    --member="serviceAccount:github-actions@k0sngin.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin"
gcloud projects add-iam-policy-binding k0sngin \
    --member="serviceAccount:github-actions@k0sngin.iam.gserviceaccount.com" \
    --role="roles/container.developer"

# Create and download key
gcloud iam service-accounts keys create github-key.json \
    --iam-account=github-actions@k0sngin.iam.gserviceaccount.com
```

2. **Add GitHub Secret**:

In your GitHub repository settings:
- Go to Settings → Secrets and variables → Actions
- Add a new secret named `GCP_SA_KEY`
- Paste the contents of `github-key.json`
- Remove the local key file: `rm github-key.json`

3. **Deploy**:

The workflow (`.github/workflows/deploy.yaml`) will:
- Trigger on pushes to `main`
- Build and push the Docker image to GCR
- Deploy via Terraform

### Using Cloud Build (Alternative)

Alternatively, you can use Google Cloud Build:

```bash
# Build and deploy
gcloud builds submit --config cloudbuild.yaml

# Or set up a trigger for automatic builds on push to main
gcloud builds triggers create github \
    --repo-name=k0sNgin \
    --repo-owner=<your-org> \
    --branch-pattern="^main$" \
    --build-config=cloudbuild.yaml
```

## Architecture

This Terraform configuration creates:

1. **Cloud Run Service** (`k0sninja`):
   - Location: `us-west1`
   - Container port: `8000`
   - Public access: All users (via IAM member)

2. **IAM Binding**:
   - Allows public access (no authentication required)

## Troubleshooting

### Error: Cloud Run Admin API not enabled

```bash
gcloud services enable run.googleapis.com
```

### Error: Cloud Build API not enabled

```bash
gcloud services enable cloudbuild.googleapis.com
```

### Error: Permission denied when pushing to GCR

```bash
gcloud auth configure-docker
```

### View Cloud Run logs

```bash
gcloud run services logs read k0sninja --region=us-west1
```

## Costs

Cloud Run charges only for:
- Request processing time
- Number of requests

The service is configured to scale to zero when not in use, minimizing costs.

## Security Considerations

Currently, the service is configured with public access (`allUsers`). For production deployments:

1. Remove or restrict the IAM member in `main.tf`
2. Implement authentication using Cloud IAM or a custom identity provider
3. Consider using Cloud Armor for DDoS protection

## Clean Up

To destroy all resources:

```bash
cd infra/terraform
terraform destroy
```

This will delete the Cloud Run service and associated IAM bindings, but will NOT delete the Docker images from Container Registry.
