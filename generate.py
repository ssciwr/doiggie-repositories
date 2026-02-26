#!/usr/bin/env python3
"""Generate README content from discovered DataRepository implementations."""

from __future__ import annotations

import importlib.metadata
import inspect
from pathlib import Path
from typing import Any


def _discover_repository_classes() -> list[type]:
    """Discover repository implementations via package entry points."""
    entry_points = importlib.metadata.entry_points(group="pooch.data_repositories")
    if not entry_points:
        # Legacy entry-point group used by older pooch-doi versions.
        entry_points = importlib.metadata.entry_points(group="data_repositories")
    return [entry_point.load() for entry_point in entry_points]


def _repository_field_names(data_repository_type: type) -> list[str]:
    """Collect public field names exposed by DataRepository."""
    fields = list(getattr(data_repository_type, "__annotations__", {}).keys())
    for name, value in data_repository_type.__dict__.items():
        if isinstance(value, property) and not name.startswith("_"):
            fields.append(name)
    return fields


def _to_serializable(value: Any) -> Any:
    """Convert class metadata values into Jinja-friendly structures."""
    if isinstance(value, tuple):
        return [_to_serializable(v) for v in value]
    if isinstance(value, list):
        return [_to_serializable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_serializable(v) for k, v in value.items()}
    if isinstance(value, type):
        return f"{value.__module__}.{value.__name__}"
    return value


def _repository_to_dict(
    repo_type: type,
    field_names: list[str],
) -> dict[str, Any]:
    data = {
        "implementation": f"{repo_type.__module__}.{repo_type.__name__}",
    }
    repo_instance = None
    instance_init_failed = False

    for field in field_names:
        value = inspect.getattr_static(repo_type, field, None)
        if isinstance(value, property):
            # Prefer evaluating property without __init__, then fall back to an instance.
            try:
                value = value.__get__(repo_type.__new__(repo_type), repo_type)
            except Exception:
                if repo_instance is None and not instance_init_failed:
                    try:
                        repo_instance = repo_type()
                    except Exception:
                        instance_init_failed = True
                if repo_instance is None:
                    value = None
                else:
                    try:
                        value = getattr(repo_instance, field)
                    except Exception:
                        value = None

        data[field] = _to_serializable(value)
    return data


def _render_template(
    template_path: Path,
    output_path: Path,
    repositories: list[dict[str, Any]],
    fields: list[str],
) -> None:
    from jinja2 import Environment, FileSystemLoader

    env = Environment(
        loader=FileSystemLoader(str(template_path.parent)),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(template_path.name)
    rendered = template.render(repositories=repositories, fields=fields)
    output_path.write_text(rendered, encoding="utf-8")


def main() -> int:
    project_root = Path(__file__).resolve().parent
    template_path = project_root / "README.md.j2"
    output_path = project_root / "README.md"

    from pooch_doi.repository import DataRepository

    repositories = [
        repo_type
        for repo_type in _discover_repository_classes()
        if isinstance(repo_type, type) and issubclass(repo_type, DataRepository)
    ]
    fields = _repository_field_names(DataRepository)
    repository_dicts = [
        _repository_to_dict(repo_type, fields) for repo_type in repositories
    ]
    _render_template(template_path, output_path, repository_dicts, fields)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
