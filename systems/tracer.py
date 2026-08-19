"""tracer bullet 的靶子。payload 就是草稿本身。"""
from kbcore.system import System, register

register(System(
    id="kb-tracer",
    suite="draft",
    build=lambda draft, repo: draft,
))
