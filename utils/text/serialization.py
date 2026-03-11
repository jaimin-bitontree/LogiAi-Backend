def serialize_pydantic(obj) -> dict:
    """Convert a Pydantic model or dict-like object to a plain dict for MongoDB storage."""
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    try:
        return dict(obj)
    except (TypeError, ValueError):
        return {}
