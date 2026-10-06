import importlib
import pkgutil

from app.models.base import Base
from app.models.enums import TaskPriority, TaskStatus
from app.models.project import Project
from app.models.task import Task

for _mod in pkgutil.iter_modules(__path__):
    if not _mod.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_mod.name}")

__all__ = ["Base", "Project", "Task", "TaskPriority", "TaskStatus"]
