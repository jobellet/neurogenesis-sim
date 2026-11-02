# Security

Please report security problems privately, through GitHub's "Report a vulnerability" button on the repository's
Security tab, rather than in a public issue. Project files (JSON) are data: expressions in them are evaluated with a
restricted evaluator (`neurogenesis/expressions.py`), never with `eval`; a way to run code from a project file is a
security problem.
