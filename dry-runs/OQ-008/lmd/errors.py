class BuildError(Exception):
    """Raised when a document fails a legal-markdown validation rule.

    Mirrors a compiler diagnostic: these are supposed to stop the build,
    not degrade gracefully, because a broken cross-reference or an
    undefined term is a correctness bug in the legal document itself.
    """

    def __init__(self, message: str, *, line: int | None = None, context: str = ""):
        self.line = line
        self.context = context
        located = f" (line {line})" if line is not None else ""
        ctx = f"\n    {context}" if context else ""
        super().__init__(f"{message}{located}{ctx}")
