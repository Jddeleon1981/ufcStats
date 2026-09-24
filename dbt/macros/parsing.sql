{#
    Parsers for the shapes ufcstats.com renders. The raw layer keeps every value
    as the site wrote it, so each of these turns one of those strings into a
    typed column. They live here rather than inline because the same six shapes
    repeat across corners and models -- "14 of 31" alone appears twelve times in
    the bouts model.
#}


{% macro nullify_sentinels(column) -%}
    {#- The site writes "--" or "---" for "not recorded" and for "undefined".
        A fighter who attempted no takedowns has no accuracy, which is not the
        same as 0%, so these become NULL rather than zero. -#}
    nullif(nullif(nullif({{ column }}, '--'), '---'), '')
{%- endmacro %}


{% macro parse_landed(column) -%}
    {#- "14 of 31" -> 14 -#}
    try_cast(split_part({{ column }}, ' of ', 1) as integer)
{%- endmacro %}


{% macro parse_attempted(column) -%}
    {#- "14 of 31" -> 31 -#}
    try_cast(split_part({{ column }}, ' of ', 2) as integer)
{%- endmacro %}


{% macro parse_percentage(column) -%}
    {#- "45%" -> 0.45, "---" -> NULL -#}
    try_cast(replace({{ nullify_sentinels(column) }}, '%', '') as decimal(5, 2)) / 100
{%- endmacro %}


{% macro parse_mmss_seconds(column) -%}
    {#- "5:08" -> 308. Minutes are unbounded: control time accumulates across
        rounds, so values above 59 minutes are legitimate. -#}
    try_cast(split_part({{ column }}, ':', 1) as integer) * 60
    + try_cast(split_part({{ column }}, ':', 2) as integer)
{%- endmacro %}


{#
    Date parsing is the one shape that is not portable. DuckDB uses strftime
    codes, Databricks uses Java patterns, so this dispatches per adapter --
    which is the whole reason the project runs against two of them.

    `style` is 'long' for the events page ("September 05, 2026") and 'short'
    for a fighter's date of birth ("Feb 13, 1990").

    NOTE: the databricks implementation is written but unverified -- prod is
    not deployed until P7. The duckdb one is exercised by every dbt build.
#}
{% macro parse_site_date(column, style='long') -%}
    {{ return(adapter.dispatch('parse_site_date', 'ufc')(column, style)) }}
{%- endmacro %}


{% macro duckdb__parse_site_date(column, style) -%}
    cast(
        try_strptime(
            {{ nullify_sentinels(column) }},
            {% if style == 'long' %}'%B %d, %Y'{% else %}'%b %d, %Y'{% endif %}
        ) as date
    )
{%- endmacro %}


{% macro databricks__parse_site_date(column, style) -%}
    try_to_timestamp(
        {{ nullify_sentinels(column) }},
        {% if style == 'long' %}'MMMM dd, yyyy'{% else %}'MMM dd, yyyy'{% endif %}
    )::date
{%- endmacro %}


{% macro default__parse_site_date(column, style) -%}
    {{ exceptions.raise_compiler_error(
        "parse_site_date has no implementation for adapter " ~ target.type
    ) }}
{%- endmacro %}
