import asyncio
import json
import os

from httpx import AsyncClient

# Import the class blueprints directly, NOT from dependencies.py
from auth import Auth
from config import Config
from httpauth import HttpAuth
from notifications import NotificationsClient


async def main():
    # 1. Initialize synchronous configs
    config = Config()

    # 2. Create the AsyncClient inside an 'async with' context manager.
    # This automatically safely closes the client when the block ends!
    async with AsyncClient(
        headers={
            "api-version": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        }
    ) as httpclient:
        # 3. Instantiate all services (Dependency Injection)
        auth_service = Auth(config, httpclient)

        web_notifications_client = NotificationsClient(
            config.web_notifications_url, auth_service, httpclient
        )

        # 4. Load initial credentials
        token_file = config.data_dir / "token.json"

        creds = {
            "userId": os.getenv("USERID", "0"),
            "isProvider": True,
        }

        # Create empty token file if missing
        if not token_file.exists():
            token_file.write_text("{}")

        # Load and merge token data
        try:
            token_data = json.loads(token_file.read_text())

            if not isinstance(token_data, dict):
                raise ValueError("token.json must contain a JSON object")

            creds.update(token_data)

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {token_file}: {e}") from e

        # 5. Set up the state
        auth_service.storeCredentials(creds)

        session_id = os.getenv("SESSIONID", "")
        httpclient.cookies.set("fixly_session_id", session_id, ".fixly.pl")

        # Attach custom httpx.Auth interceptor
        httpclient.auth = HttpAuth(auth_service)

        # Refresh the token if needed
        await auth_service.getAccessToken()

        # 6. Start the actual logic
        if auth_service.isLoggedIn():
            await web_notifications_client.init()

            topic = web_notifications_client.generate_notification_topic_key()
            await web_notifications_client.subscribe(topic)

            print("Bot is running. Listening for messages...")

            try:
                await asyncio.Event().wait()

            except asyncio.CancelledError:
                print("KeyboardInterrupt detected. Shutting down gracefully...")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
            finally:
                print("Disconnecting MQTT...")
                web_notifications_client.destroy()
        else:
            print("User is not logged in. Could not start bot.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
