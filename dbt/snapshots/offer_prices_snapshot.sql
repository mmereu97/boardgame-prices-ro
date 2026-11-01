{#-
  Price history as a slowly changing dimension (SCD Type 2): a new row only when an offer's
  price or availability changes, with dbt_valid_from / dbt_valid_to. The daily fact keeps
  every day; the snapshot keeps every change, which is far smaller over years.
-#}
{% snapshot offer_prices_snapshot %}
{{ config(
    unique_key='offer_id',
    strategy='check',
    check_cols=['price', 'available']
) }}
select distinct on (offer_id)
    offer_id, shop, game_key, title, price, available, url, collected_on
from {{ ref('fct_offer_prices') }}
order by offer_id, collected_on desc
{% endsnapshot %}
