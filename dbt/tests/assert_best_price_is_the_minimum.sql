-- The "best price" must really be the lowest in-stock price among shops today.
with latest_day as (
    select shop, max(collected_on) as day from {{ ref('fct_offer_prices') }} group by shop
),
today as (
    select f.game_key, min(f.price) as min_price
    from {{ ref('fct_offer_prices') }} f
    join latest_day d on d.shop = f.shop and d.day = f.collected_on
    where f.available
    group by f.game_key
)
select b.game_key, b.best_price, t.min_price
from {{ ref('mart_best_prices') }} b
join today t using (game_key)
where b.best_price <> t.min_price
