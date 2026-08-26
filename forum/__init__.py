"""Community forum subsystem."""

from forum.db import init_forum_db
from forum.routes import mount_forum

__all__ = ["init_forum_db", "mount_forum"]
