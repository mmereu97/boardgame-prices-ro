-- schema.org Product data from product pages. "offers" may be one object or a list.
with offers as (
    select
        o.*,
        case jsonb_typeof(o.payload -> 'offers')
            when 'array' then o.payload -> 'offers' -> 0
            else o.payload -> 'offers' end as offer
    from {{ source('raw', 'offers') }} o
    where o.platform = 'jsonld_sitemap'
)
select
    shop,
    collected_on,
    shop || ':' || md5(url)                                         as offer_id,
    url,
    payload ->> 'name'                                              as title,
    coalesce(payload -> 'brand' ->> 'name', payload ->> 'brand')    as brand,
    payload ->> 'category'                                          as category,
    coalesce(payload ->> 'gtin13', payload ->> 'gtin', payload ->> 'sku') as sku,
    (offer ->> 'price')::numeric(10, 2)                             as price,
    null::numeric(10, 2)                                            as list_price,
    (offer ->> 'availability') ilike '%InStock%'                    as available
from offers
