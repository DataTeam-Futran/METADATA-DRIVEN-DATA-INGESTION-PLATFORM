"""
Credential Provider Contracts
=============================

Defines the platform-neutral interface used to resolve secrets.

The application must not know how a secret is physically stored.

Examples of future providers:

    DEMO
    AZURE_KEY_VAULT
    AWS_SECRETS_MANAGER
    HASHICORP_VAULT
"""

from abc import ABC, abstractmethod


class SecretProvider(ABC):
    """
    Base contract for all secret providers.

    A provider receives an opaque secret reference and returns
    the secret value at runtime.

    The secret itself must never be persisted in metadata.
    """

    @abstractmethod
    def get_secret(self, secret_ref: str) -> str:
        """
        Resolve a secret using its reference.

        Parameters
        ----------
        secret_ref:
            Opaque reference stored in conn.credential_ref.

        Returns
        -------
        str
            Resolved secret value.

        Raises
        ------
        ValueError
            If the secret reference is invalid.

        RuntimeError
            If the provider cannot resolve the secret.
        """

        raise NotImplementedError