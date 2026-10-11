# Card ids

Every card in a game has a unique integer id, shared by the server and the
client:

```
id    = deck * 54 + index
deck  = 0, 1 or 2
index = 0-51  suited cards: suit * 13 + (rank - 1)
        52-53 jokers
suit  = 0 spades, 1 hearts, 2 diamonds, 3 clubs
rank  = 1 (ace) to 13 (king)
```

Card codes used in tests and fixtures: rank `A 2-9 T J Q K` followed by
suit `S H D C` (e.g. `AH`, `TS`, `QD`), and `JK` for a joker. Codes don't
say which deck a card comes from; in fixtures a repeated code means a card
from the next deck.
