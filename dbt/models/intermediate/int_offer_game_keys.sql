-- Which game is each offer? Three rules, from the most to the least certain:
--   1. ean          the offer carries a valid barcode
--   2. title_to_ean another offer with the same match_title and edition language carries one
--                   (the most common barcode for that title wins)
--   3. title        no barcode anywhere: the game is identified by its title and language
-- The offer's latest day decides its title, so a shop renaming a product moves it once.
with latest as (
    select distinct on (offer_id)
        offer_id, ean, match_title, edition_language
    from {{ ref('int_offers') }}
    where is_board_game
    order by offer_id, collected_on desc
),

title_ean as (
    select match_title, coalesce(edition_language, '?') as lang, ean,
           row_number() over (partition by match_title, coalesce(edition_language, '?')
                              order by count(*) desc, ean) as rn
    from latest
    where ean is not null and match_title is not null
    group by 1, 2, 3
)

select
    l.offer_id,
    coalesce(l.ean, t.ean)                                              as ean,
    case
        when l.ean is not null then 'ean:' || l.ean
        when t.ean is not null then 'ean:' || t.ean
        else 'title:' || l.match_title || '|' || coalesce(l.edition_language, '?')
    end                                                                 as game_key,
    case
        when l.ean is not null then 'ean'
        when t.ean is not null then 'title_to_ean'
        else 'title'
    end                                                                 as match_method
from latest l
left join title_ean t
    on t.match_title = l.match_title
   and t.lang = coalesce(l.edition_language, '?')
   and t.rn = 1
where l.match_title is not null
