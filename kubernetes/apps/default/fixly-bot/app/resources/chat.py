import asyncio
import random

from httpx import AsyncClient

from notifications import NotificationsClient


class Chat:
    def __init__(
        self, chat_client: NotificationsClient, httpclient: AsyncClient, request_id: str
    ):
        self.chat_client = chat_client
        self.httpclient = httpclient
        self.request_id = request_id

    async def main(self):
        """
        The main orchestrator for this specific Chat instance.
        This runs entirely in the background, independent of the global listener.
        """
        try:
            time_to_wait = random.randint(1, 3) * 60
            print(
                f"[Chat {self.request_id}] Initializing chat process... (in {time_to_wait} seconds)"
            )

            await asyncio.sleep(time_to_wait)  # Simulate some startup delay

            success = await self.start_conversation()

            if not success:
                print(
                    f"[Chat {self.request_id}] Failed to start conversation. Aborting."
                )
                return

            print(f"[Chat {self.request_id}] Conversation started successfully!")

            # --- FUTURE: Call other self methods here! ---
            # await self.connect_chat_specific_mqtt()
            # await self.send_ai_greeting()
            # await self.check_google_calendar()
            # ---------------------------------------------

        except Exception as e:
            print(f"[Chat {self.request_id}] Error in chat main loop: {e}")

    async def start_conversation(self, offerPrice: int | None = None) -> bool:
        variables: dict[str, str | int] = {"requestId": self.request_id}
        if offerPrice is not None:
            variables["offerPrice"] = offerPrice

        response = await self.httpclient.post(
            "https://api.fixly.pl/graphql?name=startConversationMutation",
            json={
                "operationName": "startConversationMutation",
                "variables": variables,
                "query": "mutation startConversationMutation($requestId: ID!, $offerPrice: Int) {\n  startConversation(requestId: $requestId, offerPrice: $offerPrice)\n}",
            },
            headers={
                "Referer": f"https://fixly.pl/mojefixly/oferta/{self.request_id}",
            },
        )
        response.raise_for_status()

        if response.json().get("data", {}).get("startConversation"):
            return True
        return False
