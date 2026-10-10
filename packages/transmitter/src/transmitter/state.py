"""Local publish state (`publish.json`): the authoritative mirror of what is in
R2 -- horizon first/last, every run of segment keys uploaded (or attempted:
a batch records its range before its first PUT) and not yet pruned (prune
deletes by these computed ranges; no List calls), and the digest of each
show's uploaded notes/page. Plus the current fallback version."""

from dataclasses import asdict, dataclass, field

from transmitter.workspace import Workspace, read_json, write_json


@dataclass
class PublishState:
    epoch_id: str | None = None
    first: int | None = None
    last: int | None = None
    runs: list[list[int]] = field(default_factory=list)
    notes: dict[str, str] = field(default_factory=dict)


def load_publish_state(ws: Workspace) -> PublishState:
    data = read_json(ws.publish_state_path)
    if data is None:
        return PublishState()
    return PublishState(epoch_id=data.get("epoch_id"), first=data.get("first"),
                        last=data.get("last"), runs=[list(r) for r in data.get("runs", [])],
                        notes=dict(data.get("notes", {})))


def save_publish_state(ws: Workspace, state: PublishState) -> None:
    write_json(ws.publish_state_path, asdict(state))


def load_fallback_version(ws: Workspace) -> str | None:
    data = read_json(ws.fallback_path)
    return data.get("version") if data else None


def save_fallback_version(ws: Workspace, version: str) -> None:
    write_json(ws.fallback_path, {"version": version})
