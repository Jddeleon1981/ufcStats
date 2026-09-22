{#
    Use custom schema names verbatim instead of prefixing them with the target
    schema.

    dbt's default would turn `+schema: raw` into `main_raw` on DuckDB, and
    `analytics_raw` on Databricks -- neither of which matches the `raw.bouts`
    that ufcPipeline/load.py writes. With this override the layers land where
    the naming conventions say they do: raw, staging, marts, snapshots.

    The default exists so several people can build into one warehouse without
    colliding, each prefixed by their own target schema. This project has one
    owner and one prod deployment, so the collision risk is not real and the
    readable names are worth more. Revisit if that ever stops being true.
#}

{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
