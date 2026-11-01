-- Gomag category pages. Prices come from the box's data-Gomag JSON (Lei_final_price is what
-- you pay, Lei_price the full price when discounted). The shop's board-games category also
-- holds accessories (sleeves, playmats, organisers): they are told apart by the title, using
-- the same words the collector uses to skip their product pages.
select
    shop,
    collected_on,
    shop || ':' || (payload ->> 'id')                               as offer_id,
    url,
    payload ->> 'name'                                              as title,
    null::text                                                      as brand,
    case when (payload ->> 'name') ~* '(protecti|sleeve|playmat|insert|organiz|zaruri|dice|deck box|suport|album|binder)'
         then 'Accesorii' else 'Board Games' end                    as category,
    payload ->> 'gtin13'                                            as sku,
    (payload ->> 'price')::numeric(10, 2)                           as price,
    case when (payload ->> 'list_price')::numeric > (payload ->> 'price')::numeric
         then (payload ->> 'list_price')::numeric(10, 2) end        as list_price,
    (payload ->> 'in_stock')::boolean                               as available
from {{ source('raw', 'offers') }}
where platform = 'gomag'
