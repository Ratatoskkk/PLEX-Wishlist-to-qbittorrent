"""Pure domain logic: models, release parsing, scoring and grab decisions.

Nothing in this package performs I/O. That is deliberate -- it means every
ranking and "should I grab this?" rule is testable with plain function calls,
which is where the reference project's behaviour was hardest to verify.
"""
