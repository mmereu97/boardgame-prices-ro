-- Where to buy each game today, and whether today's price is a good one.
-- "Today" is each shop's latest collection day, so a shop that failed last night still
-- shows yesterday's price instead of disappearing.
with latest_day as (
    select shop, max(collected_on) as day
    from {{ ref('fct_offer_prices') }}
    group by shop
),

current_offers as (
    select f.*
    from {{ ref('fct_offer_prices') }} f
    join latest_day d on d.shop = f.shop and d.day = f.collected_on
    where f.available
),

ranked as (
    select c.*, row_number() over (partition by game_key order by price, shop) as rn
    from current_offers c
),

history as (
    select game_key,
           min(price) filter (where collected_on >= current_date - 90) as lowest_90d,
           min(price)                                                    as lowest_ever
    from {{ ref('fct_offer_prices') }}
    where available
    group by game_key
)

select
    g.game_key,
    g.title,
    g.ean,
    b.price                                     as best_price,
    b.shop                                      as best_shop,
    b.url                                       as best_url,
    count(*)                                    as shops_in_stock,
    max(r.price)                                as highest_price,
    max(r.price) - b.price                      as savings_vs_highest,
    h.lowest_90d,
    h.lowest_ever,
    b.price <= h.lowest_ever                    as is_lowest_ever
from ranked b
join ranked r on r.game_key = b.game_key
join {{ ref('dim_games') }} g on g.game_key = b.game_key
join history h on h.game_key = b.game_key
where b.rn = 1
group by g.game_key, g.title, g.ean, b.price, b.shop, b.url, h.lowest_90d, h.lowest_ever
