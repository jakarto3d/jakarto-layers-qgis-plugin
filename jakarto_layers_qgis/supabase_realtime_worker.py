import asyncio
import threading
import uuid

from PyQt5.QtCore import QObject, pyqtSignal

from .presence import PresenceManager
from .supabase_events import (
    SupabaseDeleteMessage,
    SupabaseInsertMessage,
    SupabaseUpdateMessage,
    parse_message,
)
from .vendor.realtime import AsyncRealtimeClient


class RealTimeWorker(QObject):
    event_received = pyqtSignal(
        list,  # list[SupabaseInsertMessage]
        list,  # list[SupabaseUpdateMessage]
        list,  # list[SupabaseDeleteMessage]
    )  # Signal for realtime events
    finished = pyqtSignal()

    def __init__(
        self,
        realtime_url: str,
        anon_key: str,
        user_id: str,
        stop_event: threading.Event,
        presence_manager: PresenceManager,
        access_token: str,
    ):
        super().__init__()
        self._stop_event = stop_event
        self._realtime_client = AsyncRealtimeClient(realtime_url, token=anon_key)
        self._realtime_url = realtime_url
        self._anon_key = anon_key
        self._user_id = user_id
        self._presence_manager = presence_manager
        self._access_token = access_token

    def start(self):
        insert_messages = []
        update_messages = []
        delete_messages = []

        def _parse_message(message: dict) -> None:
            message = parse_message(message)
            if message is None:
                return
            if isinstance(message, SupabaseInsertMessage):
                insert_messages.append(message)
            elif isinstance(message, SupabaseUpdateMessage):
                update_messages.append(message)
            elif isinstance(message, SupabaseDeleteMessage):
                delete_messages.append(message)

        async def _run_realtime():
            _realtime: AsyncRealtimeClient = self._realtime_client
            try:
                await _realtime.connect()
                await _realtime.set_auth(self._access_token)
                await (
                    _realtime.channel("points")
                    .on_postgres_changes(
                        "*",
                        table="points",
                        callback=_parse_message,
                    )
                    .subscribe()
                )

                channel = _realtime.channel(
                    # this channel is private, only the user with the same id can subscribe to it
                    # this is configured in the realtime.messages table's RLS policies
                    f"jakartowns_positions_{self._user_id}",
                    params={
                        "config": {
                            "broadcast": {"ack": False, "self": False},
                            "presence": {"key": str(uuid.uuid4())},
                            "private": True,
                        }
                    },
                )
                await self._presence_manager.subscribe_channel(channel)

                while not self._stop_event.is_set():
                    await asyncio.sleep(0.25)
                    if insert_messages or update_messages or delete_messages:
                        self.event_received.emit(
                            list(insert_messages),
                            list(update_messages),
                            list(delete_messages),
                        )
                        insert_messages.clear()
                        update_messages.clear()
                        delete_messages.clear()
            finally:
                await _realtime.close()

        try:
            asyncio.run(_run_realtime())
        except Exception:
            if not self._stop_event.is_set():
                raise
        finally:
            self.finished.emit()
