"""Stable seams for the company environment. No credentials, discovery, or mock successes.

Implement in the WORK repository only. The model may explain a policy decision;
it may not emit trusted security evidence without deterministic checks.
"""
from typing import Protocol


class IntegrationRequired(RuntimeError):
    pass


class WorkAdapter(Protocol):
    def build(self, job: dict, source_zip: bytes) -> dict:
        """Isolated build + complete SBOM + scans + signed digest -> BuildReport."""
        ...

    def deploy(self, job: dict) -> dict:
        """Deploy exact image privately, verify edge/egress/health -> Deployed."""
        ...

    def agent(self, job: dict, source_zip: bytes) -> dict:
        """Approved model, bounded app context, no live data -> AgentProposal."""
        ...


class UnconnectedAdapter:
    def build(self, job, source_zip):
        raise IntegrationRequired('WORK-CONNECT: isolated-build; configure approved sandbox and trusted scanners')

    def deploy(self, job):
        raise IntegrationRequired('WORK-CONNECT: private-hosting; configure private runtime and authenticated edge')

    def agent(self, job, source_zip):
        raise IntegrationRequired('WORK-CONNECT: app-agent; configure company-approved model and data handling')


def create_adapter():
    return UnconnectedAdapter()
