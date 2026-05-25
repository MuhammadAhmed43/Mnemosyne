import uuid


def generate_id(prefix: str = "") -> str:
    """UUID4 hex, optionally prefixed (e.g. generate_id('node') -> 'node_ab12...')."""
    raw = uuid.uuid4().hex
    return f"{prefix}_{raw}" if prefix else raw
