# Sample data

Twenty public product records, collected on 2026-11-01 from the shops' public catalogues, used by the tests and by CI:

- three games sold by several shops (matched by barcode), a few games sold by one shop, and a few products that are not board games (to test the filter);
- one Pionul product page (schema.org data);
- four Regatul Jocurilor listing records (three games with their barcodes and one accessory).

`day2.jsonl` is `day1.jsonl` one day later with **one synthetic change**: the Kingdomino price at Jocozaur is lowered by 20%, so that the price-history snapshot has something to record. It is not a real price.
