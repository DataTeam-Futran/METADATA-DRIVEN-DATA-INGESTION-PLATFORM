"""
Demo Secret Provider
====================

Purpose
-------

This provider is used only for the local/development POC.

It demonstrates the production-style credential architecture:

    Metadata
        |
        v
    credential_id
        |
        v
    conn.credential_ref
        |
        v
    secret_provider_code + secret_ref
        |
        v
    DemoSecretProvider
        |
        v
    Environment Variable
        |
        v
    Actual Secret

Important
---------

The actual password is NEVER stored in the metadata tables.

The metadata database stores only a reference such as:

    POSTGRES_DEV_SECRET

The actual password is supplied through an environment variable.

This provider should eventually be replaced by a real secret
management implementation such as Azure Key Vault, AWS Secrets
Manager, HashiCorp Vault, etc.
"""

# ---------------------------------------------------------------------
# Standard-library imports
# ---------------------------------------------------------------------

# os is used to read the development secret from an environment
# variable instead of storing the password in source code.
import os


# ---------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------

# SecretProvider defines the platform-neutral credential provider
# contract.
from app.credentials.base import SecretProvider


# ---------------------------------------------------------------------
# Demo Secret Provider
# ---------------------------------------------------------------------

class DemoSecretProvider(SecretProvider):
    """
    Development-only secret provider.

    It resolves approved metadata secret references to environment
    variables.

    Example:

        POSTGRES_DEV_SECRET
                |
                v
        MDIP_DEMO_POSTGRES_PASSWORD
    """

    # -------------------------------------------------------------
    # Supported secret references
    # -------------------------------------------------------------
    #
    # The key is the reference stored in conn.credential_ref.
    #
    # The value is the environment variable containing the actual
    # development secret.
    #
    # This allows metadata to refer to a logical secret without
    # exposing the actual password.
    #
    SECRET_ENVIRONMENT_VARIABLES = {

        # Current reference used by credential ID 1 in the metadata
        # database.
        "POSTGRES_DEV_SECRET":
            "MDIP_DEMO_POSTGRES_PASSWORD",

        # Keep the earlier reference supported as well.
        #
        # This prevents breaking any existing development metadata
        # that may already use this reference.
        "secret/demo/postgresql/password":
            "MDIP_DEMO_POSTGRES_PASSWORD",
    }

    # -------------------------------------------------------------
    # Resolve secret
    # -------------------------------------------------------------

    def get_secret(
        self,
        secret_ref: str,
    ) -> str:
        """
        Resolve a logical secret reference to its actual secret.

        The actual secret is read from an environment variable.

        The secret itself is never printed or logged.
        """

        # ---------------------------------------------------------
        # Validate the secret reference
        # ---------------------------------------------------------

        # A missing reference cannot be resolved safely.
        if not secret_ref:
            raise ValueError(
                "Secret reference cannot be empty."
            )

        # ---------------------------------------------------------
        # Resolve environment variable name
        # ---------------------------------------------------------

        # Look up the approved environment variable corresponding
        # to the metadata secret reference.
        environment_variable = (
            self.SECRET_ENVIRONMENT_VARIABLES.get(
                secret_ref
            )
        )

        # Reject references that have not been explicitly registered.
        #
        # This is important because the provider should never allow
        # arbitrary environment-variable access based on metadata.
        if environment_variable is None:
            raise ValueError(
                "Unsupported DEMO secret reference: "
                f"{secret_ref}"
            )

        # ---------------------------------------------------------
        # Read the actual secret
        # ---------------------------------------------------------

        # Read the password from the environment.
        secret = os.getenv(
            environment_variable
        )

        # Fail clearly if the required environment variable has not
        # been configured.
        if not secret:
            raise RuntimeError(
                "Required DEMO secret environment variable "
                f"is not configured: {environment_variable}"
            )

        # Return the secret to the credential resolver.
        #
        # IMPORTANT:
        # Do not print this value.
        return secret