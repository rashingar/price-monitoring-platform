# spec_label_cache_log.md (append-only)

Entry format:
- timestamp: <ISO 8601>
- electronet_product_url: <url>
- product_category: <category>
- template_id: <id>
- schema_path: resources/COMMON_LABEL_SETS/<template_id>.json
- action: CREATED | UPDATED | REUSED
- sections: ["SECTION 1", "SECTION 2", ...]
- diff_summary: <short text or "-">
- fingerprint: <sha256>

---
- timestamp: 2026-02-28T13:51:00+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/xyristikes-mihanes/one-blade-philips-qp654215-pro-360?v=34621
- product_category: Ξυριστικές Μηχανές
- template_id: xyristikes_mixanes
- schema_path: resources/COMMON_LABEL_SETS/xyristikes_mixanes.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος"]
- diff_summary: Replaced legacy schema with normalized cache format and aligned exact Electronet labels/order for code 341503.
- fingerprint: f405fa2daa5fdcd3bf37534030ce1540f931979757fe865566e8046ef4ed6c4b

---
- timestamp: 2026-02-28T14:45:20+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/xyristikes-mihanes/xyristiki-mihani-philips-bg348515-wet-dry?v=38513
- product_category: Ξυριστικές Μηχανές
- template_id: xyristikes_mixanes
- schema_path: resources/COMMON_LABEL_SETS/xyristikes_mixanes.json
- action: REUSED
- sections: ["Επισκόπηση Προϊόντος"]
- diff_summary: -
- fingerprint: f405fa2daa5fdcd3bf37534030ce1540f931979757fe865566e8046ef4ed6c4b

---
- timestamp: 2026-02-28T14:49:09+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/koyreytikes-mihanes/xyristiki-mihani-rowenta-tn2804?v=38913
- product_category: Κουρευτικές Μηχανές
- template_id: koyreytikes_mixanes
- schema_path: resources/COMMON_LABEL_SETS/koyreytikes_mixanes.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος"]
- diff_summary: Migrated legacy schema to normalized format and aligned exact Electronet section/label order; removed non-canonical second section.
- fingerprint: 0ff888d3ce2147eef1fe69940ac69f99fba2127b27a1ab2acaf680129df3bb98

---
- timestamp: 2026-02-28T14:51:29+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/xyristikes-mihanes/xyristiki-mihani-philips-s314300-wet-dry?v=30555
- product_category: Ξυριστικές Μηχανές
- template_id: xyristikes_mixanes
- schema_path: resources/COMMON_LABEL_SETS/xyristikes_mixanes.json
- action: REUSED
- sections: ["Επισκόπηση Προϊόντος"]
- diff_summary: -
- fingerprint: f405fa2daa5fdcd3bf37534030ce1540f931979757fe865566e8046ef4ed6c4b

---
- timestamp: 2026-02-28T14:56:33+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/gynaikeia-frontida/boyrtses-psalidia/psalidi-mallion-rowenta-cf321l
- product_category: Βούρτσες-Ψαλίδια-ισιωτικά
- template_id: voyrtses_psalidia_isiotika
- schema_path: resources/COMMON_LABEL_SETS/voyrtses_psalidia_isiotika.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος", "Μεταφορά - Αποθήκευση"]
- diff_summary: Replaced legacy steam-brush schema with exact Electronet curling-iron labels/sections/order for this template and migrated to normalized cache format.
- fingerprint: 11d98a2c7207be9ac07280230be8ec8740cc0363412a63a7b8a9ac03e2fe7398

---
- timestamp: 2026-02-28T15:00:04+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/gynaikeia-frontida/isiotika-mallion/isiotiko-mallion-philips-bhs52000
- product_category: Βούρτσες-Ψαλίδια-ισιωτικά
- template_id: isiotika_mallion
- schema_path: resources/COMMON_LABEL_SETS/isiotika_mallion.json
- action: CREATED
- sections: ["Επισκόπηση Προϊόντος", "Γενικά Χαρακτηριστικά"]
- diff_summary: Created new template for straightener schema with exact Electronet sections/labels/order.
- fingerprint: 3b8e2e01245ea6a933d72b3279ee9cd9f68707baf0478e007e00a740e5dd10f6

---
- timestamp: 2026-02-28T15:03:10+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/gynaikeia-frontida/isiotika-mallion/isiotiko-mallion-philips-bhs75200?v=25835
- product_category: Βούρτσες-Ψαλίδια-ισιωτικά
- template_id: isiotika_mallion
- schema_path: resources/COMMON_LABEL_SETS/isiotika_mallion.json
- action: REUSED
- sections: ["Επισκόπηση Προϊόντος", "Γενικά Χαρακτηριστικά"]
- diff_summary: -
- fingerprint: 3b8e2e01245ea6a933d72b3279ee9cd9f68707baf0478e007e00a740e5dd10f6

---
- timestamp: 2026-02-28T15:06:20+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/gynaikeia-frontida/sesoyar/sesoyar-mallion-philips-drycare-pro-bhd272-2100-watt?v=20604
- product_category: Σεσουάρ
- template_id: sesoyar
- schema_path: resources/COMMON_LABEL_SETS/sesoyar.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος", "Γενικά Χαρακτηριστικά"]
- diff_summary: Migrated legacy schema to normalized cache format and aligned exact Electronet labels/order.
- fingerprint: d702d6964a73f81f8b99292a113fed03820a4229b1e0a98cfaa44354ddee1aa8

---
- timestamp: 2026-03-03T14:14:24+02:00
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/koyzines/koyzines-keramikes/koyzina-keramiki-eskimo-es-vc503w
- product_category: Κουζίνες
- template_id: koyzines
- schema_path: resources/COMMON_LABEL_SETS/koyzines.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος", "Ασφάλεια", "Ενεργειακά Χαρακτηριστικά", "Γενικά Χαρακτηριστικά"]
- diff_summary: Added missing schema fingerprint; canonical Electronet sections/labels already matched existing order and wording.
- fingerprint: 3ed2693c44a4b94ff6687b4c8dac878e823383b6c32c0e16c16f0c3857ac685c

---
---
- timestamp: 2026-03-05T11:57:42+02:00
- electronet_product_url: https://www.electronet.gr/pliroforiki/tablets/ola-ta-tablets/tablet-samsung-galaxy-tab-a9-87-64gb-wifi-graphite
- product_category: Android [ΤΗΛΕΦΩΝΙΑ > Tablets]
- template_id: tablets_tandroid
- schema_path: resources/COMMON_LABEL_SETS/tablets_tandroid.json
- action: UPDATED
- sections: ["Οθόνη", "Επεξεργαστής", "Μνήμη", "Λειτουργικό", "Camera", "Συνδεσιμότητα", "Γενικά Χαρακτηριστικά"]
- diff_summary: Added missing schema fingerprint and appended current Electronet URL example; canonical Electronet sections/labels/order already matched existing schema.
- fingerprint: 247a8e6ed5873b2fd326f36d4e8251c304a909f6f6fc25c400a5bbf0aaefed90
---
- timestamp: 2026-03-05T12:09:06+02:00
- electronet_product_url: https://www.electronet.gr/pliroforiki/tablets/ola-ta-tablets/tablet-samsung-galaxy-tab-a9-87-64gb-wifi-navy
- product_category: Android [ΤΗΛΕΦΩΝΙΑ > Tablets]
- template_id: tablets_tandroid
- schema_path: resources/COMMON_LABEL_SETS/tablets_tandroid.json
- action: REUSED
- sections: ["Οθόνη", "Επεξεργαστής", "Μνήμη", "Λειτουργικό", "Camera", "Συνδεσιμότητα", "Γενικά Χαρακτηριστικά"]
- diff_summary: -
- fingerprint: 247a8e6ed5873b2fd326f36d4e8251c304a909f6f6fc25c400a5bbf0aaefed90
---
- timestamp: 2026-03-05T13:50:13+02:00
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/psygeia-katapsyktes/psygeiokatapsyktes/psygeiokatapsyktis-lg-gbbw726cev-anthraki-c
- product_category: Ψυγειοκαταψύκτες
- template_id: psygeiokatapsyktes
- schema_path: resources/COMMON_LABEL_SETS/psygeiokatapsyktes.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος", "Συντήρηση", "Κατάψυξη", "Ενεργειακά χαρακτηριστικά", "Γενικά χαρακτηριστικά"]
- diff_summary: Normalized schema format, aligned exact Electronet section/label strings (including spacing), added CTA metadata, Electronet example URL, and schema fingerprint.
- fingerprint: f5d503e2c3d34e02bc24564ff32dab6fb33346c80a5a556c0b2e40e84188222b
---
- timestamp: 2026-03-05T14:18:36+02:00
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/gynaikeia-frontida/zygaries-somatos/zygaria-somatos-first-fa-8006-3-si-asimi?v=27787
- product_category: Ζυγαρίες Σώματος
- template_id: zygaries_somatos
- schema_path: resources/COMMON_LABEL_SETS/zygaries_somatos.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος", "Ειδικές Λειτουργίες", "Γενικά Χαρακτηριστικά"]
- diff_summary: Added missing schema fingerprint and appended current Electronet product URL example; canonical Electronet sections/labels/order already matched.
- fingerprint: a98b76fe5ca513583ae77c8f24cf41b6285c584e9ab2c9320cc086356c3fac08
- timestamp: 2026-03-06T16:20:02+02:00
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/stegnotiria/stegnotirio-royhon-bosch-wqg243b9gr-9-kg-c
- product_category: ??????????? ??????
- template_id: stegnotiria_rouxwn
- schema_path: resources/COMMON_LABEL_SETS/stegnotiria_rouxwn.json
- action: UPDATED
- sections: ["?????????? ?????????", "???????? ???????????", "?????????? ??????????????", "?????? ??????????????"]
- diff_summary: Normalized legacy schema format, added schema fingerprint and current Electronet example URL; canonical Electronet sections/labels/order already matched existing schema.
- fingerprint: ccc94227f80df3c4f8ec4f4661310b24a6b0213d736f9a897bddd36ce2db7398
---
- timestamp: 2026-03-06T16:28:10+02:00
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/stegnotiria/stegnotirio-royhon-bosch-wqg243b9gr-9-kg-c
- product_category: Στεγνωτήρια Ρούχων
- template_id: stegnotiria_rouxwn
- schema_path: resources/COMMON_LABEL_SETS/stegnotiria_rouxwn.json
- action: UPDATED
- sections: ["Επισκόπηση Προϊόντος", "Επιλογές Στεγνώματος", "Ενεργειακά Χαρακτηριστικά", "Γενικά Χαρακτηριστικά"]
- diff_summary: Corrected UTF-8 regeneration for the current Electronet URL entry; canonical Electronet sections/labels/order already matched existing schema.
- fingerprint: ccc94227f80df3c4f8ec4f4661310b24a6b0213d736f9a897bddd36ce2db7398
---

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/kafes-hymoi-rofimata/kafetieres-espresso/kafetiera-espresso-delonghi-magnifica-start-ecam22080sb-asimi-mayro
- product_category: Καφετιέρες Espresso
- template_id: kafetieres_espresso
- schema_path: resources/COMMON_LABEL_SETS/kafetieres_espresso.json
- action: REUSED
- electronet_section_names: ["Επισκόπηση Προϊόντος", "Γενικά Χαρακτηριστικά"]
- diff_summary: -
- label-set fingerprint: reused-kafetieres-espresso-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-65u7q-65-smart-4k-mini-led
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-75u7q-75-smart-4k-mini-led
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-55u7q-pro-55-smart-4k-mini-led-pro
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-55e7q-pro-55-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-43e7q-43-smart-4k
- product_category: 33''-50''
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-55a6q-55-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-65a6q-65-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:02:20
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-75a6q-75-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/kafes-hymoi-rofimata/kafetieres-espresso/kafetiera-espresso-delonghi-magnifica-start-ecam22080sb-asimi-mayro
- product_category: Καφετιέρες Espresso
- template_id: kafetieres_espresso
- schema_path: resources/COMMON_LABEL_SETS/kafetieres_espresso.json
- action: REUSED
- electronet_section_names: ["Επισκόπηση Προϊόντος", "Γενικά Χαρακτηριστικά"]
- diff_summary: -
- label-set fingerprint: reused-kafetieres-espresso-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-65u7q-65-smart-4k-mini-led
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-75u7q-75-smart-4k-mini-led
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-55u7q-pro-55-smart-4k-mini-led-pro
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-55e7q-pro-55-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-43e7q-43-smart-4k
- product_category: 33''-50''
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-55a6q-55-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-65a6q-65-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:03:18
- electronet_product_url: https://www.electronet.gr/eikona-ihos/tileoraseis/oles-oi-tileoraseis/tv-hisense-75a6q-75-smart-4k
- product_category: 50'' & άνω
- template_id: tileoraseis
- schema_path: resources/COMMON_LABEL_SETS/tileoraseis.json
- action: REUSED
- electronet_section_names: ["Εικόνα - Ήχος", "Λειτουργίες", "Συνδέσεις", "Γενικά"]
- diff_summary: -
- label-set fingerprint: reused-tileoraseis-json

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-tcl-s55he
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-hisense-wd3s8043bw3-8-kg5-kg-ad
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/entoihizomenes/foyrnoi/foyrnos-entoihizomenos-miele-h-2455-b-active-mayro-obsidian
- product_category: built_in_oven
- template_id: built_in_oven
- schema_path: resources/COMMON_LABEL_SETS/built_in_oven.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-built_in_oven

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-lg-s30a
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/skoypa-stick-rohnson-r-1239-mple
- product_category: stick_vacuum
- template_id: stick_vacuum
- schema_path: resources/COMMON_LABEL_SETS/stick_vacuum.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-stick_vacuum

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/koyreytikes-mihanes/koyreytiki-mihani-rohnson-mod-r-1018
- product_category: clipper
- template_id: clipper
- schema_path: resources/COMMON_LABEL_SETS/clipper.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-clipper

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/mikroi-mageires/fryganieres/fryganiera-rohnson-mod-r-2215-prasino
- product_category: toaster
- template_id: toaster
- schema_path: resources/COMMON_LABEL_SETS/toaster.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-toaster

## 2026-03-12T22:31:55
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-eskimo-es-w8d6admst-8-kg-6-kg-10d
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-tcl-s55he
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-hisense-wd3s8043bw3-8-kg5-kg-ad
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/entoihizomenes/foyrnoi/foyrnos-entoihizomenos-miele-h-2455-b-active-mayro-obsidian
- product_category: built_in_oven
- template_id: built_in_oven
- schema_path: resources/COMMON_LABEL_SETS/built_in_oven.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-built_in_oven

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-lg-s30a
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/skoypa-stick-rohnson-r-1239-mple
- product_category: stick_vacuum
- template_id: stick_vacuum
- schema_path: resources/COMMON_LABEL_SETS/stick_vacuum.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-stick_vacuum

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/koyreytikes-mihanes/koyreytiki-mihani-rohnson-mod-r-1018
- product_category: clipper
- template_id: clipper
- schema_path: resources/COMMON_LABEL_SETS/clipper.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-clipper

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/mikroi-mageires/fryganieres/fryganiera-rohnson-mod-r-2215-prasino
- product_category: toaster
- template_id: toaster
- schema_path: resources/COMMON_LABEL_SETS/toaster.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-toaster

## 2026-03-12T22:33:03
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-eskimo-es-w8d6admst-8-kg-6-kg-10d
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-tcl-s55he
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-hisense-wd3s8043bw3-8-kg5-kg-ad
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/entoihizomenes/foyrnoi/foyrnos-entoihizomenos-miele-h-2455-b-active-mayro-obsidian
- product_category: built_in_oven
- template_id: built_in_oven
- schema_path: resources/COMMON_LABEL_SETS/built_in_oven.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-built_in_oven

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-lg-s30a
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/skoypa-stick-rohnson-r-1239-mple
- product_category: stick_vacuum
- template_id: stick_vacuum
- schema_path: resources/COMMON_LABEL_SETS/stick_vacuum.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-stick_vacuum

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/koyreytikes-mihanes/koyreytiki-mihani-rohnson-mod-r-1018
- product_category: clipper
- template_id: clipper
- schema_path: resources/COMMON_LABEL_SETS/clipper.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-clipper

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/mikroi-mageires/fryganieres/fryganiera-rohnson-mod-r-2215-prasino
- product_category: toaster
- template_id: toaster
- schema_path: resources/COMMON_LABEL_SETS/toaster.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-toaster

## 2026-03-12T22:35:04
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-eskimo-es-w8d6admst-8-kg-6-kg-10d
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-tcl-s55he
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-hisense-wd3s8043bw3-8-kg5-kg-ad
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/entoihizomenes/foyrnoi/foyrnos-entoihizomenos-miele-h-2455-b-active-mayro-obsidian
- product_category: built_in_oven
- template_id: built_in_oven
- schema_path: resources/COMMON_LABEL_SETS/built_in_oven.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-built_in_oven

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/eikona-ihos/audio-home-systems/sound-bars-docking-stations/soundbar-lg-s30a
- product_category: soundbar
- template_id: soundbar
- schema_path: resources/COMMON_LABEL_SETS/soundbar.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-soundbar

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/skoypisma/skoypes-stick/skoypa-stick-rohnson-r-1239-mple
- product_category: stick_vacuum
- template_id: stick_vacuum
- schema_path: resources/COMMON_LABEL_SETS/stick_vacuum.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-stick_vacuum

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/andriki-peripoiisi/koyreytikes-mihanes/koyreytiki-mihani-rohnson-mod-r-1018
- product_category: clipper
- template_id: clipper
- schema_path: resources/COMMON_LABEL_SETS/clipper.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-clipper

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/exoplismos-spitioy/mikroi-mageires/fryganieres/fryganiera-rohnson-mod-r-2215-prasino
- product_category: toaster
- template_id: toaster
- schema_path: resources/COMMON_LABEL_SETS/toaster.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-toaster

## 2026-03-12T22:35:42
- electronet_product_url: https://www.electronet.gr/oikiakes-syskeyes/plyntiria-stegnotiria/plyntiria-stegnotiria/plyntirio-stegnotirio-royhon-eskimo-es-w8d6admst-8-kg-6-kg-10d
- product_category: washer_dryer
- template_id: washer_dryer
- schema_path: resources/COMMON_LABEL_SETS/washer_dryer.json
- action: REUSED
- electronet_section_names: reused from exact Electronet page
- diff_summary: -
- label-set fingerprint: reused-washer_dryer
