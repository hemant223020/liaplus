# CI/CD Pipeline Implementation

## Pipeline Overview

The CI/CD pipeline implemented using GitHub Actions follows industry best practices to automate the building, testing, and deployment of our application to Azure App Service. The pipeline is divided into separate stages to ensure each part of the process is handled correctly.

### Pipeline Stages

1. **Build Stage**
   - Checks out the code repository
   - Sets up Python environment
   - Installs dependencies from requirements.txt
   - Caches dependencies to speed up future builds

2. **Test Stage**
   - Runs linting using flake8 to ensure code quality
   - Executes unit tests using pytest
   - Ensures the application can be imported and initialized
   - Fails fast if critical issues are identified

3. **Package Stage**
   - Creates a ZIP archive of the application code
   - Uploads the archive as a build artifact
   - Makes the artifact available for deployment

4. **Deploy Stage**
   - Runs only on the main branch or manual dispatch
   - Downloads the build artifact
   - Deploys to Azure App Service using the Azure webapps-deploy action
   - Sets up environment variables for the application

5. **Verification Stage**
   - Performs a health check of the deployed application
   - Verifies the application is accessible and responding correctly
   - Provides deployment URL in the GitHub Actions UI

## Environment Variables and Secrets Management

### Types of Secrets Used

1. **Azure Publish Profile**
   - Stored as `AZURE_WEBAPP_PUBLISH_PROFILE` in GitHub Secrets
   - Contains credentials to deploy to Azure App Service
   - Generated from Azure Portal or CLI with `az webapp deployment list-publishing-credentials`

2. **Application Secrets**
   - Database connection strings
   - API keys for external services
   - Authentication tokens
   - Stored as GitHub Secrets and injected during deployment

### Implementation

```yaml
# Example secret reference in GitHub Actions
with:
  publish-profile: ${{ secrets.AZURE_WEBAPP_PUBLISH_PROFILE }}
```

### Secret Creation Process

1. In Azure:
   ```bash
   # Export the publish profile
   az webapp deployment list-publishing-credentials \
     --name liaplus-webapp \
     --resource-group liaplus-devops-rg \
     --xml > publish_profile.xml
   ```

2. In GitHub Repository:
   - Navigate to Settings > Secrets and Variables > Actions
   - Create New Repository Secret
   - Name: AZURE_WEBAPP_PUBLISH_PROFILE
   - Value: [Contents of publish_profile.xml]

### Application Configuration

For application secrets and configuration:

1. Setting environment variables in Azure:
   ```bash
   # Set configuration values
   az webapp config appsettings set \
     --name liaplus-webapp \
     --resource-group liaplus-devops-rg \
     --settings DB_CONNECTION_STRING="value" API_KEY="value"
   ```

2. Accessing in Python application:
   ```python
   import os
   db_connection = os.environ.get('DB_CONNECTION_STRING')
   api_key = os.environ.get('API_KEY')
   ```

## Security Best Practices

1. **Principle of Least Privilege**
   - Service principals and publish profiles have only the permissions needed
   - Time-limited tokens for deployments when possible

2. **Secret Rotation**
   - Regular rotation of deployment credentials
   - Automated rotation using Microsoft Identity Platform

3. **Environment Separation**
   - Different deployment targets for Dev, QA, and Production
   - Environment-specific secrets and configurations

4. **Audit Trail**
   - All deployments logged in GitHub Actions history
   - Azure Activity Log captures all resource modifications

5. **Approval Gates**
   - Pull request approval required before merging to main
   - Optional manual approval step before production deployment

## Continuous Integration vs. Continuous Deployment

This pipeline implements Continuous Deployment (CD) rather than just Continuous Integration (CI) because:

- It automatically deploys to production when changes are merged to the main branch
- It includes post-deployment verification
- It manages the entire process from code commit to production deployment

For more controlled environments, the pipeline could be modified to implement Continuous Delivery instead, requiring manual approval before the deployment stage.
