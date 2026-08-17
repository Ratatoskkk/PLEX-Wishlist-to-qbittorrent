"""Application services: the code that actually does things.

Each service takes the shared :class:`~conduit.services.context.Conduit`
context, performs one job end to end, and reports what it did through the
event bus and the database. They are all plain coroutines, so the supervisor
can schedule them, the API can trigger them on demand, and tests can call them
directly.
"""
