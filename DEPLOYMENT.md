# Deployment Guide for GCP

This guide provides step-by-step instructions to deploy the Aegis AI application on Google Cloud Platform, following the architecture plan (Backend on Cloud Run, Frontend on Firebase Hosting).

## Prerequisites

1.  **Google Cloud Project**: Create or select a project in the [Google Cloud Console](https://console.cloud.google.com/).
2.  **Enable APIs**: Ensure the **Cloud Run API** and **Cloud Build API** are enabled.
3.  **Install CLIs**:
    *   [Google Cloud CLI (`gcloud`)](https://cloud.google.com/sdk/docs/install)
    *   [Firebase CLI (`firebase-tools`)](https://firebase.google.com/docs/cli)
4.  **Authenticate**:
    ```bash
    gcloud auth login
    gcloud config set project YOUR_PROJECT_ID
    firebase login
    ```

---

## 1. Deploy the Backend (Google Cloud Run)

We have already created a `Dockerfile` and `.dockerignore` in the `backend/` directory for you.

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```

2.  **Deploy to Cloud Run:**
    Run the following command. Replace `YOUR_GEMINI_API_KEY` with your actual Gemini API key.
    ```bash
    gcloud run deploy aegis-backend \
      --source . \
      --port 8080 \
      --allow-unauthenticated \
      --region us-central1 \
      --set-env-vars="GEMINI_API_KEY=YOUR_GEMINI_API_KEY"
    ```
    *(Note: You can omit the `--set-env-vars` flag if you prefer to set it manually in the Cloud Console Native UI later).*

3.  **Note the deployed URL**: 
    After a successful deployment, the terminal will output a **Service URL** (e.g., `https://aegis-backend-xyz.run.app`). Keep this URL handy for the next step.

---

## 2. Deploy the Frontend (Firebase Hosting)

We have already updated `App.tsx` to read the API URL dynamically and created a `firebase.json` file.

1.  **Initialize Firebase (if not already done):**
    Ensure your Firebase project is linked to your Google Cloud project.
    ```bash
    cd ../frontend
    firebase init project
    ```
    *Select your existing Google Cloud Project.*

2.  **Set the Backend URL:**
    Create a `.env.production` file in the `frontend` directory and add your backend's API endpoint URL.
    ```bash
    echo "VITE_API_URL=https://<YOUR_BACKEND_URL>/api/v1/process-intent" > .env.production
    ```
    *(Replace `<YOUR_BACKEND_URL>` with the URL you got from step 1).*

3.  **Build the Production Bundle:**
    ```bash
    npm run build
    ```

4.  **Deploy to Firebase Hosting:**
    ```bash
    firebase deploy --only hosting
    ```

Your full application is now live on Google Cloud Platform!
