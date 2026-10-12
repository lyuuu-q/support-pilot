from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from support_pilot.config import get_settings


def checkpoint_conn_string() -> str:
    database_url = get_settings().database_url
    prefix = "postgresql+psycopg://"
    if database_url.startswith(prefix):
        return f"postgresql://{database_url.removeprefix(prefix)}"
    return database_url


@contextmanager
def open_checkpointer() -> Iterator[PostgresSaver | None]:
    if not get_settings().agent_checkpoint_enabled:
        yield None
        return
    with PostgresSaver.from_conn_string(checkpoint_conn_string()) as saver:
        yield saver
