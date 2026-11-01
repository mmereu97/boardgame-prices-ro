{#-
  Two small SQL functions used by the models, created at the start of every run:

  util.valid_ean(text)  -> the code if it is a valid EAN-13 / EAN-8 (check digit verified), else null.
                           Shops often put the barcode in the SKU field; the check digit tells a real
                           barcode from an internal code that happens to be 13 digits long.
  util.match_title(text) -> a product title reduced to what identifies the game across shops:
                           lower case, no diacritics, no marketing words, no punctuation.
-#}
{% macro create_helper_functions() %}
create extension if not exists unaccent;
create schema if not exists util;

create or replace function util.valid_ean(code text) returns text
language sql immutable as $$
    select case
        when code ~ '^[0-9]{13}$'
             and (10 - (select sum(substr(code, i, 1)::int * case when i % 2 = 0 then 3 else 1 end)
                        from generate_series(1, 12) i) % 10) % 10 = substr(code, 13, 1)::int
            then code
        when code ~ '^[0-9]{8}$'
             and (10 - (select sum(substr(code, i, 1)::int * case when i % 2 = 1 then 3 else 1 end)
                        from generate_series(1, 7) i) % 10) % 10 = substr(code, 8, 1)::int
            then code
    end
$$;

create or replace function util.match_title(title text) returns text
language sql immutable as $$
    select nullif(trim(regexp_replace(regexp_replace(regexp_replace(regexp_replace(
        lower(public.unaccent(coalesce(title, ''))),
        -- language and edition labels: the language is kept separately (see edition_language)
        '\(?\m(editie|editia|versiunea|versiune)?\s*(in\s+)?(limba|lb\.?)\s+(romana|engleza)\)?|\((ro|en|eng)\)|\m(ro|en)$|\m(roman|angol)\s+nyelvu\M', ' ', 'g'),
        -- generic product words that shops add in front of or after the name (Romanian, English,
        -- and Hungarian: Jocozaur publishes many titles in Hungarian)
        '\m(joc|jocul|jocuri)\s+(de\s+)?(societate|petrecere|carti|familie|strategie|board|baza)\M|\mboard\s*games?\M|\m(base|core)\s+game\M|\m(tarsasjatek|kartyajatek|jubileumi\s+kiadas)\M', ' ', 'g'),
        '[^a-z0-9]+', ' ', 'g'),
        '\s+', ' ', 'g')), '')
$$;
{% endmacro %}
