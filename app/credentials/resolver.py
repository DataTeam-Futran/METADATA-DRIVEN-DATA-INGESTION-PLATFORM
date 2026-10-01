"""
Credential Resolver
===================

Resolves a credential_id from the metadata database into
an actual runtime secret.

The resolver does NOT store secrets.

It only:

    credential_id
          |
          v
    conn.credential_ref
          |
          +-- secret_provider_code
          |
          +-- secret_ref
          |
          v
    SecretProvider
          |
          v
    secret
"""

from app.credentials.base import SecretProvider
from app.credentials.providers.demo import DemoSecretProvider
from app.db.metastore import get_metastore_connection


class CredentialResolver:
    """
    Resolves metadata credential references into runtime secrets.

    The resolver is responsible for:
        1. Reading credential metadata from the metastore.
        2. Identifying the configured secret provider.
        3. Passing the secret reference to that provider.
        4. Returning the runtime secret to the caller.

    The resolver never stores the actual secret.
    """

    def __init__(self) -> None:
        """
        Initialize the supported secret providers.

        Provider selection is based on secret_provider_code
        stored in conn.credential_ref.
        """

        self._providers: dict[str, SecretProvider] = {
            "DEMO": DemoSecretProvider(),
        }

    def resolve(self, credential_id: int) -> str:
        """
        Resolve a credential ID into its runtime secret.

        Parameters
        ----------
        credential_id:
            Credential ID from conn.connection_profile.credential_id.

        Returns
        -------
        str
            Runtime secret retrieved from the configured SecretProvider.

        Raises
        ------
        ValueError
            If credential_id is invalid, provider is unsupported,
            or secret_ref is missing.

        LookupError
            If the credential does not exist in conn.credential_ref.
        """

        # ---------------------------------------------------------
        # Step 1: Validate credential ID
        # ---------------------------------------------------------

        if credential_id <= 0:
            raise ValueError(
                "credential_id must be greater than zero."
            )

        # ---------------------------------------------------------
        # Step 2: Retrieve credential metadata
        # ---------------------------------------------------------

        query = """
            SELECT
                secret_provider_code,
                secret_ref
            FROM conn.credential_ref
            WHERE credential_id = %s
            LIMIT 1;
        """

        with get_metastore_connection() as connection:

            with connection.cursor() as cursor:

                cursor.execute(
                    query,
                    (credential_id,),
                )

                row = cursor.fetchone()

        # ---------------------------------------------------------
        # Step 3: Validate credential exists
        # ---------------------------------------------------------

        if row is None:
            raise LookupError(
                f"Credential ID {credential_id} was not found."
            )

        provider_code, secret_ref = row

        # ---------------------------------------------------------
        # Step 4: Validate provider code
        # ---------------------------------------------------------

        if provider_code is None or not str(provider_code).strip():
            raise ValueError(
                f"Credential ID {credential_id} has no "
                "secret provider configured."
            )

        provider_code = str(provider_code).strip().upper()

        # ---------------------------------------------------------
        # Step 5: Validate secret reference
        # ---------------------------------------------------------

        if secret_ref is None or not str(secret_ref).strip():
            raise ValueError(
                f"Credential ID {credential_id} has no "
                "secret reference configured."
            )

        secret_ref = str(secret_ref).strip()

        # ---------------------------------------------------------
        # Step 6: Resolve the configured provider
        # ---------------------------------------------------------

        provider = self._providers.get(provider_code)

        if provider is None:
            raise ValueError(
                f"Unsupported secret provider: {provider_code}"
            )

        # ---------------------------------------------------------
        # Step 7: Resolve the actual secret
        # ---------------------------------------------------------

        return provider.get_secret(secret_ref)