"""Tool implementations. Every tool takes a ``Config`` and returns plain JSON-safe data.

Tools must use ``rt_imaging_mcp.security`` for paths and tags. They never write,
delete, move or send anything (rule R7).
"""
