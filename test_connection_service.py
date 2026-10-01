# ============================================================
# TEST CONNECTION METADATA SERVICE
# ============================================================
#
# WHY:
# This test verifies that our ConnectionService can retrieve
# connection metadata from the Futran metadata database.
#
# Our demo connection_id is currently 1.
#
# ============================================================


from app_prod.services.connection_service import get_connection_metadata


# ============================================================
# CONNECTION ID
# ============================================================
#
# This is the demo connection that we created earlier in
# conn.connection_profile.
#
# ============================================================

connection_id = 1


try:

    # --------------------------------------------------------
    # Retrieve metadata using our service.
    # --------------------------------------------------------

    metadata = get_connection_metadata(connection_id)

    # --------------------------------------------------------
    # Check whether a matching connection was found.
    # --------------------------------------------------------

    if metadata is None:

        print("No connection metadata found.")

    else:

        # ----------------------------------------------------
        # The SELECT query returns values in this order:
        #
        # 1. database_name
        # 2. endpoint_url
        # 3. host_name
        # 4. port_no
        # 5. secret_ref
        # 6. credential_name
        # ----------------------------------------------------

        (
            database_name,
            endpoint_url,
            host_name,
            port_no,
            secret_ref,
            credential_name
        ) = metadata


        # ----------------------------------------------------
        # Display the retrieved metadata.
        # ----------------------------------------------------

        print()
        print("Connection Metadata")
        print("-------------------")

        print("Database Name :", database_name)
        print("Endpoint URL  :", endpoint_url)
        print("Host Name     :", host_name)
        print("Port Number   :", port_no)
        print("Secret Ref    :", secret_ref)
        print("Credential    :", credential_name)


except Exception as error:

    print("Failed to retrieve connection metadata.")
    print("Error:", error)