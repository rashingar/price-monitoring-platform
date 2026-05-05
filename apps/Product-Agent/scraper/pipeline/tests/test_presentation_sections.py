from pipeline.presentation_sections import normalize_presentation_sections


def test_normalize_presentation_sections_marks_usable_section() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "Αθόρυβη λειτουργία",
                "paragraph": (
                    "Η συσκευή λειτουργεί αθόρυβα και σταθερά σε κάθε κύκλο, ώστε να ταιριάζει εύκολα "
                    "στην καθημερινή χρήση του σπιτιού. Η πρακτική διαρρύθμιση βοηθά την οργάνωση, "
                    "ενώ η σταθερή απόδοση υποστηρίζει την άνετη χρήση για πολλές διαφορετικές ανάγκες."
                ),
            }
        ]
    )

    section = sections[0]
    assert section.title == "Αθόρυβη λειτουργία"
    assert section.body_text.startswith("Η συσκευή λειτουργεί αθόρυβα")
    assert section.quality == "usable"
    assert section.reason == "usable_clean"
    assert section.metrics.word_count >= 25
    assert section.metrics.alphabetic_char_count >= 120


def test_normalize_presentation_sections_marks_weak_short_body() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "Γρήγορη χρήση",
                "paragraph": "Πρακτική λύση για καθημερινή χρήση με καθαρό αποτέλεσμα.",
            }
        ]
    )

    section = sections[0]
    assert section.quality == "weak"
    assert section.reason == "weak_short_body"


def test_normalize_presentation_sections_marks_missing_empty_after_clean() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "Κενό μπλοκ",
                "paragraph": "<div><script>ignored()</script><style>.x{}</style><span>   </span></div>",
            }
        ]
    )

    section = sections[0]
    assert section.body_text == ""
    assert section.quality == "missing"
    assert section.reason == "missing_empty_after_clean"


def test_normalize_presentation_sections_marks_missing_image_only() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "Εικόνα μόνο",
                "paragraph": "<div><img src=\"https://example.com/image.jpg\" /></div>",
                "image_url": "https://example.com/image.jpg",
            }
        ]
    )

    section = sections[0]
    assert section.body_text == ""
    assert section.quality == "missing"
    assert section.reason == "missing_image_only"


def test_normalize_presentation_sections_marks_weak_missing_title() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "",
                "paragraph": (
                    "Η προσεγμένη σχεδίαση βοηθά την τακτοποίηση του χώρου και προσφέρει άνετη πρόσβαση "
                    "στα βασικά σημεία χρήσης, ενώ η καθαρή οργάνωση υποστηρίζει την καθημερινή πρακτικότητα "
                    "χωρίς περιττές κινήσεις ή πρόσθετα βήματα."
                ),
            }
        ]
    )

    section = sections[0]
    assert section.quality == "weak"
    assert section.reason == "weak_missing_title"


def test_normalize_presentation_sections_marks_duplicate_against_previously_accepted_sections() -> None:
    sections = normalize_presentation_sections(
        [
                {
                    "title": "Άνετη χρήση",
                    "paragraph": (
                        "Η ευέλικτη διάταξη βοηθά την καθημερινή χρήση και κρατά τα βασικά σημεία εύκολα προσβάσιμα "
                        "για πιο ξεκούραστη και σταθερή εμπειρία σε κάθε κύκλο λειτουργίας, ενώ η πρακτική οργάνωση "
                        "διευκολύνει την τοποθέτηση των απαραίτητων αντικειμένων και υποστηρίζει σταθερή απόδοση "
                        "κατά τη συχνή χρήση στο σπίτι."
                    ),
                },
                {
                    "title": "Άνεση κάθε μέρα",
                    "paragraph": (
                        "Η ευέλικτη διάταξη βοηθά την καθημερινή χρήση και κρατά τα βασικά σημεία εύκολα προσβάσιμα "
                        "για πιο ξεκούραστη και σταθερή εμπειρία σε κάθε κύκλο λειτουργίας, ενώ η πρακτική οργάνωση "
                        "διευκολύνει την τοποθέτηση των απαραίτητων αντικειμένων και υποστηρίζει σταθερή απόδοση "
                        "κατά τη συχνή χρήση στο σπίτι."
                    ),
                },
        ]
    )

    assert sections[0].quality == "usable"
    assert sections[1].quality == "weak"
    assert sections[1].reason == "weak_duplicate"
    assert sections[1].metrics.is_duplicate is True


def test_normalize_presentation_sections_preserves_source_order() -> None:
    sections = normalize_presentation_sections(
        [
            {"title": "Πρώτο", "paragraph": "Αυτό είναι το πρώτο τμήμα με αρκετό περιεχόμενο για καθαρή ταξινόμηση και σταθερή σειρά."},
            {"title": "Δεύτερο", "paragraph": "Αυτό είναι το δεύτερο τμήμα με αρκετό περιεχόμενο για καθαρή ταξινόμηση και σταθερή σειρά."},
        ]
    )

    assert [section.source_index for section in sections] == [1, 2]
    assert [section.title for section in sections] == ["Πρώτο", "Δεύτερο"]


def test_normalize_presentation_sections_preserves_wording_after_cleaning() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "Καθαρή διατύπωση",
                "paragraph": "<p>Διατηρεί <strong>την ίδια</strong> διατύπωση χωρίς αναδιατύπωση ή σύνοψη.</p>",
            }
        ]
    )

    assert sections[0].body_text == "Διατηρεί την ίδια διατύπωση χωρίς αναδιατύπωση ή σύνοψη."


def test_normalize_presentation_sections_cleans_whitespace_and_html() -> None:
    sections = normalize_presentation_sections(
        [
            {
                "title": "  Έξυπνη   ροή  ",
                "paragraph": "<div>  Πρώτη πρόταση. <br/> Δεύτερη πρόταση.  </div>",
            }
        ]
    )

    assert sections[0].title == "Έξυπνη ροή"
    assert sections[0].body_text == "Πρώτη πρόταση. Δεύτερη πρόταση."


def test_normalize_presentation_sections_pads_missing_extraction_when_requested_count_exceeds_source() -> None:
    sections = normalize_presentation_sections(
        [{"title": "Μόνο ένα", "paragraph": "Υπάρχει μόνο ένα διαθέσιμο τμήμα με επαρκές σώμα για έλεγχο."}],
        sections_requested=2,
    )

    assert len(sections) == 2
    assert sections[1].quality == "missing"
    assert sections[1].reason == "missing_extraction"
