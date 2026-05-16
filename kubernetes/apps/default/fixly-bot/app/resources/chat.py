import asyncio
import random

from httpx import AsyncClient

from config import Config
from notifications import NotificationsClient


class Chat:
    def __init__(
        self,
        config: Config,
        chat_client: NotificationsClient,
        httpclient: AsyncClient,
        request_id: str,
    ):
        self.config = config
        self.chat_client = chat_client
        self.httpclient = httpclient
        self.request_id = request_id

    async def main(self):
        """
        The main orchestrator for this specific Chat instance.
        This runs entirely in the background, independent of the global listener.
        """
        try:
            # details = await self.get_request_details()
            # if not details:
            #     print(
            #         f"[Chat {self.request_id}] No details found for request. aborting checks"
            #     )
            # else:
            #     print(
            #         f"[Chat {self.request_id}] Request details: \nDotyczy: {details.get('8080', {}).get('answer')}\nProjekt: {details.get('8081', {}).get('answer')}\nElementy: {details.get('8082', {}).get('answer')}\nPowierzchnia: {details.get('8083', {}).get('answer')}\nKiedy usługa powinna być wykonana?: {details.get('service-schedule', {}).get('answer')}"
            #     )

            time_to_wait = random.randint(1, 3) * 60
            print(
                f"[Chat {self.request_id}] Initializing chat process... (in {time_to_wait} seconds)"
            )

            await asyncio.sleep(time_to_wait)  # Simulate some human delay

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
            f"{self.config.api_url}/graphql?name=startConversationMutation",
            json={
                "operationName": "startConversationMutation",
                "variables": variables,
                "query": "mutation startConversationMutation($requestId: ID!, $offerPrice: Int) {\\n  startConversation(requestId: $requestId, offerPrice: $offerPrice)\\n}",
            },
            headers={
                "Referer": f"https://fixly.pl/mojefixly/oferta/{self.request_id}",
            },
        )
        print(f"[Chat {self.request_id}] startConversation response: {response.text}")
        response.raise_for_status()

        if response.json().get("data", {}).get("startConversation"):
            return True
        return False

    async def get_request_details(self) -> dict:

        response = await self.httpclient.post(
            f"{self.config.api_url}/graphql?name=ProviderRequest",
            json={
                "operationName": "ProviderRequest",
                "variables": {"requestId": self.request_id},
                "query": "fragment ProviderVas on Vas {\\n  id\\n  slug\\n  type\\n  name\\n  shortName\\n  price\\n  discount\\n  salePrice\\n  promoDays\\n  description\\n  features\\n  imageUrl\\n  expirationDays\\n  paymentOptions {\\n    id\\n    slug\\n    name\\n    description\\n    imageUrl\\n    url\\n    __typename\\n  }\\n  prices {\\n    oneTime {\\n      price\\n      discount\\n      salePrice\\n      __typename\\n    }\\n    subscription {\\n      price\\n      discount\\n      salePrice\\n      __typename\\n    }\\n    __typename\\n  }\\n  __typename\\n}\\n\\nquery ProviderRequest($requestId: ID!) {\\n  me {\\n    id\\n    phone\\n    email\\n    emailVerified\\n    provider {\\n      id\\n      onboardingStep\\n      vases {\\n        isAvailable\\n        isEnabled\\n        vas {\\n          ...ProviderVas\\n          __typename\\n        }\\n        __typename\\n      }\\n      account {\\n        pointsBalance\\n        __typename\\n      }\\n      __typename\\n    }\\n    __typename\\n  }\\n  providerRequestByIdWithExpired(id: $requestId) {\\n    id\\n    status\\n    lat\\n    lon\\n    schedule\\n    address\\n    distance\\n    createdAt\\n    expired\\n    expiresAt\\n    muted\\n    askedForReview\\n    isDirectRequest\\n    isPayWithFixly\\n    freeSlots\\n    busySlots\\n    seen\\n    canAskForReview\\n    price\\n    priceLabel\\n    fake\\n    features\\n    phonePrice\\n    iconUrl\\n    title\\n    state\\n    isPayWithFixly\\n    pwf {\\n      price\\n      state\\n      verificationInfo {\\n        state\\n        __typename\\n      }\\n      __typename\\n    }\\n    quoteState {\\n      value\\n      changedAt\\n      canChangeToDone\\n      text\\n      url\\n      actionText\\n      actionDoneText\\n      canPerformAction\\n      __typename\\n    }\\n    subscription {\\n      isAvailable\\n      isEnabled\\n      isSoldOut\\n      canBeProlonged\\n      enabledAt\\n      expiresAt\\n      vas {\\n        ...ProviderVas\\n        __typename\\n      }\\n      __typename\\n    }\\n    askForReview {\\n      isAsked\\n      suggestedL4Categories {\\n        id\\n        name\\n        __typename\\n      }\\n      __typename\\n    }\\n    lastMessage {\\n      type\\n      content\\n      __typename\\n    }\\n    mapUrls {\\n      web\\n      __typename\\n    }\\n    review {\\n      id\\n      createdAt\\n      rating\\n      text\\n      __typename\\n    }\\n    lastOffer {\\n      price\\n      units\\n      unitsLabel\\n      unitsShortLabel\\n      __typename\\n    }\\n    category {\\n      name\\n      id\\n      __typename\\n    }\\n    l4Category {\\n      id\\n      slug\\n      name\\n      isPayWithFixly\\n      l2 {\\n        id\\n        slug\\n        __typename\\n      }\\n      l3 {\\n        id\\n        slug\\n        __typename\\n      }\\n      __typename\\n    }\\n    user {\\n      id\\n      lastName\\n      firstName\\n      avatarUrl\\n      phone\\n      maskedPhone\\n      hasPhone\\n      __typename\\n    }\\n    details {\\n      id\\n      answer\\n      originalAnswer\\n      question\\n      questionId\\n      files\\n      documentFiles {\\n        name\\n        type\\n        url\\n        __typename\\n      }\\n      __typename\\n    }\\n    appliedProviders {\\n      id\\n      featured\\n      newcomer: isNewcomer\\n      isPayWithFixlyRegistered\\n      avatar\\n      feedbackCount\\n      feedbackClientsCount\\n      rating\\n      review {\\n        id\\n        __typename\\n      }\\n      __typename\\n    }\\n    label {\\n      type\\n      text\\n      ctaText\\n      isLocked\\n      __typename\\n    }\\n    badges {\\n      id\\n      type\\n      title\\n      __typename\\n    }\\n    __typename\\n  }\\n}",
            },
            headers={
                "Referer": f"https://fixly.pl/mojefixly/oferta/{self.request_id}",
            },
        )
        print(f"[Chat {self.request_id}] ProviderRequest response: {response.text}")
        response.raise_for_status()

        details = (
            response.json()
            .get("data", {})
            .get("providerRequestByIdWithExpired", {})
            .get("details", {})
        )
        return {detail["questionId"]: detail for detail in details} if details else {}
