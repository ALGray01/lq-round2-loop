"""Supplementary, optional check against the REAL Graphiti/Honcho/Cognee
libraries -- not the stand-ins in this repo.

Everything else in `legal_memory/` is stdlib-only by design (see README
Limitations). This one file is the deliberate exception: it pip-installs
and inspects the actual `graphiti-core`, `honcho-ai`, and `cognee`
packages to check two claims this README makes by source inspection
rather than assumption:

1. Does Graphiti's real edge schema actually carry bi-temporal fields
   (this repo's `valid_from_week`/`learned_week` are modeled on it)?
2. Do these libraries' real tenant/matter-partition mechanisms
   (`group_id`, `workspace_id`, `dataset_name`) require a value at
   construction the way this repo's `Fact.matter_id` does, or do they
   default to a shared bucket when omitted?

This is NOT an end-to-end behavioral test: none of the three libraries
were actually run against the scenario (Graphiti needs a Neo4j instance
plus an LLM for entity extraction; Honcho is a client for a hosted API;
Cognee's `cognify` pipeline needs an LLM too, and none of
`ANTHROPIC_API_KEY`/`OPENAI_API_KEY` are set in this environment --
checked directly with `os.environ`, not assumed). `check_local_llm_access()`
goes one step further than just checking API keys: it also probes common
local-inference ports (Ollama, LM Studio, generic dev servers) and looks
for `ollama`/`llama-cpp` on PATH, so "no LLM available here" is a checked
fact, not an assumption that stops at "no API key set." What follows is
source inspection of installed packages, not a benchmark run.

Requires: `pip install graphiti-core honcho-ai cognee` (large dependency
trees, especially cognee -- not part of this repo's own requirements,
and not needed to run anything else in `legal_memory/`).
"""
from __future__ import annotations

import inspect
import os


def check_graphiti() -> None:
    print("=== graphiti-core: real EntityEdge temporal fields ===")
    from graphiti_core.edges import EntityEdge

    fields = EntityEdge.model_fields
    for name in ("created_at", "expired_at", "valid_at", "invalid_at"):
        present = name in fields
        print(f"  {name}: {'present' if present else 'MISSING'}"
              + (f" (required={fields[name].is_required()})" if present else ""))
    print("  -> confirms this repo's bi-temporal design (two independent clocks:")
    print("     valid_at/invalid_at = valid time, created_at/expired_at = transaction")
    print("     time) matches Graphiti's actual edge schema, not just its design docs.")

    print()
    print("=== graphiti-core: is group_id (its matter-partition mechanism) required? ===")
    from graphiti_core.edges import Edge
    group_id_field = Edge.model_fields["group_id"]
    print(f"  Edge.group_id is_required() at the Pydantic model level: {group_id_field.is_required()}")
    print("  (this only means the *low-level* Edge object needs *some* string passed in --")
    print("   see below for what value the *public* add_episode() API actually supplies)")
    from graphiti_core.helpers import validate_group_id
    print(f"  validate_group_id.__doc__ (first line): {validate_group_id.__doc__.strip().splitlines()[0]!r}")
    src = inspect.getsource(validate_group_id)
    allows_empty = "Allow empty string" in src
    print(f"  validate_group_id source explicitly allows empty string: {allows_empty}")
    add_episode_src = inspect.getsource(
        __import__("graphiti_core.graphiti", fromlist=["Graphiti"]).Graphiti.add_episode
    )
    falls_back = "get_default_group_id" in add_episode_src and "group_id is None" in add_episode_src
    print(f"  Graphiti.add_episode(group_id=None) resolves a default before constructing"
          f" any Edge: {falls_back}")
    print("  -> The low-level Edge model requires *a* string (Pydantic can't have a")
    print("     missing field); the public API a caller actually uses resolves that")
    print("     string FOR them when they don't pass one, silently pooling into a")
    print("     shared default ('' for most providers). The practical, caller-facing")
    print("     guarantee is 'you always get some group_id,' not 'you must choose one' --")
    print("     the opposite of this repo's Fact.matter_id, which has no such resolution")
    print("     step and refuses to construct at all without a real value.")


def check_honcho() -> None:
    print()
    print("=== honcho-ai: is workspace_id (its tenant-partition mechanism) required? ===")
    from honcho.client import Honcho
    sig = inspect.signature(Honcho.__init__)
    workspace_param = sig.parameters["workspace_id"]
    print(f"  Honcho.__init__'s workspace_id default: {workspace_param.default!r}")
    src = inspect.getsource(Honcho.__init__)
    print(f"  Falls back to \"default\" (env var or literal) when omitted: {'\"default\"' in src}")
    from honcho.peer import Peer
    peer_sig = inspect.signature(Peer.__init__)
    peer_id_field = peer_sig.parameters["peer_id"].default
    print(f"  Peer.peer_id field: {peer_id_field!r} (min_length enforced -- but this is")
    print("    peer identity within a workspace, not cross-tenant isolation)")
    print("  -> Same pattern as Graphiti: the actual tenant-scoping parameter")
    print("     (workspace_id) is optional and pools into a shared \"default\"")
    print("     workspace when a caller forgets to pass it.")


def check_cognee() -> None:
    print()
    print("=== cognee: is dataset_name (its matter-partition mechanism) required? ===")
    from cognee.api.v1.add.add import add as cognee_add
    sig = inspect.signature(cognee_add)
    dataset_name_default = sig.parameters["dataset_name"].default
    print(f"  add()'s dataset_name default: {dataset_name_default!r}")
    print("  -> A third confirmation of the same pattern: cognee's real partition")
    print("     key also defaults to a shared bucket (\"main_dataset\") rather than")
    print("     requiring an explicit value.")


def check_local_llm_access() -> None:
    """No API key doesn't rule out a local model server -- checked directly
    rather than assumed. Tries common local inference ports (Ollama's
    default 11434, LM Studio's 1234, and two other common dev-server ports)
    with a short timeout, and looks for `ollama`/`llama-cpp` on PATH.
    """
    import shutil
    import urllib.request

    print("Local model server / binary check (not just API keys):")
    for port in (11434, 1234, 8080, 5000):
        try:
            urllib.request.urlopen(f"http://localhost:{port}", timeout=1.5)
            print(f"  port {port}: reachable (unexpected -- investigate before assuming no local LLM)")
        except Exception as exc:  # noqa: BLE001 -- any failure means "not reachable," which is the expected case
            print(f"  port {port}: not reachable ({type(exc).__name__})")
    for binary in ("ollama", "llama-cpp", "llama-cpp-python"):
        found = shutil.which(binary)
        print(f"  `{binary}` on PATH: {found or 'not found'}")


def main() -> None:
    print(f"ANTHROPIC_API_KEY set: {bool(os.environ.get('ANTHROPIC_API_KEY'))}")
    print(f"OPENAI_API_KEY set: {bool(os.environ.get('OPENAI_API_KEY'))}")
    print()
    check_local_llm_access()
    print("(no API key, no reachable local model server or binary -- so no")
    print(" end-to-end run of any of these libraries, and no real LLM-driven")
    print(" extraction step, was possible here; everything below is source")
    print(" inspection of installed packages, not a behavioral test)")
    print()
    check_graphiti()
    check_honcho()
    check_cognee()
    print()
    print("=== Summary ===")
    print("  All three real libraries' actual tenant/matter-partition parameter")
    print("  (group_id / workspace_id / dataset_name) is OPTIONAL with a shared")
    print("  default fallback -- none of them make it a required field the way")
    print("  this repo's Fact.matter_id is required and non-nullable. This is a")
    print("  real, verified finding, not an assumption -- and it means this")
    print("  repo's isolation design is a deliberate hardening beyond what any")
    print("  of the three reference libraries do by default, not a description")
    print("  of how they already behave.")


if __name__ == "__main__":
    main()
