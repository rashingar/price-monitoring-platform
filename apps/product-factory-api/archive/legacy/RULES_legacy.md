## CSV EXPORT / IMPORT TEMPLATE RULES (CRITICAL)

Historical note:
- This archived rules file preserves the pre-M5 legacy workflow wording.
- File references such as `product_import_template.csv`, `TEMPLATE_presentation.html`, and `catalog_taxonomy.json` are retained as pre-M6 root-asset references for provenance and should not be read as current runtime paths.

After every successful product generation, also generate a downloadable `.csv` import file for OpenCart.

### SOURCE OF TRUTH
- Use `product_import_template.csv` from Sources as the source of truth for:
  - exact header names
  - exact header order
- Never reorder headers based on `opencart active catalog.csv`.
- The active catalog may be used only to understand formatting conventions, not to override the template header order.

### MANDATORY MODEL RULE
- A confirmed 6-digit model is mandatory.
- If the 6-digit model is missing, ambiguous, or not confirmed, output exactly:
  `Generation failed, provide 6-digit model`
- In that failure case:
  - do NOT generate product content
  - do NOT generate HTML blocks
  - do NOT generate categories/filters
  - do NOT generate a CSV file

### EXPECTED INPUT FORMAT FOR FOLLOW-UP PROMPTS
Follow-up prompts after the master prompt may use this shape:
- `model:`
- `url:`
- `photos:`default is `1`
- `sections:`default is `0`
- `skroutz_status:` default is `0`
- `boxnow:` default is `0`
- `price:` default is `0`

Rules:
- `model:` = mandatory confirmed 6-digit model
- `url:` = mandatory product source URL
- `photos:` = optional integer
- `sections:` = optional integer for besco sections
- If `photos:` is missing, default to `1`
- If `sections:` is missing, default is `0`
- If `skroutz_status:` is missing, default is `0`
- If `boxnow:` is missing, default is `0`
- If `price:` is missing,  default is `0`

### CSV FILE OUTPUT RULES
- The CSV filename must be:
  `{model}.csv`
- The CSV must contain exactly **2 rows**:
  1. first row = headers
  2. second row = values
- Use the exact headers from `product_import_template.csv`
- Use UTF-8 encoding
- Do not add extra rows, notes, comments, or blank lines

### FIXED DEFAULT VALUES
Always set these fields exactly as follows unless the template itself requires a different header name:
- `status = 0`
- `quantity = 0`
- `skroutz_status = 0`
- `boxnow = 0`
- `minimum = 1`
- `subtract = 1`

### IMAGE RULES
Use the prompt `model` and `photos` fields to build image values.

#### Main image
- `image = "catalog/01_main/{model}/{model}-1.jpg"`

#### Additional images
- `additional_image` is derived from `photos - 1`
- If `photos: 1` or `photos` is missing, then:
  - `additional_image = ""`
- If `photos: N` and `N > 1`, then:
  - start from `catalog/01_main/{model}/{model}-2.jpg`
  - continue through `catalog/01_main/{model}/{model}-N.jpg`
  - join values using `:::`

Examples:
- model `330825`, photos `1`
  - `image = "catalog/01_main/330825/330825-1.jpg"`
  - `additional_image = ""`
- model `330825`, photos `3`
  - `image = "catalog/01_main/330825/330825-1.jpg"`
  - `additional_image = "catalog/01_main/330825/330825-2.jpg:::catalog/01_main/330825/330825-3.jpg"`
- model `330825`, photos `5`
  - `image = "catalog/01_main/330825/330825-1.jpg"`
  - `additional_image = "catalog/01_main/330825/330825-2.jpg:::catalog/01_main/330825/330825-3.jpg:::catalog/01_main/330825/330825-4.jpg:::catalog/01_main/330825/330825-5.jpg"`

### HTML PRESENTATION TEMPLATE RULES (MANDATORY)

Use `TEMPLATE_presentation.html` as the sole structural source of truth for the HTML in **Παρουσίαση**.

#### Core rule
- The HTML presentation template is mandatory.
- Generate exactly **ONE** HTML code block for **Παρουσίαση**.
- The HTML skeleton must follow `TEMPLATE_presentation.html` exactly.
- Do NOT rewrite, simplify, compress, restyle, or improvise the template structure.
- Do NOT output Markdown outside the single HTML block.

#### Static wrapper structure (locked)
The HTML must always follow this exact top-level order:

1. `<div class="etr-desc">`
2. centered H2 title
3. intro paragraph
4. CTA wrapper with button
5. `<hr />`
6. inner `<div class="etr-desc">`
7. zero or more feature section blocks
8. closing wrappers

#### Allowed classes only
Use only these exact class names where shown in the template:
- `etr-desc`
- `etr-sec`
- `etr-sec rev`
- `etr-text`
- `etr-img`

Do NOT invent, rename, merge, split, or replace these class names.

#### Static HTML wrappers (locked)
Use these exact wrappers and styles:

##### Product title
```html
<h2 style="text-align:center"><span style="font-size:36px"><strong>...</strong></span></h2>
```

##### Intro paragraph
```html
<p style="margin-left:auto; margin-right:auto; text-align:left"><span style="font-size:24px">...</span></p>
```

##### CTA wrapper
```html
<div style="margin-bottom:20px; margin-left:auto; margin-right:auto; margin-top:20px; text-align:center">...</div>
```

##### CTA button
```html
<a href="..." style="font-size: 20px; padding: 12px 28px; background-color: #03BABE; color: #F7FCFC; border-radius: 12px; text-decoration: none;">...</a>
```

##### Feature heading
```html
<h2><span style="font-size:24px"><strong>...</strong></span></h2>
```

##### Feature paragraph
```html
<p><span style="font-size:22px">...</span></p>
```

#### Section layout (locked)
- Odd-numbered feature sections must use:
```html
<div class="etr-sec">
  <div class="etr-text">...</div>
  <div class="etr-img"><img ... /></div>
</div>
```

- Even-numbered feature sections must use:
```html
<div class="etr-sec rev">
  <div class="etr-text">...</div>
  <div class="etr-img"><img ... /></div>
</div>
```

#### Child order rule (locked)
Inside **every** feature section, keep this exact child order:
1. `<div class="etr-text">...</div>`
2. `<div class="etr-img"><img ... /></div>`

Do NOT swap text/image order manually.

#### Even-image alignment rule (locked)
For every even-numbered section image (`besco2.jpg`, `besco4.jpg`, etc.), the `<img>` tag must include this exact inline style:
```html
style="display:block; margin-left:auto; margin-right:0;"
```

Do NOT apply this right-alignment style to odd-numbered section images unless the template explicitly requires it.

#### Image container rule
Every feature image must always stay inside:
```html
<div class="etr-img"><img ... /></div>
```

Do NOT remove the `etr-img` wrapper.

#### Besco image path rule
Feature image src must always use this exact path format:
```html
https://www.etranoulis.gr/image/catalog/01_bescos/{model}/bescoN.jpg
```

Rules:
- `{model}` must be the confirmed 6-digit model
- `N` must match the section number (`1, 2, 3, ...`)
- no placeholder folder is allowed
- if the confirmed 6-digit model is missing, generation must fail according to the mandatory model rule

#### CTA style rule
The CTA block must always preserve:
- `font-size: 20px`
- `padding: 12px 28px`
- `background-color: #03BABE`
- `color: #F7FCFC`
- `border-radius: 12px`
- `text-decoration: none;`

Do NOT alter CTA colors, spacing, border radius, or text-decoration unless the source template itself is updated.

#### Intro/body typography rule
Always preserve these static font-size wrappers:
- title: `36px`
- intro paragraph: `24px`
- feature headings: `24px`
- feature paragraphs: `22px`

Do NOT substitute other static font sizes.

#### Locked static tags
The following tags/wrappers are mandatory where applicable:
- outer `<div class="etr-desc">`
- inner `<div class="etr-desc">`
- `<hr />`
- CTA wrapper `<div ...>`
- `<h2><span><strong>...</strong></span></h2>`
- paragraph `<p><span>...</span></p>`

#### Zero-sections rule
If `sections = 0`, still output:
- outer `.etr-desc`
- H2
- intro paragraph
- CTA block
- `<hr />`
- inner `.etr-desc`

But output **no** feature section blocks inside the inner `.etr-desc`.

#### Hard prohibitions
- Do NOT invent alternative wrappers.
- Do NOT remove the nested inner `.etr-desc`.
- Do NOT replace `etr-sec rev` with only inline styling.
- Do NOT add extra containers around the section blocks.
- Do NOT change wrapper nesting.
- Do NOT omit `<hr />`.
- Do NOT output multiple HTML blocks.
- Do NOT convert the HTML to plain text.
- Do NOT strip inline styles that exist in the template.
- Do NOT place sources/citations inside the HTML.

#### Validation before final output
The HTML presentation is invalid if any of the following is true:
- outer `.etr-desc` is missing
- inner `.etr-desc` is missing
- H2 / intro / CTA / `<hr />` / inner sections order is changed
- any even-numbered section is missing `class="etr-sec rev"`
- any odd-numbered section incorrectly uses `rev`
- any section changes the order of `.etr-text` and `.etr-img`
- any required class name differs from the template
- any even-numbered image is missing:
  `style="display:block; margin-left:auto; margin-right:0;"`
- more than one HTML code block is produced for **Παρουσίαση**



### FIELD MAPPING FOR CSV VALUES
Map the generated product content into the CSV fields using these rules:

- `model` → confirmed 6-digit model
- `mpn` → value from **MPN**
- `name` → value from **Όνομα Προϊόντος**, following the locked product-name schema defined in the master prompt
- `description` → HTML from **Παρουσίαση**
- `characteristics` → HTML from **Τεχνικά Χαρακτηριστικά**
- `category` → serialized category value built from:
  - Parent Category
  - Leaf Category
  - Sub Category
- `image` → `catalog/01_main/{model}/{model}-1.jpg`
- `additional_image` → from `photos` rule above
- `manufacturer` → inferred brand/manufacturer from the exact product
- `price` → `0` unless explicitly provided
- `quantity` → `0`
- `minimum` → `1`
- `subtract` → `1`
- `stock_status` → `Έως 30 ημέρες`
- `status` → `0`
- `meta_keyword` → value from **Meta Keywords**
- `meta_title` → value from **Meta Title**
- `meta_description` → value from **Meta Description**
- `seo_keyword` → value from **SEO URL**
- `product_url` → `https://www.etranoulis.gr/{seo_keyword}`
- `related_product` → leave empty unless explicitly provided
- `bestprice_status` → `1`
- `skroutz_status` → `0` unless explicitly provided
- `boxnow` → `0` unless explicitly provided

### CATEGORY SERIALIZATION RULE
When building the CSV `category` field, follow this exact process:

1. Resolve the canonical category nodes from `catalog_taxonomy.json` using verified product context:
   - `parent_category`
   - `leaf_category`
   - `sub_category`

2. Build the OpenCart serialized `category` field as a late-derived import string, not as a plain label.

3. Use this exact serialization format:
   - with subcategory:
     `Parent:::Parent///Leaf:::Parent///Leaf///Sub`
   - without subcategory:
     `Parent:::Parent///Leaf`

4. Serialization rules:
   - use `:::` to separate selected category nodes
   - use `///` to express hierarchy inside each node path
   - preserve the exact resolved Greek category labels
   - do not invent category levels
   - do not reorder resolved levels
   - if `sub_category` is missing or unresolved, serialize only:
     `Parent:::Parent///Leaf`

5. BoxNow overlay rule:
   - if `boxnow = 1`, append `:::Μικροσυσκευές` to the final serialized `category` string
   - this append happens AFTER canonical category serialization is completed
   - treat `Μικροσυσκευές` as an import-only overlay category for downstream workflows
   - do not use `Μικροσυσκευές` to replace the canonical taxonomy match

6. Hard rules:
   - if `parent_category` or `leaf_category` cannot be resolved confidently, leave the CSV `category` field empty rather than guessing
   - do not serialize a standalone subcategory without resolved parent and leaf
   - do not use CTA labels or filter groups as substitutes for category nodes

7. Examples:
   - Parent=`ΕΙΚΟΝΑ & ΗΧΟΣ`, Leaf=`Audio Systems`, Sub=`Sound Bars`
     → `ΕΙΚΟΝΑ & ΗΧΟΣ:::ΕΙΚΟΝΑ & ΗΧΟΣ///Audio Systems:::ΕΙΚΟΝΑ & ΗΧΟΣ///Audio Systems///Sound Bars`

   - Parent=`ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ`, Leaf=`Συσκευές Κουζίνας`, Sub=`Μπλέντερ`
     → `ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Συσκευές Κουζίνας:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Συσκευές Κουζίνας///Μπλέντερ`

   - same as above with `boxnow = 1`
     → `ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Συσκευές Κουζίνας:::ΟΙΚΙΑΚΟΣ ΕΞΟΠΛΙΣΜΟΣ///Συσκευές Κουζίνας///Μπλέντερ:::Μικροσυσκευές`

   - Parent=`ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ`, Leaf=`Απορροφητήρες`, Sub=`-`
     → `ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ:::ΟΙΚΙΑΚΕΣ ΣΥΣΚΕΥΕΣ///Απορροφητήρες`

### SANITIZATION RULES
Before writing the CSV:
- trim leading/trailing spaces from all scalar fields
- preserve HTML exactly in `description` and `characteristics`
- escape CSV values correctly when they contain:
  - commas
  - quotes
  - line breaks
  - HTML
- do not alter Greek characters
- do not strip accents
- do not convert HTML to plain text

### OUTPUT BEHAVIOR
For every valid generation:
1. Generate the `.csv` file named `{model}.csv`
- Constraint: it must be created locally under `products/{model}.csv`
2. Then generate the normal product output in the required format
- If the active master prompt defines a chat-output override, follow that override for what is shown in chat.
- Current override target: after the CSV artifact, chat may render only `0) Φίλτρα` while the remaining sections are still generated internally as needed for CSV mapping and validation.

For invalid generation due to missing/unconfirmed 6-digit model:
- output exactly:
  `Generation failed, provide 6-digit model`

### HARD FAIL CONDITIONS
Treat the generation as failed if any of the following is true:
- `model` is missing
- `model` is not exactly 6 digits
- the 6-digit model cannot be confirmed from the prompt/context
- multiple conflicting model codes exist

In any hard fail condition, output exactly:
`Generation failed, provide 6-digit model`
