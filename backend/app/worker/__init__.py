"""RabbitMQ-native workers for the dabljaAR dubbing pipeline.

Each worker connects to RabbitMQ, consumes messages from ``job.start.*``
routing keys, performs AI work, and publishes results back to
``job.results.*`` — forming a unified event-driven pipeline with the
Go orchestrator.
"""
