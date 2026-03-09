"""Test a deployed Agent Engine."""

import os
import asyncio
import vertexai
from vertexai import agent_engines

PROJECT_ID = os.getenv("PROJECT_ID", "[your-project-id]")
LOCATION = os.getenv("REGION", "us-central1")
STAGING_BUCKET = os.getenv("STAGING_BUCKET", f"gs://{PROJECT_ID}_cloudbuild")
RESOURCE_NAME = os.getenv("RESOURCE_NAME", "[your-resource-name]")

print("Initializing Vertex AI SDK...")
vertexai.init(
    project=PROJECT_ID,
    location=LOCATION,
    staging_bucket=STAGING_BUCKET,
)


async def main():
    print(f"Connecting to Agent Engine: {RESOURCE_NAME}")
    try:
        remote_app = agent_engines.get(RESOURCE_NAME)

        print("Creating session...")
        session = await remote_app.async_create_session(user_id="test_user")
        print(f"Session created: {session}")

        query = "What is the current weather in Seoul, South Korea?"
        print(f"\nSending query: '{query}'")

        async for event in remote_app.async_stream_query(
            user_id="test_user",
            session_id=session["id"],
            message=query,
        ):
            print(event)

    except Exception as e:
        print(f"Test failed: {e}")


if __name__ == "__main__":
    asyncio.run(main())
