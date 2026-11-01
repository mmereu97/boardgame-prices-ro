{#- Use the configured schema names as they are (staging, marts...), not "dbt_staging". -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}
