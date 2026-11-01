-- PrestaShop listing (the shop's own JSON). The product type is in "reference" (Joc de baza,
-- Extensie, Accesoriu...); a product without an add-to-cart link is out of stock; the barcode
-- comes from the product page, remembered by the collector (null until it has been read).
select
    shop,
    collected_on,
    shop || ':' || (payload ->> 'id_product')                       as offer_id,
    url,
    payload ->> 'name'                                              as title,
    null::text                                                      as brand,
    payload ->> 'reference'                                         as category,
    payload ->> 'gtin13'                                            as sku,
    (payload ->> 'price_amount')::numeric(10, 2)                    as price,
    case when (payload ->> 'has_discount')::boolean
         then (payload ->> 'regular_price_amount')::numeric(10, 2) end as list_price,
    nullif(payload ->> 'add_to_cart_url', '') is not null           as available
from {{ source('raw', 'offers') }}
where platform = 'prestashop'
