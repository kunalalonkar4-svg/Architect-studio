"""Reference plans shown to Claude in the system prompt. They are checked by the test suite against the real engine, so the
format and rules they demonstrate can never drift out of date. They show the quality bar; Claude must still design each plot afresh."""
import json


def _R(k, n, kind, x, y, w, h, l="GF"):
    return dict(key=k, name=n, kind=kind, level=l, x=x, y=y, w=w, h=h)


def _C(a, b, t="door"):
    return dict(a=a, b=b, type=t)


# 20 x 50 ft plot, road south, open spaces front 1.5 m, rear 1.0 m, sides 0: envelope 5850 x 12500
PLAN_20X50 = dict(
    summary="2BHK on a narrow plot: living with sit-out at the road, kitchen-dining behind it, then a side passage serving two bedrooms and the wet rooms",
    entry_room="living",
    rooms=[_R("living", "Living", "living", 0, 0, 3900, 3200), _R("sitout", "Sit-out", "sitout", 3900, 0, 1950, 3200),
           _R("kitchen", "Kitchen", "kitchen", 0, 3200, 2400, 2800), _R("dining", "Dining", "dining", 2400, 3200, 3450, 2800),
           _R("bed1", "Bedroom 1", "bedroom", 0, 6000, 3300, 3300), _R("bed2", "Bedroom 2", "bedroom", 0, 9300, 3300, 3200),
           _R("passage", "Passage", "passage", 3300, 6000, 1050, 6500), _R("toilet", "Toilet", "toilet", 4350, 6000, 1500, 2400),
           _R("store", "Store", "store", 4350, 8400, 1500, 1950), _R("toilet2", "Toilet 2", "toilet", 4350, 10350, 1500, 2150)],
    connections=[_C("living", "sitout"), _C("living", "dining", "open"), _C("kitchen", "dining", "open"), _C("dining", "passage", "open"),
                 _C("bed1", "passage"), _C("bed2", "passage"), _C("toilet", "passage"), _C("store", "passage"), _C("toilet2", "passage")])

# 40 x 50 ft plot, road south, open spaces front 3 m, rear 1.5 m, sides 0.9 m: envelope 10150 x 10500. Duplex 4BHK.
PLAN_40X50_DUPLEX = dict(
    summary="Duplex 4BHK: parking, living, dining, kitchen and a study/guest room below; master suite and two bedrooms with a shared toilet above the same stair",
    entry_room="entry",
    rooms=[_R("living", "Living", "living", 0, 0, 5000, 4600), _R("entry", "Entry", "entry", 5000, 0, 2300, 1600),
           _R("stair", "Staircase", "stair", 5000, 1600, 2300, 3000), _R("parking", "Car Parking", "parking", 7300, 0, 2850, 4600),
           _R("dining", "Dining", "dining", 0, 4600, 7300, 3000), _R("toilet", "Toilet", "toilet", 7300, 4600, 2850, 1500),
           _R("store", "Store", "store", 7300, 6100, 2850, 1500), _R("bed1", "Bedroom 1", "bedroom", 0, 7600, 3650, 2900),
           _R("kitchen", "Kitchen", "kitchen", 3650, 7600, 2350, 2900), _R("study", "Study", "study", 6000, 7600, 4150, 2900),
           _R("f_master", "Master Bedroom", "bedroom", 0, 0, 5000, 4600, "FF"), _R("f_toilet1", "Toilet (attached)", "toilet", 5000, 0, 2300, 1600, "FF"),
           _R("f_stair", "Staircase", "stair", 5000, 1600, 2300, 3000, "FF"), _R("f_balcony", "Balcony", "balcony", 7300, 0, 2850, 4600, "FF"),
           _R("f_lounge", "Family Lounge", "passage", 0, 4600, 7300, 3000, "FF"), _R("f_toilet", "Toilet", "toilet", 7300, 4600, 2850, 1500, "FF"),
           _R("f_store", "Store", "store", 7300, 6100, 2850, 1500, "FF"), _R("f_bed2", "Bedroom 3", "bedroom", 0, 7600, 3650, 2900, "FF"),
           _R("f_toilet2", "Toilet (shared)", "toilet", 3650, 7600, 1500, 2900, "FF"), _R("f_bed3", "Bedroom 4", "bedroom", 5150, 7600, 5000, 2900, "FF")],
    connections=[_C("living", "dining", "open"), _C("dining", "stair", "open"), _C("living", "entry"), _C("parking", "entry"), _C("dining", "kitchen", "open"),
                 _C("dining", "bed1"), _C("dining", "study"), _C("dining", "toilet"), _C("dining", "store"),
                 _C("f_lounge", "f_stair", "open"), _C("f_lounge", "f_master"), _C("f_master", "f_toilet1"), _C("f_stair", "f_balcony"),
                 _C("f_lounge", "f_bed2"), _C("f_lounge", "f_bed3"), _C("f_bed2", "f_toilet2"), _C("f_bed3", "f_toilet2"),
                 _C("f_lounge", "f_toilet"), _C("f_lounge", "f_store")])


def examples_text() -> str:
    return ("EXAMPLE 1 - 20 x 50 ft plot (envelope 5850 x 12500 mm), call design_floor_plan with:\n" + json.dumps(PLAN_20X50, separators=(",", ":")) +
            "\n\nEXAMPLE 2 - 40 x 50 ft plot (envelope 10150 x 10500 mm), duplex 4BHK:\n" + json.dumps(PLAN_40X50_DUPLEX, separators=(",", ":")))
