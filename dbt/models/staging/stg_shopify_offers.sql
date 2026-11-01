-- One row per Shopify variant per day. A product with several variants (e.g. language
-- editions) is several offers; "Default Title" is Shopify's name for "no variant".
select
    o.shop,
    o.collected_on,
    o.shop || ':' || (v ->> 'id')                                   as offer_id,
    o.url,
    case when coalesce(v ->> 'title', 'Default Title') = 'Default Title'
         then o.payload ->> 'title'
         else (o.payload ->> 'title') || ' - ' || (v ->> 'title') end as title,
    nullif(o.payload ->> 'vendor', '')                              as brand,
    nullif(o.payload ->> 'product_type', '')                        as category,
    nullif(v ->> 'sku', '')                                         as sku,
    (v ->> 'price')::numeric(10, 2)                                 as price,
    nullif(v ->> 'compare_at_price', '')::numeric(10, 2)            as list_price,
    (v ->> 'available')::boolean                                    as available
from {{ source('raw', 'offers') }} o
cross join lateral jsonb_array_elements(o.payload -> 'variants') v
where o.platform = 'shopify'
