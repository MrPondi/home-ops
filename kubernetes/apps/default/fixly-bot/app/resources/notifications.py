import asyncio
import json
import ssl
import uuid
from typing import Literal, Optional, Set
from urllib.parse import urlparse

import paho.mqtt.client as mqtt
from httpx import AsyncClient
from paho.mqtt.enums import CallbackAPIVersion

from auth import Auth


class NotificationsClient:
    def __init__(self, url: str, auth_service: Auth, httpclient: AsyncClient):
        if not url:
            raise ValueError("NotificationsClient requires a valid URL.")

        self.url = url
        parsed = urlparse(url)

        if not parsed.hostname:
            raise ValueError(f"Could not parse hostname from URL: {url}")

        self.host = parsed.hostname
        self.port = parsed.port or (
            443 if parsed.scheme in ["wss", "https", "mqtts"] else 80
        )
        self.use_tls = parsed.scheme in ["wss", "https", "mqtts"]
        self.transport: Literal["websockets", "tcp"] = (
            "websockets" if parsed.scheme in ["ws", "wss", "http", "https"] else "tcp"
        )
        self.ws_path = parsed.path if parsed.path else "/"

        self.auth_service = auth_service
        self.httpclient = httpclient

        self.client: Optional[mqtt.Client] = None
        self.user_id: Optional[str] = None

        self.subscribed_topics: Set[str] = set()
        self.pending_topics: Set[str] = set()

        # We start these as None. They will be initialized in `init()`
        self._ready_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def init(self) -> None:
        # Create the asyncio objects now that we are safely inside the running event loop
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._ready_event is None:
            self._ready_event = asyncio.Event()

        self.user_id = self.auth_service.getUserId()
        if not self.user_id:
            print("❌ Initialization terminated: user is not logged in.")
            return

        access_token = await self.auth_service.getAccessToken()
        if not access_token:
            print("❌ Failed to get access token.")
            return

        client_id = f"web-{self.user_id}-{uuid.uuid4()}"

        self.client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            transport=self.transport,
            protocol=mqtt.MQTTv311,
        )

        self.client.username_pw_set(username="JWT", password=access_token)

        if self.transport == "websockets":
            self.client.ws_set_options(
                path=self.ws_path, headers=dict(self.httpclient.headers.copy())
            )

        if self.use_tls:
            self.client.tls_set(cert_reqs=ssl.CERT_REQUIRED)

        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        self.client.connect(self.host, self.port, keepalive=10)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code == 0:
            # Safely set the event flag using the stored loop
            if self._loop and self._ready_event:
                self._loop.call_soon_threadsafe(self._ready_event.set)

            for topic in self.pending_topics:
                client.subscribe(topic, qos=1)
                self.subscribed_topics.add(topic)
            self.pending_topics.clear()
        elif reason_code == "Bad user name or password":
            if self._loop:
                asyncio.run_coroutine_threadsafe(self.force_reconnect(), self._loop)
        else:
            print(int(reason_code))
            print(f"❌ Connection failed. Reason code: {reason_code}")

    def _on_disconnect(
        self, client, userdata, disconnect_flags, reason_code, properties=None
    ):
        print(f"⚠️ Disconnected from MQTT broker. Reason code: {reason_code}")
        if self._ready_event:
            self._ready_event.clear()

        if self._loop:
            asyncio.run_coroutine_threadsafe(self.force_reconnect(), self._loop)


    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            tooltip = payload.get("tooltip", {})
            if payload.get("action") == "service_request-new":
                print(
                    f"New request with customer {tooltip.get('title').strip().capitalize()}."
                )
                if self._loop:
                    request_id = tooltip.get("requestId")

                    if request_id:
                        from chat import Chat

                        chat_session = Chat(
                            config=self.auth_service.config,
                            chat_client=self,
                            httpclient=self.httpclient,
                            request_id=str(request_id),
                        )

                        asyncio.run_coroutine_threadsafe(
                            chat_session.main(), self._loop
                        )
            elif payload.get("action") == "service_request-canceled":
                print(
                    f"Request with customer {payload.get('subject').strip().capitalize()} was canceled."
                )
            elif (
                payload.get("action") == "sendNewMessagesAggregatedTooltip"
                and tooltip.get("title") == "Odpisz zlecającym"
            ):
                print("Someone opened fixly on their browser")
        except Exception as e:
            print(f"\n❓ [Raw Message Error]: {msg.payload} | Error: {e}")

    async def force_reconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()

        self.pending_topics.update(self.subscribed_topics)
        self.subscribed_topics.clear()

        await self.init()

    async def subscribe(self, topic: str):
        # If init hasn't been called or hasn't connected yet, queue it.
        if not self._ready_event or not self._ready_event.is_set():
            self.pending_topics.add(topic)
            return

        # It's ready, so we wait just to be mathematically safe.
        await self._ready_event.wait()

        if not self.client:
            return

        if topic not in self.subscribed_topics:
            self.client.subscribe(topic, qos=1)
            self.subscribed_topics.add(topic)

    async def unsubscribe(self, topic: str):
        if not self._ready_event:
            return

        await self._ready_event.wait()

        if not self.client:
            return

        if topic in self.subscribed_topics:
            self.client.unsubscribe(topic)
            self.subscribed_topics.remove(topic)

    async def publish(self, topic: str, content: dict):
        if not self._ready_event:
            raise RuntimeError("You must call await client.init() before publishing.")

        await self._ready_event.wait()

        if not self.client:
            raise RuntimeError("Client is not initialized")

        payload = json.dumps(content)
        self.client.publish(topic, payload, qos=1)

    def generate_notification_topic_key(self) -> str:
        if not self.user_id:
            raise ValueError("User ID not available yet. Make sure init() is called.")
        return f"web-notifications/{self.user_id}"

    def destroy(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.client = None

        if self._ready_event:
            self._ready_event.clear()
