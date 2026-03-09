"""Deploy Gemini Agent to Vertex AI Agent Engine.

Usage:
    # Create new Agent Engine
    python scripts/deploy_agent_engine.py --project <PROJECT_ID>

    # Update existing Agent Engine
    python scripts/deploy_agent_engine.py --project <PROJECT_ID> --update <RESOURCE_NAME>
"""

import argparse
import os
import sys


def parse_args():
    parser = argparse.ArgumentParser(
        description="Deploy Gemini Agent to Vertex AI Agent Engine",
    )
    parser.add_argument(
        "--project", required=True, help="GCP project ID",
    )
    parser.add_argument(
        "--update", metavar="RESOURCE_NAME",
        help="Update existing Agent Engine (pass full resource name)",
    )
    parser.add_argument(
        "--region", default="us-central1", help="GCP region (default: us-central1)",
    )
    parser.add_argument(
        "--staging-bucket", default=None,
        help="GCS staging bucket (default: gs://<PROJECT_ID>_cloudbuild)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    PROJECT_ID = args.project
    LOCATION = args.region
    STAGING_BUCKET = args.staging_bucket or f"gs://{PROJECT_ID}_cloudbuild"

    os.environ["PROJECT_ID"] = PROJECT_ID
    os.environ["GOOGLE_CLOUD_PROJECT"] = PROJECT_ID

    print(f"Initializing Vertex AI SDK...")
    print(f"  Project:        {PROJECT_ID}")
    print(f"  Location:       {LOCATION}")
    print(f"  Staging Bucket: {STAGING_BUCKET}")

    import vertexai
    from vertexai import agent_engines

    vertexai.init(
        project=PROJECT_ID,
        location=LOCATION,
        staging_bucket=STAGING_BUCKET,
    )

    # ---------------------------------------------------------------
    # Agent Engine uses service account auth (not API key).
    # No env vars needed for authentication.
    # ---------------------------------------------------------------
    env_vars = {}

    # ---------------------------------------------------------------
    # Prepare agent for deployment
    # ---------------------------------------------------------------
    import gemini_agent.agent

    print("Preparing agent for deployment...")
    print(f"  Agent Model: {gemini_agent.agent.MODEL_NAME}")

    app = agent_engines.AdkApp(
        agent=gemini_agent.agent.root_agent,
        enable_tracing=True,
    )

    SERVICE_ACCOUNT = f"agent-engine-sa@{PROJECT_ID}.iam.gserviceaccount.com"
    print(f"  Service Account: {SERVICE_ACCOUNT}")

    REQUIREMENTS = [
        "google-cloud-aiplatform[adk,agent_engines]>=1.128.0",
        "google-adk>=1.15.0",
        "google-cloud-secret-manager>=2.16.0",
        "nest-asyncio>=1.5.0",
        "python-dotenv>=1.0.0",
        "google-api-python-client>=2.100.0",
        "google-auth>=2.20.0",
        "google-auth-oauthlib>=1.0.0",
    ]

    RESOURCE_LIMITS = {"cpu": "2", "memory": "4Gi"}
    print(f"  Resource Limits: {RESOURCE_LIMITS}")

    # ---------------------------------------------------------------
    # Deploy / Update
    # ---------------------------------------------------------------
    try:
        if args.update:
            print(f"\nUpdating existing Agent Engine: {args.update}")
            remote_app = agent_engines.update(
                resource_name=args.update,
                agent_engine=app,
                requirements=REQUIREMENTS,
                extra_packages=["./gemini_agent"],
                display_name="Gemini Agent",
                env_vars=env_vars,
                resource_limits=RESOURCE_LIMITS,
            )
            print("Update finished!")
        else:
            print("\nCreating new Agent Engine...")
            remote_app = agent_engines.create(
                agent_engine=app,
                requirements=REQUIREMENTS,
                extra_packages=["./gemini_agent"],
                display_name="Gemini Agent",
                service_account=SERVICE_ACCOUNT,
                env_vars=env_vars,
                resource_limits=RESOURCE_LIMITS,
            )
            print("Deployment finished!")

        print(f"Resource Name: {remote_app.resource_name}")

    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
