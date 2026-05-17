import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def test_source_url_agent_agent_facade_reexports_owner_symbols() -> None:
    from ecommerce.source_url_agent.agent import (  # noqa: E402
        ProgressCallback as CompatProgressCallback,
        Resolver as CompatResolver,
        SourceUrlAgentOptions as CompatSourceUrlAgentOptions,
        SourceUrlAgentResult as CompatSourceUrlAgentResult,
        run_source_url_agent as compat_run_source_url_agent,
    )
    from ecommerce.source_url_agent.options import (  # noqa: E402
        ProgressCallback,
        Resolver,
        SourceUrlAgentOptions,
        SourceUrlAgentResult,
    )
    from ecommerce.source_url_agent.runner import run_source_url_agent  # noqa: E402

    assert CompatProgressCallback is ProgressCallback
    assert CompatResolver is Resolver
    assert CompatSourceUrlAgentOptions is SourceUrlAgentOptions
    assert CompatSourceUrlAgentResult is SourceUrlAgentResult
    assert compat_run_source_url_agent is run_source_url_agent
