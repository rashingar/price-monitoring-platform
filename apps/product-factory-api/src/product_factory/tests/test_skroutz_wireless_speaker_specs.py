from product_factory.parser_product_skroutz import SkroutzProductParser


def test_skroutz_speaker_summary_enriches_wireless_speaker_specs() -> None:
    url = "https://www.skroutz.gr/s/63718085/crystal-audio-prt-20.html"
    html = """
    <html><body>
      <div class="sku-title"><a class="category-tag" href="/c/2682/karaoke.html">Karaoke</a><h1 class="page-title">Crystal Audio PRT-20</h1><small class="sku-code">63718085</small></div>
      <a class="brand-page-link"><span>Crystal Audio</span></a>
      <div class="summary"><div class="description long"><div class="body-text">Bluetooth 5.3 • 200W • Tweeter 1x1,5’’ & 2xWoofer 10’’ • Απόκριση συχνοτήτων 60Hz-18kHz • Ενσωματωμένη μπαταρία διάρκειας 6 ωρών • Διάρκεια φόρτισης από 6 έως 8 ώρες • LED φωτισμός party flame light • LCD οθόνη • FM radio • Πολλαπλοί είσοδοι USB,SD card, Mic, Guitar, AUX in • Περιλαμβάνει ασύρματο μικρόφωνο • Δυνατότητα σύνδεσης ενσύρματου μικροφώνου (δεν περιλαμβάνεται) • Διαστάσεις 38x36x89,5cm • Βάρος 21,8kg • TWS</div></div></div>
      <div id="specs"><div class="spec-groups"><div class="spec-details"><h3>Γενικά</h3><dl><dt>Ισχύς (RMS)</dt><dd>200 W</dd></dl></div></div></div>
    </body></html>
    """

    parsed = SkroutzProductParser().parse(html, url)
    values = {item.label: item.value for section in parsed.source.spec_sections for item in section.items}

    assert parsed.source.page_type == "product"
    assert values["Bluetooth"] == "5.3"
    assert values["TWS Stereo Pairing"] == "Ναι"
    assert values["Απόκριση Συχνοτήτων"] == "60Hz-18kHz"
    assert values["Ασύρματο Μικρόφωνο"] == "Περιλαμβάνεται"
    assert values["Βάρος"] == "21,8kg"
