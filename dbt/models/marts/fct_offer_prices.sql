-- The daily fact: one row per board-game offer per shop per day it was collected.
select
    o.collected_on,
    o.shop,
    o.offer_id,
    k.game_key,
    k.match_method,
    o.title,
    o.price,
    o.list_price,
    o.available,
    o.url
from {{ ref('int_offers') }} o
join {{ ref('int_offer_game_keys') }} k using (offer_id)
where o.is_board_game
