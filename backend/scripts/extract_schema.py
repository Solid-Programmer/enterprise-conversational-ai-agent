import sys
import os
import json
import pyodbc

# ==============================================================================
# Database Connection Configuration (read from environment variables with defaults)
# ==============================================================================
DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_NAME = os.getenv("DB_NAME", "AdventureWorks2022")
DB_DRIVER = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
DB_TRUSTED_CONNECTION = os.getenv("DB_TRUSTED_CONNECTION", "yes")
DB_TRUST_SERVER_CERTIFICATE = os.getenv("DB_TRUST_SERVER_CERTIFICATE", "yes")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")


def get_connection():
    """Builds pyodbc connection string and connects to SQL Server."""
    if DB_USER and DB_PASSWORD:
        conn_str = (
            f"DRIVER={{{DB_DRIVER}}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD};"
            f"TrustServerCertificate={DB_TRUST_SERVER_CERTIFICATE};"
        )
    else:
        conn_str = (
            f"DRIVER={{{DB_DRIVER}}};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"Trusted_Connection={DB_TRUSTED_CONNECTION};"
            f"TrustServerCertificate={DB_TRUST_SERVER_CERTIFICATE};"
        )

    try:
        return pyodbc.connect(conn_str)
    except Exception as e:
        print(f"Error connecting to database '{DB_NAME}' on server '{DB_SERVER}': {e}")
        sys.exit(1)


def format_data_type(type_name, max_length, precision, scale):
    """Formats SQL data type into a standard readable type string."""
    t = type_name.lower()
    if t in ("varchar", "char", "varbinary", "binary"):
        return f"{t}(max)" if max_length == -1 else f"{t}({max_length})"
    elif t in ("nvarchar", "nchar"):
        return f"{t}(max)" if max_length == -1 else f"{t}({max_length // 2})"
    elif t in ("decimal", "numeric"):
        return f"{t}({precision},{scale})"
    return t


def extract_schema_metadata(schema_name):
    """Queries SQL Server system views to extract tables, columns, descriptions, and foreign key relationships."""
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Query tables and table-level descriptions (MS_Description extended property)
    tables_query = """
        SELECT 
            t.name AS table_name,
            CAST(ep.value AS NVARCHAR(MAX)) AS table_description
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        LEFT JOIN sys.extended_properties ep 
            ON ep.major_id = t.object_id 
           AND ep.minor_id = 0 
           AND ep.class = 1 
           AND ep.name = 'MS_Description'
        WHERE s.name = ? AND t.is_ms_shipped = 0
        ORDER BY t.name
    """
    cursor.execute(tables_query, schema_name)
    table_rows = cursor.fetchall()

    tables_dict = {}
    for row in table_rows:
        tables_dict[row.table_name] = {
            "name": row.table_name,
            "description": row.table_description if row.table_description else None,
            "columns": []
        }

    # 2. Query columns, data types, nullability, primary keys, and column-level descriptions
    columns_query = """
        SELECT 
            t.name AS table_name,
            c.name AS column_name,
            st.name AS system_type_name,
            c.max_length,
            c.precision,
            c.scale,
            c.is_nullable,
            CASE 
                WHEN pk.column_id IS NOT NULL THEN 1 
                ELSE 0 
            END AS is_primary_key,
            CAST(ep.value AS NVARCHAR(MAX)) AS column_description
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        INNER JOIN sys.columns c ON t.object_id = c.object_id
        INNER JOIN sys.types st ON c.system_type_id = st.user_type_id AND st.is_user_defined = 0
        LEFT JOIN (
            SELECT 
                ic.object_id, 
                ic.column_id
            FROM sys.indexes i
            INNER JOIN sys.index_columns ic 
                ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            WHERE i.is_primary_key = 1
        ) pk ON c.object_id = pk.object_id AND c.column_id = pk.column_id
        LEFT JOIN sys.extended_properties ep 
            ON ep.major_id = c.object_id 
           AND ep.minor_id = c.column_id 
           AND ep.class = 1 
           AND ep.name = 'MS_Description'
        WHERE s.name = ? AND t.is_ms_shipped = 0
        ORDER BY t.name, c.column_id
    """

    cursor.execute(columns_query, schema_name)
    col_rows = cursor.fetchall()

    for row in col_rows:
        table_name = row.table_name
        if table_name in tables_dict:
            data_type = format_data_type(
                row.system_type_name, row.max_length, row.precision, row.scale
            )
            tables_dict[table_name]["columns"].append({
                "name": row.column_name,
                "data_type": data_type,
                "nullable": bool(row.is_nullable),
                "primary_key": bool(row.is_primary_key),
                "description": row.column_description if row.column_description else None
            })

    tables_list = [tables_dict[t_name] for t_name in sorted(tables_dict.keys())]

    # 3. Query foreign key relationships grouped by FK constraint (handling composite keys)
    relationships_query = """
        SELECT 
            fk.name AS constraint_name,
            parent_s.name AS from_schema,
            parent_t.name AS from_table,
            parent_c.name AS from_column,
            ref_s.name AS to_schema,
            ref_t.name AS to_table,
            ref_c.name AS to_column,
            fkc.constraint_column_id
        FROM sys.foreign_keys fk
        INNER JOIN sys.tables parent_t ON fk.parent_object_id = parent_t.object_id
        INNER JOIN sys.schemas parent_s ON parent_t.schema_id = parent_s.schema_id
        INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
        INNER JOIN sys.columns parent_c ON fkc.parent_object_id = parent_c.object_id AND fkc.parent_column_id = parent_c.column_id
        INNER JOIN sys.tables ref_t ON fk.referenced_object_id = ref_t.object_id
        INNER JOIN sys.schemas ref_s ON ref_t.schema_id = ref_s.schema_id
        INNER JOIN sys.columns ref_c ON fkc.referenced_object_id = ref_c.object_id AND fkc.referenced_column_id = ref_c.column_id
        WHERE parent_s.name = ? AND parent_t.is_ms_shipped = 0
        ORDER BY parent_t.name, fk.name, fkc.constraint_column_id
    """

    cursor.execute(relationships_query, schema_name)
    rel_rows = cursor.fetchall()

    rel_map = {}
    for row in rel_rows:
        key = row.constraint_name
        if key not in rel_map:
            rel_map[key] = {
                "constraint_name": row.constraint_name,
                "from_schema": row.from_schema,
                "from_table": row.from_table,
                "from_columns": [],
                "to_schema": row.to_schema,
                "to_table": row.to_table,
                "to_columns": []
            }
        rel_map[key]["from_columns"].append(row.from_column)
        rel_map[key]["to_columns"].append(row.to_column)

    relationships = list(rel_map.values())
    relationships.sort(key=lambda r: (r["from_table"], r["constraint_name"]))

    conn.close()

    return {
        "schema": schema_name,
        "tables": tables_list,
        "relationships": relationships
    }


def main():
    schema_name = sys.argv[1] if len(sys.argv) > 1 else "Sales"
    print(f"Extracting metadata for schema '{schema_name}' from database '{DB_NAME}'...")

    schema_data = extract_schema_metadata(schema_name)

    output_filename = f"{schema_name.lower()}_schema.json"
    with open(output_filename, "w", encoding="utf-8") as f:
        json.dump(schema_data, f, indent=2)

    print(f"Extraction complete! Metadata saved to '{output_filename}'.")
    print(f"Total tables: {len(schema_data['tables'])}, Total relationships: {len(schema_data['relationships'])}")


if __name__ == "__main__":
    main()
