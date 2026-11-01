-- A barcode identifies exactly one game: no two game_keys may share an EAN.
select ean, count(distinct game_key) as games
from {{ ref('dim_games') }}
where ean is not null
group by ean
having count(distinct game_key) > 1
