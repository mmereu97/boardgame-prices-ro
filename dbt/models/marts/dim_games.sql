-- One row per game. The display title is the one most shops use; ties go to a Romanian
-- title over a Hungarian one (Jocozaur), then to the shortest.
with offers as (
    select f.*, k.ean
    from {{ ref('fct_offer_prices') }} f
    join {{ ref('int_offer_game_keys') }} k using (offer_id)
),

titles as (
    select game_key, title,
           row_number() over (partition by game_key
                              order by count(distinct shop) desc,
                                       (title ~* 'nyelv|társasjáték|kártyajáték'),
                                       length(title), title) as rn
    from offers
    group by game_key, title
)

select
    o.game_key,
    max(o.ean)                                  as ean,
    t.title,
    count(distinct o.shop)                      as shops,
    count(distinct o.offer_id)                  as offers,
    min(o.collected_on)                         as first_seen,
    max(o.collected_on)                         as last_seen
from offers o
join titles t on t.game_key = o.game_key and t.rn = 1
group by o.game_key, t.title
