-- All shops in one shape, plus what the matching needs:
--   ean               a real barcode (check digit verified) if the shop exposes one
--   match_title       the title reduced to the game's name (util.match_title)
--   edition_language  ro / en when the title says so: a Romanian and an English edition
--                     are different products and must not be matched together
--   is_board_game     from the reference/board_game_categories seed; when several patterns
--                     match a category, the most specific (longest) one wins
with unioned as (
    select * from {{ ref('stg_shopify_offers') }}
    union all
    select * from {{ ref('stg_jsonld_offers') }}
    union all
    select * from {{ ref('stg_prestashop_offers') }}
    union all
    select * from {{ ref('stg_gomag_offers') }}
),

categorised as (
    select
        u.*,
        (select c.is_board_game
         from {{ ref('board_game_categories') }} c
         where c.shop = u.shop and coalesce(u.category, '') like c.category_pattern
         order by length(c.category_pattern) desc
         limit 1) as is_board_game
    from unioned u
)

select
    shop,
    collected_on,
    offer_id,
    url,
    title,
    brand,
    category,
    sku,
    util.valid_ean(sku)                                   as ean,
    util.match_title(title)                               as match_title,
    case
        when public.unaccent(lower(title)) ~ '(limba|lb\.?)\s+romana|\(ro\)|\mro$|editie romaneasca|romanian edition|roman nyelvu' then 'ro'
        when public.unaccent(lower(title)) ~ '(limba|lb\.?)\s+engleza|\(en\)|\(eng\)|\men$|english edition|angol nyelvu' then 'en'
    end                                                   as edition_language,
    price,
    list_price,
    available,
    coalesce(is_board_game, false)                        as is_board_game
from categorised
where price > 0
