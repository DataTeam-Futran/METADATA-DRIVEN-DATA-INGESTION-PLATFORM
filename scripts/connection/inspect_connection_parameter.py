from app.db.metastore import get_metastore_connection


SECRET_KEYWORDS = (
    "password",
    "secret",
    "token",
    "key",
    "credential",
)


def is_sensitive(parameter_name: str, is_secret_ref: bool) -> bool:
    if is_secret_ref:
        return True

    parameter_name_lower = parameter_name.lower()

    return any(
        keyword in parameter_name_lower
        for keyword in SECRET_KEYWORDS
    )


def main() -> None:
    connection_id = 1

    print("=" * 80)
    print("CONNECTION PARAMETERS")
    print("=" * 80)

    query = """
        SELECT
            connection_parameter_id,
            connection_id,
            parameter_name,
            parameter_value,
            value_type_code,
            is_secret_ref,
            environment_override
        FROM conn.connection_parameter
        WHERE connection_id = %s
        ORDER BY connection_parameter_id;
    """

    with get_metastore_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (connection_id,))
            rows = cursor.fetchall()

    print()

    if not rows:
        print(
            f"No connection parameters found "
            f"for connection_id={connection_id}."
        )
    else:
        for row in rows:
            parameter_id = row[0]
            parameter_name = row[2]
            parameter_value = row[3]
            value_type = row[4]
            is_secret_ref = row[5]
            environment_override = row[6]

            if is_sensitive(
                parameter_name,
                is_secret_ref,
            ):
                display_value = "***MASKED***"
            else:
                display_value = parameter_value

            print(
                f"parameter_id={parameter_id} | "
                f"name={parameter_name} | "
                f"value={display_value} | "
                f"type={value_type} | "
                f"secret_ref={is_secret_ref} | "
                f"environment_override={environment_override}"
            )

    print()
    print("=" * 80)
    print("CONNECTION PARAMETER INSPECTION COMPLETED")
    print("=" * 80)


if __name__ == "__main__":
    main()