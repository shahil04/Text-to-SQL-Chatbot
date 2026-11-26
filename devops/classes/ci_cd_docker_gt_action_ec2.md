https://github.com/shahil04/url_shortener_project_cicd

docker-deploy.yml
name: Text-to-SQL CI + Deploy in aws

on:
  # Build and publish the Docker image for pushes to any branch.
  push:
  pull_request:
    branches: ["master"]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    env:
      IMAGE_NAME: shahil004/text_to_sql

    steps:
      - name: Checkout Repository
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Check Python Syntax
        run: python -m compileall -q app main.py demo_sqllite.py

      - name: Validate SQLite Database
        run: |
          python -c "import sqlite3; c=sqlite3.connect('uber.db'); result=c.execute('PRAGMA integrity_check').fetchone()[0]; c.close(); print('Database:', result); raise SystemExit(result != 'ok')"

      - name: Build Docker Image
        run: docker build -t "$IMAGE_NAME:v1.0" .

      - name: Log in to Docker Hub
        if: github.event_name != 'pull_request'
        uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_PASSWORD }}

      - name: Push Docker Image
        if: github.event_name != 'pull_request'
        run: docker push "$IMAGE_NAME:v1.0"

      - name: Deploy to Amazon EC2
        if: github.event_name != 'pull_request' && github.ref == 'refs/heads/master'
        uses: appleboy/ssh-action@v1.2.2
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_KEY }}
          script: |
            # Download the published image from Docker Hub.
            docker pull ${{ env.IMAGE_NAME }}:v1.0
            # Stop and remove the previous container if it exists.
            docker stop text-to-sql-chatbot || true
            docker rm text-to-sql-chatbot || true
            # Start the new container and keep port 8501 private to the EC2 host.
            docker run -d \
              --restart=always \
              -p 8501:8501 \
              --name text-to-sql-chatbot \
              ${{ env.IMAGE_NAME }}:v1.0



======================================
1. login
- docker login --> in cmd session

2. Tag your local image
- docker tag <local-image>:<local-tag> <username>/<repository>:<tag>
- eg: docker tag my-app:latest johndoe/my-app:v1.0

3. push the image 
- docker push <username>/<repository>:<tag>

========================================
### after publish pull this docker image in ec2 and run without any project file

After the GitHub Action pushes the image to Docker Hub, SSH into the EC2
instance and run these commands. The image contains the application and its
runtime dependencies, so you do not need to clone the repository or copy
project files to EC2.

```bash
# Download the published image from Docker Hub.
docker pull shahil004/text_to_sql:v1.0

# Stop the old container; ignore the error if it is not running.
docker stop text-to-sql-chatbot 2>/dev/null || true
# Remove the old container; ignore the error if it does not exist.
docker rm text-to-sql-chatbot 2>/dev/null || true

# Remove the current container:bash if exits
sudo docker rm -f text-to-sql-chatbot
# Start the new container in the background and restart it automatically.
docker run -d \
  --restart=always \
  -p 8501:8501 \
  --name text-to-sql-chatbot \
  shahil004/text_to_sql:v1.0

# simple commands for it
or docker run -it -p 8501:8501 shahil004/text_to_sql:v1.0

# Check whether the container is running.
docker ps --filter name=text-to-sql-chatbot
# Show the latest container logs for troubleshooting.
docker logs --tail 50 text-to-sql-chatbot
```

The Docker Hub repository must be public, or the EC2 instance must log in to
Docker Hub before `docker pull`. The app listens on EC2 localhost port `8501`;
use an authenticated HTTPS reverse proxy for remote access rather than
exposing the unauthenticated Streamlit port directly.

===================
### next step github to docker automations

1. In GitHub, open **Settings → Secrets and variables → Actions** and add:
   - `DOCKER_USERNAME` — your Docker Hub username.
   - `DOCKER_PASSWORD` — a Docker Hub access token.
2. Create `.github/workflows/docker-push.yml` in your repository. GitHub Actions
   detects and runs workflow files stored in this folder.
3. Add this workflow. It builds the image on every branch push and publishes it
   to Docker Hub. Pull requests to `master` build the image without publishing.

   ```yaml
   name: Build and Push Docker Image

   # Run on pushes to any branch, pull requests targeting master, or manual dispatch.
   on:
     push:
     pull_request:
       branches: ["master"]
     workflow_dispatch:

   # Allow the workflow to read repository contents only.
   permissions:
     contents: read

   # Build the container on GitHub's hosted Ubuntu runner.
   jobs:
     docker:
       runs-on: ubuntu-latest
       steps:
         # Check out the source code, including the Dockerfile.
         - name: Check out repository
           uses: actions/checkout@v6

         # Prepare Docker Buildx for the image build.
         - name: Set up Docker Buildx
           uses: docker/setup-buildx-action@v3

         # Authenticate only when the event is allowed to publish an image.
         - name: Log in to Docker Hub
           if: github.event_name != 'pull_request'
           uses: docker/login-action@v3
           with:
             username: ${{ secrets.DOCKER_USERNAME }}
             password: ${{ secrets.DOCKER_PASSWORD }}

         # Build for every event; publish on pushes and manual runs, not pull requests.
         - name: Build and push image
           uses: docker/build-push-action@v6
           with:
             context: .
             push: ${{ github.event_name != 'pull_request' }}
             # Use the Docker Hub repository and version tag.
             tags: shahil004/text_to_sql:v1.0
   ```

4. Commit and push your changes. The workflow builds from the repository's
   `Dockerfile` and publishes `shahil004/text_to_sql:v1.0` to Docker Hub.

