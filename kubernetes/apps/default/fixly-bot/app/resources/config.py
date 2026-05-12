from pathlib import Path


class Config:
    api_url: str = "https://api.fixly.pl"
    chat_url: str = "wss://chat.fixly.pl"
    web_notifications_url: str = "wss://web-notify.fixly.pl"
    data_dir: Path = Path("/data")
