from dmint_dashboard.core_client import CoreClient, ThreadSafeApprovalStore

__version__ = "1.0.0"


def main(argv: list[str] | None = None, prog: str | None = None) -> None:
    """Run the public Dashboard CLI entrypoint."""
    from dmint_dashboard.__main__ import main as _main

    return _main(argv=argv, prog=prog)


__all__ = ["CoreClient", "ThreadSafeApprovalStore", "main", "__version__"]
